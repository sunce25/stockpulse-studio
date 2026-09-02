import os
import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ai.context_builder import ANALYSIS_HISTORY_FIELDS, build_analysis_context
from ai.copilot import AICopilot, EMPTY_QUESTION_MESSAGE
from services.openrouter import OPENROUTER_CHAT_URL, generate_ai_analysis
from config.settings import get_setting
from funds.auth_store import SupabaseYangJiBaoAuthStore
from funds.fund_adapter import (
    FUND_HOLDING_FIELDS,
    assess_data_freshness,
    get_demo_holdings,
    normalize_fund_holding,
)
from funds.fund_analyzer import FundAnalyzer
from funds.holding_history import (
    append_sync_history,
    build_sync_record,
    sanitize_sync_record,
)
from funds.portfolio_analyzer import PortfolioAnalyzer
from funds.snapshot_store import FundSnapshotError, SupabaseFundSnapshotStore
from funds.yangjibao_client import YangJiBaoClient, YangJiBaoError


class SettingsTests(unittest.TestCase):
    def test_environment_takes_precedence(self):
        with patch.dict(os.environ, {"STOCKPULSE_TEST_SETTING": "env-value"}):
            self.assertEqual(get_setting("STOCKPULSE_TEST_SETTING", "fallback"), "env-value")

    def test_missing_setting_uses_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_setting("STOCKPULSE_MISSING_SETTING", "fallback"), "fallback")


