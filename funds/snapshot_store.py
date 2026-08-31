"""Private persistence for normalized fund snapshots.

Only provider-neutral holdings are stored. YangJiBao tokens, cookies, QR login
state and raw provider responses must never enter this store.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

import requests

from funds.fund_adapter import FUND_HOLDING_FIELDS, normalize_fund_holdings


class FundSnapshotError(RuntimeError):
    """Safe persistence error that never includes credentials or holdings."""


def _is_safe_holding(value: Any) -> bool:
    if not isinstance(value, dict) or not set(FUND_HOLDING_FIELDS).issubset(value):
        return False
    forbidden_fragments = ("token", "cookie", "authorization", "account_id")
    return not any(
        fragment in str(key).lower()
        for key in value
        for fragment in forbidden_fragments
    )


def _is_fund_snapshot(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("schema_version") == 1
        and value.get("source") == "yangjibao"
        and isinstance(value.get("holdings"), list)
        and all(_is_safe_holding(item) for item in value["holdings"])
    )


class SupabaseFundSnapshotStore:
    """Store one normalized, read-only fund snapshot in the existing state table."""

    def __init__(
        self,
        project_url: str,
        secret_key: str,
        record_id: str = "primary-funds",
        *,
        timeout: float = 8.0,
        session: Any | None = None,
    ):
        self.project_url = str(project_url).strip().rstrip("/")
        self.secret_key = str(secret_key).strip()
        self.record_id = str(record_id).strip() or "primary-funds"
        self.timeout = max(3.0, min(float(timeout), 30.0))
        self.session = session or requests
        if not self.project_url.startswith("https://") or not self.secret_key:
            raise ValueError("Supabase fund snapshot configuration is incomplete")

    @property
    def endpoint(self) -> str:
        return f"{self.project_url}/rest/v1/stockpulse_state"

    def _headers(self, prefer: str = "") -> dict[str, str]:
        headers = {
            "apikey": self.secret_key,
            "Content-Type": "application/json",
        }
        if not self.secret_key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {self.secret_key}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def load(self) -> dict[str, Any] | None:
        try:
            response = self.session.get(
                self.endpoint,
                params={"id": f"eq.{self.record_id}", "select": "payload"},
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            rows = response.json()
        except Exception as exc:
            raise FundSnapshotError("读取基金云端快照失败，请稍后重试。") from exc

        if not rows:
            return None
        payload = rows[0].get("payload") if isinstance(rows[0], dict) else None
        if not _is_fund_snapshot(payload):
            raise FundSnapshotError("基金云端快照格式无效，已停止加载。")

        snapshot = copy.deepcopy(payload)
        snapshot["holdings"] = normalize_fund_holdings(
            snapshot["holdings"], source="yangjibao"
        )
        return snapshot

    def save(self, holdings: list[dict[str, Any]], updated_at: str = "") -> None:
        if not holdings or not all(_is_safe_holding(item) for item in holdings):
            raise FundSnapshotError("拒绝保存包含敏感字段或格式无效的基金快照。")
        safe_holdings = normalize_fund_holdings(holdings, source="yangjibao")
        if not all(_is_safe_holding(item) for item in safe_holdings):
            raise FundSnapshotError("拒绝保存空白或格式无效的基金快照。")

        payload = {
            "schema_version": 1,
            "source": "yangjibao",
            "updated_at": str(updated_at or "").strip()
            or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "holdings": copy.deepcopy(safe_holdings),
        }
        try:
            response = self.session.post(
                self.endpoint,
                params={"on_conflict": "id"},
                json={
                    "id": self.record_id,
                    "payload": payload,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                headers=self._headers("resolution=merge-duplicates,return=minimal"),
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            raise FundSnapshotError("保存基金云端快照失败，本次数据仍仅在当前会话可用。") from exc
