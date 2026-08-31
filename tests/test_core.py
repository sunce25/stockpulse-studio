import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

try:
    import requests  # noqa: F401
except ImportError:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = RuntimeError
    requests_stub.get = None
    sys.modules["requests"] = requests_stub

from modules.data_adapter import DataAdapter
from modules.cloud_storage import CloudBackedWatchlistManager
from modules.indicators import add_all_indicators, add_rsi
from modules.screener import StockScreener
from modules.watchlist import DEFAULT_WATCHLIST_DATA, WatchlistManager, has_active_position


def make_kline(length=30, rising=True):
    close = np.arange(1, length + 1, dtype=float)
    if not rising:
        close = close[::-1]
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=length),
            "open": close - 0.2,
            "close": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "volume": np.full(length, 1000.0),
        }
    )


class IndicatorTests(unittest.TestCase):
    def test_rsi_is_100_for_continuous_gains(self):
        result = add_rsi(make_kline()[["close"]], periods=(6,))
        self.assertEqual(result.iloc[-1]["RSI_6"], 100.0)

    def test_kline_is_sorted_and_deduplicated(self):
        source = pd.concat([make_kline(5), make_kline(5).iloc[[-1]]], ignore_index=True)
        result = add_all_indicators(source.sample(frac=1, random_state=1))
        self.assertEqual(len(result), 5)
        self.assertTrue(result["date"].is_monotonic_increasing)


class ScreenerTests(unittest.TestCase):
    def test_technical_strategy_with_no_matches_returns_empty(self):
        pool = pd.DataFrame(
            [{"symbol": "TEST", "price": 10, "pct_chg": 1, "pe": 10, "mktcap": 500}]
        )
        adapter = types.SimpleNamespace(
            get_market_spot_pool=lambda **kwargs: pool.copy(),
            get_kline_data=lambda *args, **kwargs: make_kline(rising=False),
        )
        result = StockScreener(adapter).screen(preset_strategy="均线多头精选")
        self.assertTrue(result.empty)


