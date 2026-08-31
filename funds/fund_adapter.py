"""Normalize fund holdings from any provider into StockPulse's internal model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


FUND_HOLDING_FIELDS = (
    "fund_code",
    "fund_name",
    "market_value",
    "cost_amount",
    "shares",
    "cost_nav",
    "latest_nav",
    "estimated_nav",
    "holding_return_pct",
    "holding_profit",
    "portfolio_weight",
    "source",
    "updated_at",
    "nav_date",
    "estimated_nav_time",
    "market_timezone",
    "is_qdii",
    "data_freshness",
    "stale_data",
)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _boolean(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "是"}:
        return True
    if normalized in {"false", "0", "no", "n", "否"}:
        return False
    return default


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def assess_data_freshness(
    updated_at: Any,
    *,
    is_qdii: bool = False,
    now: datetime | None = None,
) -> tuple[str, bool]:
    """Classify freshness with a wider delay window for QDII/overseas funds."""
    timestamp = _parse_time(updated_at)
    if timestamp is None:
        return "unknown", True
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    age_seconds = (
        reference.astimezone(timezone.utc) - timestamp
    ).total_seconds()
    if age_seconds < -300:
        return "invalid_future_time", True
    max_age_hours = 72 if is_qdii else 36
    is_stale = age_seconds > (max_age_hours * 3600)
    return ("stale" if is_stale else "fresh"), is_stale


def normalize_fund_holding(raw: dict[str, Any], source: str = "unknown") -> dict[str, Any]:
    """Convert provider-neutral input to the stable internal holding schema."""
    shares = _number(raw.get("shares"))
    latest_nav = _number(raw.get("latest_nav"))
    cost_nav = _number(raw.get("cost_nav"))
    market_value = _number(raw.get("market_value"), shares * latest_nav)
    cost_amount = _number(raw.get("cost_amount"), shares * cost_nav)
    holding_profit = _number(raw.get("holding_profit"), market_value - cost_amount)
    calculated_return = (holding_profit / cost_amount * 100) if cost_amount else 0.0
    updated_at = str(raw.get("updated_at") or raw.get("nav_date") or "")
    nav_date = str(raw.get("nav_date") or "")
    is_qdii = _boolean(raw.get("is_qdii"), False)
    freshness_reference = raw.get("freshness_reference") or nav_date or updated_at
    freshness, stale_data = assess_data_freshness(
        freshness_reference, is_qdii=is_qdii
    )

    return {
        "fund_code": str(raw.get("fund_code", "")).strip(),
        "fund_name": str(raw.get("fund_name", "")).strip(),
        "market_value": round(market_value, 2),
        "cost_amount": round(cost_amount, 2),
        "shares": shares,
        "cost_nav": cost_nav,
        "latest_nav": latest_nav,
        "estimated_nav": (
            None if raw.get("estimated_nav") in (None, "") else _number(raw.get("estimated_nav"))
        ),
        "holding_return_pct": _number(raw.get("holding_return_pct"), calculated_return),
        "holding_profit": round(holding_profit, 2),
        "portfolio_weight": _number(raw.get("portfolio_weight")),
        "source": str(raw.get("source") or source),
        "updated_at": updated_at,
        "nav_date": nav_date,
        "estimated_nav_time": str(raw.get("estimated_nav_time") or ""),
        "market_timezone": str(raw.get("market_timezone") or "Asia/Shanghai"),
        "is_qdii": is_qdii,
        "data_freshness": str(raw.get("data_freshness") or freshness),
        "stale_data": _boolean(raw.get("stale_data"), stale_data),
        # Optional normalized dimensions used by portfolio risk aggregation.
        "asset_type": str(raw.get("asset_type") or "fund"),
        "industry": str(raw.get("industry") or "未分类"),
        "theme": str(raw.get("theme") or "未分类"),
        "region": str(raw.get("region") or ("overseas" if is_qdii else "china")),
        "today_profit": _number(raw.get("today_profit")),
    }


def normalize_fund_holdings(
    records: Iterable[dict[str, Any]], source: str = "unknown"
) -> list[dict[str, Any]]:
    """Normalize a portfolio and calculate weights from normalized market value."""
    holdings = [normalize_fund_holding(item, source=source) for item in records]
    total_value = sum(max(0.0, item["market_value"]) for item in holdings)
    for item in holdings:
        item["portfolio_weight"] = (
            item["market_value"] / total_value if total_value else 0.0
        )
    return holdings


def get_demo_holdings() -> list[dict[str, Any]]:
    """Return clearly synthetic holdings for the unconnected fund page."""
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    demo = [
        {
            "fund_code": "DEMO001",
            "fund_name": "示例·宽基指数基金",
            "market_value": 36000,
            "cost_amount": 33000,
            "shares": 22000,
            "cost_nav": 1.50,
            "latest_nav": 1.6364,
            "today_profit": 128,
            "industry": "宽基",
            "theme": "核心资产",
            "updated_at": timestamp,
            "nav_date": timestamp[:10],
        },
        {
            "fund_code": "DEMO002",
            "fund_name": "示例·科技主题基金",
            "market_value": 27800,
            "cost_amount": 25500,
            "shares": 12500,
            "cost_nav": 2.04,
            "latest_nav": 2.224,
            "today_profit": -86,
            "industry": "科技",
            "theme": "半导体",
            "updated_at": timestamp,
            "nav_date": timestamp[:10],
        },
        {
            "fund_code": "DEMO003",
            "fund_name": "示例·海外指数 QDII",
            "market_value": 22620,
            "cost_amount": 21100,
            "shares": 14000,
            "cost_nav": 1.5071,
            "latest_nav": 1.6157,
            "estimated_nav": 1.621,
            "estimated_nav_time": timestamp,
            "today_profit": 62,
            "industry": "宽基",
            "theme": "海外指数",
            "is_qdii": True,
            "region": "overseas",
            "market_timezone": "America/New_York",
            "updated_at": timestamp,
            "nav_date": timestamp[:10],
        },
    ]
    return normalize_fund_holdings(demo, source="demo")