class FundArchitectureTests(unittest.TestCase):
    def test_openrouter_returns_stable_result_and_uses_bearer_header(self):
        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "组合风险可控。"}}]}

        class FakeSession:
            def post(self, url, headers, json, timeout, allow_redirects):
                self.url = url
                self.headers = headers
                self.body = copy.deepcopy(json)
                self.timeout = timeout
                self.allow_redirects = allow_redirects
                return FakeResponse()

        session = FakeSession()
        result = generate_ai_analysis(api_key="private-openrouter-key", model="openrouter/free", system_prompt="只解释数据", task_prompt="分析组合", context={"portfolio_summary": {"risk_score": 20}}, session=session)

        self.assertEqual(result, {"success": True, "model": "openrouter/free", "content": "组合风险可控。", "error": None})
        self.assertEqual(session.url, OPENROUTER_CHAT_URL)
        self.assertEqual(session.headers["Authorization"], "Bearer private-openrouter-key")
        self.assertNotIn("private-openrouter-key", str(session.body))
        self.assertEqual(session.body["model"], "openrouter/free")
        self.assertEqual(session.body["temperature"], 0.2)
        self.assertEqual(session.body["max_tokens"], 1400)
        self.assertFalse(session.allow_redirects)

    def test_openrouter_missing_key_is_safe(self):
        result = generate_ai_analysis(api_key="", model="openrouter/free", system_prompt="", task_prompt="", context={})
        self.assertFalse(result["success"])
        self.assertIn("OPENROUTER_API_KEY", result["error"])

    def test_copilot_uses_injected_provider_without_exposing_key(self):
        class FakeProvider:
            def generate(self, **kwargs):
                self.request = kwargs
                return {"success": True, "model": "openrouter/free", "content": "仅基于上下文的回答", "error": None}

        provider = FakeProvider()
        copilot = AICopilot(
            api_key="private-key",
            model="openrouter/free",
            client=provider.generate,
        )
        answer = copilot.answer_question(
            {"portfolio_summary": {"risk_score": 20}}, "最大风险是什么？"
        )

        self.assertEqual(answer["content"], "仅基于上下文的回答")
        self.assertEqual(provider.request["context"]["user_question"], "最大风险是什么？")
        self.assertEqual(provider.request["model"], "openrouter/free")
        self.assertNotIn("api_key", copilot.configuration_status())
        self.assertEqual(copilot.answer_question({}, "")["error"], EMPTY_QUESTION_MESSAGE)

    def test_sync_history_distinguishes_investment_from_valuation(self):
        previous = [
            {
                **get_demo_holdings()[0],
                "fund_code": "A",
                "fund_name": "定投基金",
                "shares": 100.0,
                "cost_amount": 100.0,
                "market_value": 110.0,
            },
            {
                **get_demo_holdings()[1],
                "fund_code": "B",
                "fund_name": "估值基金",
                "shares": 100.0,
                "cost_amount": 100.0,
                "market_value": 110.0,
            },
        ]
        current = copy.deepcopy(previous)
        current[0].update(shares=110.0, cost_amount=110.0, market_value=121.0)
        current[1]["market_value"] = 112.0

        record = build_sync_record(previous, current, "2026-09-01T10:00:00+00:00")

        self.assertEqual(record["changed_fund_count"], 2)
        self.assertEqual(record["investment_change_count"], 1)
        self.assertEqual(record["changes"][0]["change_type"], "份额增加")
        self.assertEqual(record["changes"][1]["change_type"], "估值变化")
        self.assertEqual(record["cost_change"], 10.0)

    def test_sync_history_is_bounded_and_newest_first(self):
        history = []
        for index in range(5):
            history = append_sync_history(
                history, {"timestamp": str(index), "status": "success"}, limit=3
            )
        self.assertEqual([item["timestamp"] for item in history], ["4", "3", "2"])

    def test_sync_history_restore_uses_field_whitelist(self):
        restored = sanitize_sync_record(
            {
                "timestamp": "2026-09-01T10:00:00+00:00",
                "status": "success",
                "token": "must-not-survive",
                "changes": [{"fund_code": "A", "cookie": "must-not-survive"}],
            }
        )
        self.assertNotIn("token", restored)
        self.assertNotIn("cookie", restored["changes"][0])

    def test_yangjibao_authorization_is_encrypted_at_rest(self):
        class FakeResponse:
            def __init__(self, payload=None):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return copy.deepcopy(self.payload)

        class FakeSession:
            def __init__(self):
                self.rows = {}

            def get(self, _url, params, headers, timeout):
                _ = (headers, timeout)
                record_id = params["id"].removeprefix("eq.")
                payload = self.rows.get(record_id)
                return FakeResponse([] if payload is None else [{"payload": payload}])

            def post(self, _url, params, json, headers, timeout):
                _ = (params, headers, timeout)
                self.rows[json["id"]] = copy.deepcopy(json["payload"])
                return FakeResponse()

        session = FakeSession()
        store = SupabaseYangJiBaoAuthStore(
            "https://example.supabase.co",
            "sb_secret_test",
            "high-entropy-server-material",
            session=session,
        )
        store.save("private-token", "account-1", "长期账户", 3)

        persisted_text = str(session.rows["primary-yangjibao-auth"])
        self.assertNotIn("private-token", persisted_text)
        self.assertNotIn("account-1", persisted_text)
        self.assertEqual(store.load()["token"], "private-token")
        self.assertEqual(store.load()["account_id"], "account-1")

    def test_fund_snapshot_round_trip_excludes_provider_credentials(self):
        class FakeResponse:
            def __init__(self, payload=None):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return copy.deepcopy(self.payload)

        class FakeSession:
            def __init__(self):
                self.rows = {}

            def get(self, _url, params, headers, timeout):
                _ = (headers, timeout)
                record_id = params["id"].removeprefix("eq.")
                payload = self.rows.get(record_id)
                return FakeResponse([] if payload is None else [{"payload": payload}])

            def post(self, _url, params, json, headers, timeout):
                _ = (params, headers, timeout)
                self.rows[json["id"]] = copy.deepcopy(json["payload"])
                return FakeResponse()

        session = FakeSession()
        store = SupabaseFundSnapshotStore(
            "https://example.supabase.co",
            "sb_secret_test",
            session=session,
        )
        store.save(get_demo_holdings(), "2026-09-01T10:00:00+00:00")
        restored = store.load()

        self.assertEqual(len(restored["holdings"]), 3)
        self.assertEqual(restored["updated_at"], "2026-09-01T10:00:00+00:00")
        self.assertEqual(restored["schema_version"], 2)
        self.assertEqual(len(restored["history"]), 1)
        self.assertEqual(restored["history"][0]["status"], "success")
        persisted_text = str(session.rows["primary-funds"]).lower()
        self.assertNotIn("token", persisted_text)
        self.assertNotIn("cookie", persisted_text)
        self.assertNotIn("account_id", persisted_text)

    def test_fund_snapshot_rejects_credential_fields(self):
        holding = get_demo_holdings()[0]
        holding["access_token"] = "must-not-persist"
        store = SupabaseFundSnapshotStore(
            "https://example.supabase.co",
            "sb_secret_test",
            session=object(),
        )
        with self.assertRaises(FundSnapshotError):
            store.save([holding])

    def test_normalized_model_contains_required_and_qdii_fields(self):
        holding = normalize_fund_holding({"fund_code": "X", "shares": 10, "latest_nav": 2})
        self.assertTrue(set(FUND_HOLDING_FIELDS).issubset(holding))
        self.assertIn("estimated_nav_time", holding)
        self.assertIn("market_timezone", holding)

    def test_string_boolean_and_future_timestamp_are_safe(self):
        holding = normalize_fund_holding(
            {"fund_code": "X", "is_qdii": "false", "stale_data": "false"}
        )
        self.assertFalse(holding["is_qdii"])
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        freshness, stale = assess_data_freshness(future)
        self.assertEqual(freshness, "invalid_future_time")
        self.assertTrue(stale)

    def test_demo_portfolio_matches_expected_total(self):
        holdings = get_demo_holdings()
        result = PortfolioAnalyzer().analyze(holdings)
        self.assertEqual(result["total_assets"], 86420.0)
        self.assertEqual(result["fund_count"], 3)
        self.assertIn("industry_concentration", result)
        self.assertIn("overseas_asset_ratio", result)
        self.assertEqual(result["risk_scope"], "结构风险")

    def test_rule_engine_and_context_keep_freshness(self):
        holding = get_demo_holdings()[0]
        holding["access_token"] = "must-not-reach-ai"
        analysis = FundAnalyzer().analyze(holding, nav_history=range(1, 31))
        portfolio = PortfolioAnalyzer().analyze([holding])
        context = build_analysis_context(
            portfolio_summary=portfolio,
            holdings=[holding],
            technical_signals=[analysis],
        )
        self.assertEqual(analysis["rule_version"], "fund-rules-v1")
        self.assertIn("stale_data", context)
        self.assertNotIn("access_token", context["holdings"][0])
        self.assertNotIn("must-not-reach-ai", str(context))
        self.assertTrue(set(ANALYSIS_HISTORY_FIELDS))

    def test_missing_history_does_not_produce_holding_advice(self):
        analysis = FundAnalyzer().analyze(get_demo_holdings()[0])
        self.assertFalse(analysis["historical_metrics_available"])
        self.assertEqual(analysis["risk_status"], "数据不足")
        self.assertEqual(analysis["recommendation"], "观察")

    def test_optional_integrations_default_to_safe_state(self):
        client = YangJiBaoClient(token="", account_id="")
        self.assertFalse(client.is_configured())
        with self.assertRaises(YangJiBaoError):
            client.get_holdings()
        copilot = AICopilot(api_key="", model="openrouter/free")
        self.assertIn("OPENROUTER_API_KEY", copilot.answer_question({}, "test")["error"])
        self.assertNotIn("api_key", copilot.configuration_status())

    def test_yangjibao_blocks_insecure_transport(self):
        class FailIfCalledSession:
            def get(self, *args, **kwargs):
                raise AssertionError("HTTP request should have been blocked")

        client = YangJiBaoClient(
            signing_secret="test-signing-material",
            base_url="http://example.com",
            session=FailIfCalledSession(),
        )
        self.assertFalse(client.uses_secure_transport())
        with self.assertRaises(YangJiBaoError):
            client.create_qr_login()

    def test_yangjibao_qr_and_accounts_are_sanitized(self):
        class FakeResponse:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, params, headers, timeout):
                self.calls.append((url, params, headers, timeout))
                if url.endswith("/qr_code"):
                    return FakeResponse(
                        {"code": 200, "data": {"id": "qr-123", "url": "yjb://login"}}
                    )
                if url.endswith("/qr_code_state/qr-123"):
                    return FakeResponse(
                        {"code": 200, "data": {"state": 2, "token": "private-token"}}
                    )
                if url.endswith("/fund_hold"):
                    self.last_holdings_params = params
                    return FakeResponse(
                        {
                            "code": 200,
                            "data": [
                                {
                                    "code": "000001",
                                    "short_name": "测试基金",
                                    "hold_share": "100.5",
                                    "hold_cost": "1.2",
                                    "money": "130.65",
                                    "hold_earn": "10.05",
                                    "cost_money": "120.60",
                                    "jzrq": "2026-08-31",
                                    "nv_info": {
                                        "dwjz": "1.3",
                                        "gsz": "1.31",
                                        "vgszzl": "1.5",
                                        "gztime": "2026-09-01T10:00:00+08:00",
                                    },
                                }
                            ],
                        }
                    )
                return FakeResponse(
                    {
                        "code": 200,
                        "data": {
                            "list": [
                                {"id": "account-1", "title": "长期账户", "count": 3}
                            ]
                        },
                    }
                )

        session = FakeSession()
        client = YangJiBaoClient(
            token="",
            signing_secret="test-signing-material",
            base_url="https://example.com",
            session=session,
        )
        challenge = client.create_qr_login()
        login = client.poll_qr_login(challenge["id"])
        authorized = YangJiBaoClient(
            token=login["token"],
            signing_secret="test-signing-material",
            base_url="https://example.com",
            session=session,
        )
        accounts = authorized.get_accounts()
        holdings = authorized.get_holdings("account-1")

        self.assertEqual(login["state"], "authorized")
        self.assertEqual(accounts[0]["display_name"], "长期账户")
        self.assertEqual(set(accounts[0]), {"account_id", "display_name", "holding_count"})
        self.assertNotIn("private-token", str(authorized.configuration_status()))
        self.assertEqual(session.last_holdings_params, {"account_id": "account-1"})
        self.assertEqual(holdings[0]["fund_code"], "000001")
        self.assertEqual(holdings[0]["source"], "yangjibao")
        self.assertEqual(holdings[0]["market_value"], 130.65)
        self.assertEqual(holdings[0]["latest_nav"], 1.3)
        self.assertEqual(holdings[0]["estimated_nav"], 1.31)
        self.assertAlmostEqual(holdings[0]["today_profit"], 1.95975)
        self.assertTrue(set(FUND_HOLDING_FIELDS).issubset(holdings[0]))
        self.assertNotIn("hold_share", holdings[0])


if __name__ == "__main__":
    unittest.main()
