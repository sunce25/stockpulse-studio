"""Deterministic fund analysis. No LLM calls are permitted in this module."""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np


class FundAnalyzer:
    """Calculate auditable fund metrics and finite rule-based labels."""

    RULE_VERSION = "fund-rules-v1"

    def analyze(self, holding: dict, nav_history: Iterable[float] | None = None) -> dict:
        values = np.asarray(list(nav_history) if nav_history is not None else [], dtype=float)
        values = values[np.isfinite(values) & (values > 0)]

        max_drawdown = None
        volatility = None
        momentum = None
        ma_trend = "数据不足"
        if values.size >= 2:
            peaks = np.maximum.accumulate(values)
            max_drawdown = float(np.min(values / peaks - 1) * 100)
            returns = np.diff(values) / values[:-1]
            volatility = float(np.std(returns, ddof=1) * math.sqrt(252) * 100) if returns.size > 1 else 0.0
        if values.size >= 20:
            momentum = float((values[-1] / values[-20] - 1) * 100)
            ma20 = float(np.mean(values[-20:]))
            ma_trend = "上行" if values[-1] > ma20 else "下行"

        holding_return = float(holding.get("holding_return_pct", 0.0) or 0.0)
        volatility_component = min(100.0, (volatility or 20.0) * 2.0)
        drawdown_component = min(100.0, abs(max_drawdown or 0.0) * 3.0)
        stale_penalty = 20.0 if holding.get("stale_data") else 0.0
        qdii_penalty = 8.0 if holding.get("is_qdii") else 0.0
        risk_score = round(min(100.0, volatility_component * 0.5 + drawdown_component * 0.3 + stale_penalty + qdii_penalty))

        trend_score = 50
        if ma_trend == "上行":
            trend_score += 20
        elif ma_trend == "下行":
            trend_score -= 20
        if momentum is not None:
            trend_score += max(-20, min(20, round(momentum)))
        trend_score = max(0, min(100, trend_score))
        opportunity_score = max(0, min(100, round(trend_score * 0.7 + (100 - risk_score) * 0.3)))

        historical_metrics_available = values.size >= 2
        if holding.get("stale_data"):
            risk_status = "数据待更新"
            recommendation = "观察"
        elif not historical_metrics_available:
            risk_status = "数据不足"
            recommendation = "观察"
        elif risk_score >= 70:
            risk_status = "风险升高"
            recommendation = "仓位偏高" if holding.get("portfolio_weight", 0) >= 0.3 else "观察"
        elif trend_score >= 65:
            risk_status = "风险可控"
            recommendation = "小幅关注"
        else:
            risk_status = "中性"
            recommendation = "持有"

        return {
            "fund_code": holding.get("fund_code", ""),
            "holding_return_pct": holding_return,
            "max_drawdown_pct": max_drawdown,
            "volatility_pct": volatility,
            "ma_trend": ma_trend,
            "momentum_pct": momentum,
            "valuation_percentile": None,
            "risk_score": risk_score,
            "trend_score": trend_score,
            "opportunity_score": opportunity_score,
            "risk_status": risk_status,
            "recommendation": recommendation,
            "rule_version": self.RULE_VERSION,
            "stale_data": bool(holding.get("stale_data", True)),
            "historical_metrics_available": historical_metrics_available,
        }
