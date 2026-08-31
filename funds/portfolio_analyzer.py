"""Portfolio-level deterministic analytics for normalized holdings."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

import numpy as np


def _concentration_by(holdings: list[dict], field: str) -> dict:
    weights = defaultdict(float)
    for item in holdings:
        weights[str(item.get(field) or "未分类")] += float(item.get("portfolio_weight", 0.0))
    largest_name, largest_weight = max(weights.items(), key=lambda pair: pair[1], default=("", 0.0))
    return {
        "largest": {"name": largest_name, "weight": largest_weight},
        "score": round(sum(weight * weight for weight in weights.values()) * 100, 2),
        "breakdown": dict(weights),
    }


class PortfolioAnalyzer:
    """Aggregate objective portfolio metrics into JSON-serializable output."""

    RULE_VERSION = "portfolio-rules-v1"

    def analyze(
        self,
        holdings: Iterable[dict],
        portfolio_history: Iterable[float] | None = None,
    ) -> dict:
        items = [dict(item) for item in holdings]
        total_assets = sum(float(item.get("market_value", 0.0) or 0.0) for item in items)
        total_cost = sum(float(item.get("cost_amount", 0.0) or 0.0) for item in items)
        total_profit = total_assets - total_cost
        today_profit = sum(float(item.get("today_profit", 0.0) or 0.0) for item in items)

        for item in items:
            item["portfolio_weight"] = (
                float(item.get("market_value", 0.0) or 0.0) / total_assets
                if total_assets
                else 0.0
            )
        largest = max(items, key=lambda item: item["portfolio_weight"], default={})
        concentration_score = round(
            sum(item["portfolio_weight"] ** 2 for item in items) * 100, 2
        )
        industry = _concentration_by(items, "industry")
        theme = _concentration_by(items, "theme")

        overseas_ratio = sum(
            item["portfolio_weight"]
            for item in items
            if item.get("region") == "overseas" or item.get("is_qdii")
        )
        stock_ratio = sum(
            item["portfolio_weight"] for item in items if item.get("asset_type") == "stock"
        )
        fund_ratio = sum(
            item["portfolio_weight"] for item in items if item.get("asset_type") == "fund"
        )

        history = np.asarray(
            list(portfolio_history) if portfolio_history is not None else [], dtype=float
        )
        history = history[np.isfinite(history) & (history > 0)]
        max_drawdown = None
        volatility = None
        if history.size >= 2:
            max_drawdown = float(np.min(history / np.maximum.accumulate(history) - 1) * 100)
            returns = np.diff(history) / history[:-1]
            volatility = float(np.std(returns, ddof=1) * math.sqrt(252) * 100) if returns.size > 1 else 0.0

        stale_ratio = (
            sum(item["portfolio_weight"] for item in items if item.get("stale_data"))
            if items
            else 0.0
        )
        largest_weight = float(largest.get("portfolio_weight", 0.0) or 0.0)
        risk_score = round(
            min(
                100,
                largest_weight * 45
                + concentration_score * 0.35
                + stale_ratio * 20
                + min(20, (volatility or 0.0) * 0.5),
            )
        )

        return {
            "total_assets": round(total_assets, 2),
            "total_cost": round(total_cost, 2),
            "total_profit": round(total_profit, 2),
            "total_return_pct": round(total_profit / total_cost * 100, 2) if total_cost else 0.0,
            "today_profit": round(today_profit, 2),
            "fund_count": len(items),
            "largest_position": {
                "code": largest.get("fund_code", ""),
                "name": largest.get("fund_name", ""),
                "weight": largest_weight,
            },
            "max_single_position_weight": largest_weight,
            "concentration_score": concentration_score,
            "industry_concentration": industry,
            "theme_concentration": theme,
            "overseas_asset_ratio": overseas_ratio,
            "stock_asset_ratio": stock_ratio,
            "fund_asset_ratio": fund_ratio,
            "max_drawdown_pct": max_drawdown,
            "volatility_pct": volatility,
            "risk_score": risk_score,
            "risk_scope": "结构风险" if history.size < 2 else "结构与历史风险",
            "historical_metrics_available": history.size >= 2,
            "stale_data": any(item.get("stale_data") for item in items),
            "stale_asset_ratio": stale_ratio,
            "rule_version": self.RULE_VERSION,
        }