class BatchQuoteTests(unittest.TestCase):
    @staticmethod
    def _quote_response(symbol="600519", name="贵州茅台", price="1500"):
        fields = [""] * 46
        fields[1], fields[2], fields[3], fields[4], fields[5] = (
            name,
            symbol,
            price,
            "1490",
            "1495",
        )
        fields[6], fields[31], fields[32], fields[33], fields[34] = (
            "100",
            "10",
            "0.67",
            "1510",
            "1480",
        )
        return types.SimpleNamespace(
            content=(f'v_sh{symbol}="' + "~".join(fields) + '";').encode("gbk")
        )

    def test_realtime_quote_uses_short_lived_cache(self):
        adapter = DataAdapter()
        response = self._quote_response()
        with patch("modules.data_adapter.requests.get", return_value=response) as request_get:
            first = adapter.get_realtime_quote("600519", "A股")
            second = adapter.get_realtime_quote("600519", "A股")

        self.assertEqual(first["price"], 1500.0)
        self.assertEqual(second, first)
        request_get.assert_called_once()

    def test_batch_quotes_use_short_lived_cache(self):
        adapter = DataAdapter()
        response = self._quote_response()
        items = [{"symbol": "600519", "market": "A股", "name": "贵州茅台"}]
        with patch("modules.data_adapter.requests.get", return_value=response) as request_get:
            first = adapter.get_batch_quotes(items)
            second = adapter.get_batch_quotes(items)

        self.assertEqual(second, first)
        request_get.assert_called_once()

    def test_kline_cache_returns_defensive_copies(self):
        adapter = DataAdapter()
        source = make_kline(10)
        with patch.object(
            adapter,
            "_get_kline_data_uncached",
            return_value=source,
        ) as fetch:
            first = adapter.get_kline_data("600519", "A股", limit=10)
            first.loc[0, "close"] = -999
            second = adapter.get_kline_data("600519", "A股", limit=10)

        self.assertNotEqual(second.loc[0, "close"], -999)
        fetch.assert_called_once()

    def test_newer_us_extended_quote_overlays_regular_close(self):
        adapter = DataAdapter()
        base = {
            "symbol": "AAPL",
            "market": "美股",
            "price": 100.0,
            "prev_close": 99.0,
            "time": "2026-08-28 16:00:01",
            "source": "腾讯行情",
        }
        extended = {
            "price": 101.0,
            "change": 2.0,
            "pct_chg": 2.0202,
            "time": "2026-08-31 08:00:00 EDT",
            "source": "Yahoo Finance 分钟行情",
            "session": "盘前",
            "is_extended_hours": True,
            "timestamp": 1788181200,
        }
        with patch.object(adapter, "_get_us_extended_quote", return_value=extended):
            result = adapter._apply_us_extended_quote(base)
        self.assertEqual(result["price"], 101.0)
        self.assertEqual(result["session"], "盘前")

    def test_older_extended_quote_does_not_replace_regular_quote(self):
        adapter = DataAdapter()
        base = {
            "symbol": "AAPL",
            "market": "美股",
            "price": 100.0,
            "prev_close": 99.0,
            "time": "2026-08-28 16:00:01",
            "source": "腾讯行情",
        }
        with patch.object(
            adapter,
            "_get_us_extended_quote",
            return_value={"price": 90.0, "timestamp": 1},
        ):
            result = adapter._apply_us_extended_quote(base)
        self.assertEqual(result["price"], 100.0)
        self.assertEqual(result["source"], "腾讯行情")

    def test_partial_batch_response_preserves_input_order(self):
        adapter = DataAdapter()
        items = [
            {"symbol": "AAPL", "market": "美股"},
            {"symbol": "MSFT", "market": "美股"},
        ]
        fields = [""] * 35
        fields[1], fields[2], fields[3], fields[4], fields[5] = "微软", "MSFT", "400", "390", "395"
        fields[6], fields[31], fields[32], fields[33], fields[34] = "100", "10", "2.56", "405", "392"
        response = types.SimpleNamespace(content=("v_usmsft=\"" + "~".join(fields) + "\";").encode("gbk"))

        def fallback(symbol, market):
            return {"symbol": symbol, "market": market, "price": 0.0}

        with patch("modules.data_adapter.requests.get", return_value=response), patch.object(
            adapter, "get_realtime_quote", side_effect=fallback
        ):
            result = adapter.get_batch_quotes(items)

        self.assertEqual([quote["symbol"] for quote in result], ["AAPL", "MSFT"])
        self.assertEqual(result[1]["price"], 400.0)

    def test_usd_cny_rate_is_fetched_and_cached(self):
        adapter = DataAdapter()
        fields = ["", "美元人民币", "USD/CNY", "6.745925"]
        response = types.SimpleNamespace(content=("~".join(fields)).encode("gbk"))
        with patch("modules.data_adapter.requests.get", return_value=response) as request_get:
            first = adapter.get_usd_cny_rate()
            second = adapter.get_usd_cny_rate()

        self.assertEqual(first, 6.745925)
        self.assertEqual(second, first)
        self.assertEqual(adapter.usd_cny_rate_source, "腾讯财经实时汇率")
        request_get.assert_called_once()

    def test_usd_cny_offline_fallback_is_current_and_labeled(self):
        adapter = DataAdapter()
        malformed = types.SimpleNamespace(content=b"", json=lambda: {})
        with patch("modules.data_adapter.requests.get", return_value=malformed):
            rate = adapter.get_usd_cny_rate()

        self.assertEqual(rate, 6.745925)
        self.assertEqual(adapter.usd_cny_rate_source, "内置参考（2026-08-30）")


