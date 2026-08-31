"""Build LLM-ready structured context from completed Python analysis results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


ANALYSIS_HISTORY_FIELDS = (
    "timestamp",
    "asset",
    "portfolio_snapshot",
    "rule_version",
    "risk_score",
    "technical_score",
    "recommendation",
    "llm_provider",
    "llm_model",
    "ai_explanation",
)


def build_analysis_context(
    *,
    portfolio_summary: dict | None = None,
    holdings: list[dict] | None = None,
    technical_signals: list[dict] | None = None,
    risk_summary: dict | None = None,
    market_context: dict | None = None,
    user_question: str = "",
) -> dict[str, Any]:
    """Assemble facts already computed by deterministic application modules."""
    normalized_holdings = [dict(item) for item in (holdings or [])]
    sources_stale = any(item.get("stale_data", False) for item in normalized_holdings)
    portfolio = dict(portfolio_summary or {})
    risk = dict(risk_summary or {})
    market = dict(market_context or {})
    stale_data = bool(
        sources_stale
        or portfolio.get("stale_data", False)
        or risk.get("stale_data", False)
        or market.get("stale_data", False)
    )
    updated_times = [
        str(item.get("updated_at"))
        for item in normalized_holdings
        if item.get("updated_at")
    ]
    return {
        "context_version": "stockpulse-context-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "data_updated_at": max(updated_times, default=""),
        "stale_data": stale_data,
        "portfolio_summary": portfolio,
        "holdings": normalized_holdings,
        "technical_signals": list(technical_signals or []),
        "risk_summary": risk,
        "market_context": market,
        "user_question": str(user_question or "").strip(),
        "instructions": {
            "objective_metrics_are_read_only": True,
            "auto_trading_allowed": False,
            "data_gap_response": "数据不足",
        },
    }


def build_analysis_history_record(
    *,
    asset: str = "portfolio",
    portfolio_snapshot: dict | None = None,
    rule_version: str = "",
    risk_score: float | None = None,
    technical_score: float | None = None,
    recommendation: str = "观察",
    llm_provider: str = "",
    llm_model: str = "",
    ai_explanation: str = "",
) -> dict[str, Any]:
    """Create the audit record shape; persistence is intentionally deferred."""
    return {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "asset": asset,
        "portfolio_snapshot": dict(portfolio_snapshot or {}),
        "rule_version": rule_version,
        "risk_score": risk_score,
        "technical_score": technical_score,
        "recommendation": recommendation,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "ai_explanation": ai_explanation,
    }
