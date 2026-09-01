"""Provider-neutral fund snapshot comparison and audit summaries.

The audit record intentionally excludes account identifiers, credentials and raw
provider payloads. It records only normalized portfolio totals and position
changes so recurring investments can be distinguished from market movements.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


AUDIT_HISTORY_LIMIT = 90
_CHANGE_TOLERANCE = 1e-6


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _totals(holdings: Iterable[dict[str, Any]]) -> dict[str, float | int]:
    items = list(holdings)
    return {
        "fund_count": len(items),
        "total_assets": round(sum(_number(item.get("market_value")) for item in items), 2),
        "total_cost": round(sum(_number(item.get("cost_amount")) for item in items), 2),
        "total_profit": round(sum(_number(item.get("holding_profit")) for item in items), 2),
    }


def _changed(value: float) -> bool:
    return abs(value) > _CHANGE_TOLERANCE


def build_sync_record(
    previous: Iterable[dict[str, Any]] | None,
    current: Iterable[dict[str, Any]],
    synced_at: str = "",
) -> dict[str, Any]:
    """Build a safe, compact audit record for one successful synchronization."""
    old_items = list(previous or [])
    new_items = list(current)
    old_by_code = {str(item.get("fund_code") or ""): item for item in old_items}
    new_by_code = {str(item.get("fund_code") or ""): item for item in new_items}
    changes: list[dict[str, Any]] = []

    for code in sorted(set(old_by_code) | set(new_by_code)):
        old = old_by_code.get(code)
        new = new_by_code.get(code)
        reference = new or old or {}
        shares_delta = _number((new or {}).get("shares")) - _number((old or {}).get("shares"))
        cost_delta = _number((new or {}).get("cost_amount")) - _number((old or {}).get("cost_amount"))
        value_delta = _number((new or {}).get("market_value")) - _number((old or {}).get("market_value"))

        if old is None:
            change_type = "新增基金"
        elif new is None:
            change_type = "基金移除"
        elif _changed(shares_delta):
            change_type = "份额增加" if shares_delta > 0 else "份额减少"
        elif _changed(cost_delta):
            change_type = "成本变化"
        elif _changed(value_delta):
            change_type = "估值变化"
        else:
            continue

        changes.append(
            {
                "fund_code": code,
                "fund_name": str(reference.get("fund_name") or code),
                "change_type": change_type,
                "shares_delta": round(shares_delta, 6),
                "cost_amount_delta": round(cost_delta, 2),
                "market_value_delta": round(value_delta, 2),
                "investment_change": change_type
                in {"新增基金", "基金移除", "份额增加", "份额减少", "成本变化"},
            }
        )

    old_totals = _totals(old_items)
    new_totals = _totals(new_items)
    timestamp = str(synced_at or "").strip() or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()
    investment_changes = sum(bool(item["investment_change"]) for item in changes)
    return {
        "timestamp": timestamp,
        "status": "success",
        **new_totals,
        "asset_change": round(
            float(new_totals["total_assets"]) - float(old_totals["total_assets"]), 2
        ),
        "cost_change": round(
            float(new_totals["total_cost"]) - float(old_totals["total_cost"]), 2
        ),
        "changed_fund_count": len(changes),
        "investment_change_count": investment_changes,
        "changes": changes,
    }


def sanitize_sync_record(record: dict[str, Any]) -> dict[str, Any]:
    """Whitelist audit fields when restoring records from private persistence."""
    raw_changes = record.get("changes", [])
    changes = []
    if isinstance(raw_changes, list):
        for item in raw_changes:
            if not isinstance(item, dict):
                continue
            changes.append(
                {
                    "fund_code": str(item.get("fund_code") or ""),
                    "fund_name": str(item.get("fund_name") or ""),
                    "change_type": str(item.get("change_type") or ""),
                    "shares_delta": round(_number(item.get("shares_delta")), 6),
                    "cost_amount_delta": round(_number(item.get("cost_amount_delta")), 2),
                    "market_value_delta": round(_number(item.get("market_value_delta")), 2),
                    "investment_change": bool(item.get("investment_change")),
                }
            )
    return {
        "timestamp": str(record.get("timestamp") or ""),
        "status": "success" if record.get("status") == "success" else "failed",
        "fund_count": max(0, int(_number(record.get("fund_count")))),
        "total_assets": round(_number(record.get("total_assets")), 2),
        "total_cost": round(_number(record.get("total_cost")), 2),
        "total_profit": round(_number(record.get("total_profit")), 2),
        "asset_change": round(_number(record.get("asset_change")), 2),
        "cost_change": round(_number(record.get("cost_change")), 2),
        "changed_fund_count": max(0, int(_number(record.get("changed_fund_count")))),
        "investment_change_count": max(
            0, int(_number(record.get("investment_change_count")))
        ),
        "changes": changes,
    }


def sanitize_sync_history(
    history: Iterable[dict[str, Any]] | None,
    limit: int = AUDIT_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    """Restore only bounded, whitelisted audit data."""
    return [
        sanitize_sync_record(item)
        for item in (history or [])
        if isinstance(item, dict)
    ][: max(1, int(limit))]


def append_sync_history(
    history: Iterable[dict[str, Any]] | None,
    record: dict[str, Any],
    limit: int = AUDIT_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    """Append one audit record while keeping bounded newest-first history."""
    items = sanitize_sync_history(history, limit=limit)
    safe_record = sanitize_sync_record(record)
    if items and items[0].get("timestamp") == safe_record.get("timestamp"):
        items[0] = safe_record
    else:
        items.insert(0, safe_record)
    return items[: max(1, int(limit))]
