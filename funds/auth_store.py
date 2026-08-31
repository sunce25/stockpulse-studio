"""Encrypted server-side persistence for YangJiBao read-only authorization."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class YangJiBaoAuthStoreError(RuntimeError):
    """Safe error that never exposes encryption material or credentials."""


class SupabaseYangJiBaoAuthStore:
    """Encrypt a minimal read-only authorization before writing to Supabase."""

    def __init__(
        self,
        project_url: str,
        secret_key: str,
        encryption_material: str,
        record_id: str = "primary-yangjibao-auth",
        *,
        timeout: float = 8.0,
        session: Any | None = None,
    ):
        import requests

        self.project_url = str(project_url).strip().rstrip("/")
        self.secret_key = str(secret_key).strip()
        self.record_id = str(record_id).strip() or "primary-yangjibao-auth"
        self.timeout = max(3.0, min(float(timeout), 30.0))
        self.session = session or requests
        if (
            not self.project_url.startswith("https://")
            or not self.secret_key
            or not str(encryption_material)
        ):
            raise ValueError("YangJiBao authorization persistence is not configured")
        digest = hashlib.sha256(
            ("stockpulse:yangjibao-auth:v1\0" + str(encryption_material)).encode(
                "utf-8"
            )
        ).digest()
        self._cipher = Fernet(base64.urlsafe_b64encode(digest))

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
            raise YangJiBaoAuthStoreError("读取养基宝加密授权失败。") from exc
        if not rows:
            return None
        payload = rows[0].get("payload") if isinstance(rows[0], dict) else None
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise YangJiBaoAuthStoreError("养基宝加密授权格式无效。")
        ciphertext = str(payload.get("ciphertext") or "")
        try:
            credentials = json.loads(self._cipher.decrypt(ciphertext.encode()).decode())
        except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise YangJiBaoAuthStoreError("养基宝加密授权无法解密，请重新扫码。") from exc
        if not isinstance(credentials, dict):
            raise YangJiBaoAuthStoreError("养基宝加密授权内容无效。")
        token = str(credentials.get("token") or "").strip()
        account_id = str(credentials.get("account_id") or "").strip()
        if not token or not account_id:
            raise YangJiBaoAuthStoreError("养基宝加密授权不完整，请重新扫码。")
        return {
            "token": token,
            "account_id": account_id,
            "display_name": str(credentials.get("display_name") or "基金账户"),
            "holding_count": max(0, int(credentials.get("holding_count") or 0)),
        }

    def save(
        self,
        token: str,
        account_id: str,
        display_name: str = "基金账户",
        holding_count: int = 0,
    ) -> None:
        safe_token = str(token or "").strip()
        safe_account_id = str(account_id or "").strip()
        if not safe_token or not safe_account_id:
            raise YangJiBaoAuthStoreError("拒绝保存空白养基宝授权。")
        plaintext = json.dumps(
            {
                "token": safe_token,
                "account_id": safe_account_id,
                "display_name": str(display_name or "基金账户"),
                "holding_count": max(0, int(holding_count or 0)),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        payload = {
            "schema_version": 1,
            "ciphertext": self._cipher.encrypt(plaintext).decode(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
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
            raise YangJiBaoAuthStoreError("保存养基宝加密授权失败。") from exc

    def delete(self) -> None:
        try:
            response = self.session.delete(
                self.endpoint,
                params={"id": f"eq.{self.record_id}"},
                headers=self._headers("return=minimal"),
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            raise YangJiBaoAuthStoreError("删除养基宝加密授权失败。") from exc

