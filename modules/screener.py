# -*- coding: utf-8 -*-
"""
Multi-Dimensional Stock Screener & Technical Filter for StockPulse Studio.
Filters A-shares, US stocks, and ETFs by fundamental & technical criteria.
"""
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
from modules.data_adapter import DataAdapter
from modules.indicators import add_all_indicators


class StockScreener:
    def __init__(self, data_adapter: DataAdapter = None):
        self.adapter = data_adapter or DataAdapter()

    def screen(
        self,
        market_type: str = "A股",
        preset_strategy: str = "全部候选",
        min_price: float = 0.0,
        max_price: float = 9999.0,
        min_pct_chg: float = -20.0,
        max_pct_chg: float = 20.0,
        min_pe: float = 0.0,
        max_pe: float = 500.0,
        min_mktcap: float = 0.0,
        limit_pool_size: int = 80
    ) -> pd.DataFrame:
        """
        根据设定条件和预置策略筛选股票
        """
        # 1. 获取基础候选池
        df_pool = self.adapter.get_market_spot_pool(market_type=market_type, top_n=limit_pool_size)
        if df_pool is None or df_pool.empty:
            return pd.DataFrame()

        # 确保关键列存在并进行数值转换
        for col in ["price", "pct_chg", "change", "pe", "pb", "mktcap", "turnover", "volume"]:
            if col in df_pool.columns:
                df_pool[col] = pd.to_numeric(df_pool[col], errors="coerce").fillna(0.0)
            else:
                df_pool[col] = 0.0

        # 2. 基础财务与行情区间过滤
        cond = (
            (df_pool["price"] >= min_price) &
            (df_pool["price"] <= max_price) &
            (df_pool["pct_chg"] >= min_pct_chg) &
            (df_pool["pct_chg"] <= max_pct_chg)
        )
        if max_pe < 500:
            cond = cond & (df_pool["pe"] >= min_pe) & (df_pool["pe"] <= max_pe)
        if min_mktcap > 0 and "mktcap" in df_pool.columns:
            cond = cond & (df_pool["mktcap"] >= min_mktcap)

        filtered_df = df_pool[cond].copy()
        if filtered_df.empty:
            return pd.DataFrame()

        # 3. 策略/技术形态二次扫描
        if preset_strategy in {"均线多头精选", "MACD金叉反弹", "放量突破"}:
            candidates = filtered_df.head(25)["symbol"].astype(str).tolist()
            matched_symbols = self._scan_technical_strategy(
                candidates, market_type, preset_strategy
            )
            filtered_df = filtered_df[filtered_df["symbol"].isin(matched_symbols)]

        elif preset_strategy == "低估值蓝筹":
            filtered_df = filtered_df[(filtered_df["pe"] > 0) & (filtered_df["pe"] <= 20) & (filtered_df["mktcap"] >= 300)]

        # 排序
        filtered_df = filtered_df.sort_values(by="pct_chg", ascending=False).reset_index(drop=True)
        return filtered_df

    def _scan_technical_strategy(
        self, symbols: list[str], market_type: str, strategy: str
    ) -> list[str]:
        """Scan independent symbols concurrently with a conservative worker cap."""
        if not symbols:
            return []

        def matches(symbol: str) -> bool:
            limit = 20 if strategy == "放量突破" else 30
            try:
                k_df = self.adapter.get_kline_data(
                    symbol, market=market_type, limit=limit
                )
                minimum_rows = 10 if strategy == "放量突破" else 20
                if k_df is None or len(k_df) < minimum_rows:
                    return False
                k_df = add_all_indicators(k_df)
                latest = k_df.iloc[-1]
                if strategy == "均线多头精选":
                    return bool(
                        latest["close"]
                        > latest["MA_5"]
                        > latest["MA_10"]
                        > latest["MA_20"]
                    )
                if strategy == "MACD金叉反弹":
                    prev = k_df.iloc[-2]
                    return bool(
                        prev["MACD_DIF"] <= prev["MACD_DEA"]
                        and latest["MACD_DIF"] > latest["MACD_DEA"]
                    )
                vol_5 = float(latest.get("VOL_MA_5", 0.0) or 0.0)
                return bool(
                    vol_5 > 0
                    and latest["volume"] / vol_5 >= 1.7
                    and latest["close"] > latest["open"]
                )
            except (KeyError, TypeError, ValueError, IndexError):
                return False

        matched = set()
        with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as executor:
            futures = {executor.submit(matches, symbol): symbol for symbol in symbols}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    if future.result():
                        matched.add(symbol)
                except Exception:
                    continue
        return [symbol for symbol in symbols if symbol in matched]

    def export_to_excel(self, df: pd.DataFrame) -> bytes:
        """导出筛选结果为 Excel 二进制字节流"""
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="选股结果")
        return output.getvalue()

    def export_to_csv(self, df: pd.DataFrame) -> str:
        """导出为 CSV 文本"""
        return df.to_csv(index=False, encoding="utf-8-sig")
