"""Security boundary for the experimental, read-only YangJiBao connection.

Important security and compatibility notes:

1. YangJiBao does not currently document a stable public developer API.
2. The browser-plugin endpoints and response schemas may change without notice.
3. Tokens, cookies, account IDs and signing material must never enter Git.
4. Credentials must only come from environment variables or Streamlit Secrets.
5. All YangJiBao-specific requests and field mapping belong in this module.
6. UI, AI and analysis modules must never depend on raw provider fields.
7. This client intentionally implements login/account discovery only. Holdings
   remain disabled until the transport and returned schema are verified.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any
from urllib.parse import urlparse

from config.settings import get_setting


DEFAULT_BASE_URL = "https://browser-plug-api.yangjibao.com"


class YangJiBaoError(RuntimeError):
    """Safe user-facing provider error that never contains credentials."""


class YangJiBaoClient:
    """Minimal read-only client for login checks and account discovery."""

    def __init__(
        self,
        token: str | None = None,
        account_id: str | None = None,
        *,
        signing_secret: str | None = None,
        base_url: str | None = None,
        timeout: float = 12.0,
        session: Any | None = None,
    ):
        self._token = token if token is not None else get_setting("YANGJIBAO_TOKEN")
        self._account_id = account_id if account_id is not None else get_setting("YANGJIBAO_ACCOUNT_ID")
        self._signing_secret = signing_secret if signing_secret is not None else get_setting("YANGJIBAO_SIGNING_SECRET")
        configured_base = (
            base_url
            or get_setting("YANGJIBAO_BASE_URL")
            or DEFAULT_BASE_URL
        )
        self._base_url = configured_base.rstrip("/")
        self._timeout = max(3.0, min(float(timeout), 30.0))
        self._session = session
        if self._session is None:
            try:
                import requests

                session_factory = getattr(requests, "Session", None)
                self._session = session_factory() if session_factory else None
            except ImportError:
                self._session = None

    def is_configured(self) -> bool:
        """Return persistent credential status without exposing values."""
        return bool(self._token and self._account_id)

    def can_start_login(self) -> bool:
        """Return whether the safe login prerequisites are available."""
        return bool(self._signing_secret and self.uses_secure_transport())

    def uses_secure_transport(self) -> bool:
        """Reject endpoints that would send a login token over plain HTTP."""
        parsed = urlparse(self._base_url)
        return parsed.scheme.lower() == "https" and bool(parsed.netloc)

    def configuration_status(self) -> dict[str, bool]:
        """Expose booleans only; never return configuration contents."""
        return {
            "token_configured": bool(self._token),
            "account_configured": bool(self._account_id),
            "signing_configured": bool(self._signing_secret),
            "secure_transport": self.uses_secure_transport(),
        }

    def _signature(self, path: str, timestamp: int, token: str) -> str:
        if not self._signing_secret:
            raise YangJiBaoError("养基宝连接参数未配置完整。")
        sign_path = path.split("?", 1)[0]
        payload = f"{sign_path}{token}{timestamp}{self._signing_secret}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()  # noqa: S324

    def _request(self, path: str, *, token: str | None = None, params: dict[str, Any] | None = None) -> Any:
        if not self.uses_secure_transport():
            raise YangJiBaoError("已阻止非 HTTPS 的养基宝连接。")
        if not path.startswith("/"):
            raise YangJiBaoError("养基宝请求路径无效。")
        if self._session is None:
            raise YangJiBaoError("养基宝网络组件尚未安装。")

        request_token = self._token if token is None else token
        timestamp = int(time.time())
        headers = {
            "Accept": "application/json",
            "Authorization": request_token or "",
            "Request-Time": str(timestamp),
            "Request-Sign": self._signature(path, timestamp, request_token or ""),
        }
        try:
            response = self._session.get(
                f"{self._base_url}{path}",
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except ValueError as exc:
            raise YangJiBaoError("养基宝返回了无法识别的数据。") from exc
        except Exception as exc:
            if exc.__class__.__name__ in {"Timeout", "ConnectTimeout", "ReadTimeout"}:
                raise YangJiBaoError("养基宝连接超时，请稍后重试。") from exc
            raise YangJiBaoError("养基宝连接失败，接口可能暂时不可用。") from exc

        if not isinstance(payload, dict):
            raise YangJiBaoError("养基宝返回的数据格式异常。")
        code = payload.get("code")
        if code not in (None, 0, 200, "0", "200"):
            raise YangJiBaoError("养基宝拒绝了本次请求，请重新授权。")
        return payload.get("data", payload)

    def create_qr_login(self) -> dict[str, str]:
        """Create a short-lived QR login challenge without persisting data."""
        data = self._request("/qr_code", token="")
        if not isinstance(data, dict):
            raise YangJiBaoError("养基宝二维码数据格式异常。")
        qr_id = str(data.get("id") or "").strip()
        qr_url = str(data.get("url") or "").strip()
        if not qr_id or not qr_url:
            raise YangJiBaoError("养基宝没有返回有效的登录二维码。")
        return {"id": qr_id, "url": qr_url}

    def poll_qr_login(self, qr_id: str) -> dict[str, str]:
        """Check one QR challenge; the returned token must stay server-side."""
        safe_qr_id = str(qr_id or "").strip()
        if not safe_qr_id or not safe_qr_id.replace("-", "").isalnum():
            raise YangJiBaoError("养基宝登录会话无效，请重新生成二维码。")
        data = self._request(f"/qr_code_state/{safe_qr_id}", token="")
        if not isinstance(data, dict):
            raise YangJiBaoError("养基宝登录状态格式异常。")

        raw_state = str(data.get("state", "")).strip()
        token = str(data.get("token") or "").strip()
        if raw_state == "2" and token:
            return {"state": "authorized", "token": token}
        if raw_state in {"0", "1", ""}:
            return {"state": "pending", "token": ""}
        return {"state": "expired", "token": ""}

    def get_accounts(self) -> list[dict[str, Any]]:
        """Return sanitized account metadata; raw provider JSON stays private."""
        if not self._token:
            raise YangJiBaoError("尚未完成养基宝授权。")
        data = self._request("/user_account")
        raw_accounts = data.get("list", []) if isinstance(data, dict) else data
        if not isinstance(raw_accounts, list):
            raise YangJiBaoError("养基宝账户列表格式异常。")

        accounts: list[dict[str, Any]] = []
        for index, item in enumerate(raw_accounts):
            if not isinstance(item, dict):
                continue
            account_id = str(item.get("id") or "").strip()
            if not account_id:
                continue
            try:
                holding_count = max(0, int(item.get("count") or 0))
            except (TypeError, ValueError):
                holding_count = 0
            accounts.append(
                {
                    "account_id": account_id,
                    "display_name": str(item.get("title") or item.get("name") or f"基金账户 {index + 1}").strip(),
                    "holding_count": holding_count,
                }
            )
        return accounts

    def get_holdings(self):
        """Remain disabled until the read-only connection is verified safely."""
        raise NotImplementedError("养基宝持仓同步尚未启用；当前仅验证登录和账户列表。")