class WatchlistTests(unittest.TestCase):
    def test_active_position_requires_positive_shares(self):
        self.assertTrue(has_active_position({"shares": 0.016957449}))
        self.assertFalse(has_active_position({"shares": 0}))
        self.assertFalse(has_active_position({"shares": ""}))
        self.assertFalse(has_active_position({"shares": "invalid"}))

    def test_save_is_valid_and_does_not_mutate_defaults(self):
        original_defaults = copy.deepcopy(DEFAULT_WATCHLIST_DATA)
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "watchlist.json"
            manager = WatchlistManager(str(data_file))
            manager.add_stock("TEST", "测试", group="全部")
            with data_file.open(encoding="utf-8") as saved:
                content = json.load(saved)
            self.assertTrue(any(item["symbol"] == "TEST" for item in content["items"]))
        self.assertEqual(DEFAULT_WATCHLIST_DATA, original_defaults)

    def test_batch_hide_is_persistent_and_reversible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "watchlist.json"
            manager = WatchlistManager(str(data_file))

            changed = manager.set_stocks_hidden(["NVDA", "AAPL"], hidden=True)
            self.assertEqual(changed, 2)
            reloaded = WatchlistManager(str(data_file))
            hidden_symbols = {
                item["symbol"]
                for item in reloaded.get_items()
                if item.get("hidden_from_portfolio", False)
            }
            self.assertEqual(hidden_symbols, {"NVDA", "AAPL"})

            restored = reloaded.set_stocks_hidden(["NVDA", "AAPL"], hidden=False)
            self.assertEqual(restored, 2)
            self.assertFalse(
                any(item.get("hidden_from_portfolio", False) for item in reloaded.get_items())
            )

    def test_fractional_us_shares_round_trip_to_nine_decimals(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "watchlist.json"
            manager = WatchlistManager(str(data_file))
            manager.add_stock(
                "NVDA",
                "英伟达",
                market="美股",
                group="美股科技",
                cost_price=100.0,
                shares=0.123456789,
            )

            saved = WatchlistManager(str(data_file)).get_stock("NVDA")
            self.assertEqual(f"{saved['shares']:.9f}", "0.123456789")

    def test_custom_subset_order_is_persistent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "watchlist.json"
            manager = WatchlistManager(str(data_file))

            changed = manager.reorder_stocks(["TSLA", "NVDA", "AAPL"])
            self.assertTrue(changed)
            saved_symbols = [
                item["symbol"] for item in WatchlistManager(str(data_file)).get_items()
            ]
            self.assertEqual(saved_symbols[:3], ["TSLA", "NVDA", "AAPL"])

    def test_custom_group_create_rename_and_assignment_are_persistent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = Path(temp_dir) / "watchlist.json"
            manager = WatchlistManager(str(data_file))

            self.assertTrue(manager.add_group("量化观察"))
            manager.add_stock(
                "NVDA",
                "英伟达",
                market="美股",
                group="量化观察",
            )
            self.assertEqual(manager.get_stock("NVDA")["group"], "量化观察")

            self.assertTrue(manager.rename_group("量化观察", "AI核心"))
            reloaded = WatchlistManager(str(data_file))
            self.assertIn("AI核心", reloaded.get_groups())
            self.assertNotIn("量化观察", reloaded.get_groups())
            self.assertEqual(reloaded.get_stock("NVDA")["group"], "AI核心")
            self.assertFalse(reloaded.rename_group("全部", "不可重命名"))

    def test_supabase_watchlist_round_trip_uses_remote_document(self):
        class FakeResponse:
            def __init__(self, payload=None):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return copy.deepcopy(self.payload)

        class FakeSupabaseSession:
            def __init__(self):
                self.rows = {}
                self.last_headers = {}

            def get(self, _url, params, headers, timeout):
                _ = timeout
                self.last_headers = headers
                record_id = params["id"].removeprefix("eq.")
                payload = self.rows.get(record_id)
                return FakeResponse([] if payload is None else [{"payload": payload}])

            def post(self, _url, params, json, headers, timeout):
                _ = (params, timeout)
                self.last_headers = headers
                self.rows[json["id"]] = copy.deepcopy(json["payload"])
                return FakeResponse()

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_session = FakeSupabaseSession()
            first_file = Path(temp_dir) / "first.json"
            manager = CloudBackedWatchlistManager(
                data_file=str(first_file),
                project_url="https://example.supabase.co",
                secret_key="sb_secret_test",
                session=fake_session,
            )
            self.assertEqual(manager.persistence_mode, "cloud")
            self.assertTrue(manager.add_group("云端分组"))
            self.assertIn("云端分组", fake_session.rows["primary"]["groups"])
            self.assertNotIn("Authorization", fake_session.last_headers)

            second_file = Path(temp_dir) / "second.json"
            reloaded = CloudBackedWatchlistManager(
                data_file=str(second_file),
                project_url="https://example.supabase.co",
                secret_key="sb_secret_test",
                session=fake_session,
            )
            self.assertIn("云端分组", reloaded.get_groups())
            self.assertEqual(reloaded.remote_error, "")


if __name__ == "__main__":
    unittest.main()
