"""Isolated boundary for a possible future YangJiBao integration.

Important security and compatibility notes:

1. YangJiBao may not provide a stable, official public developer API.
2. Any private endpoint or response schema may change without notice.
3. Tokens and cookies are credentials and must never be committed to GitHub.
4. Credentials must only come from environment variables or Streamlit Secrets.
5. All YangJiBao-specific request and field-mapping logic belongs in this file.
6. UI, AI, and analysis modules must consume normalized StockPulse holdings,
   never raw YangJiBao response fields.

This release intentionally performs no network requests.
"""

from __future__ import annotations

from config.settings import get_setting


class YangJiBaoClient:
    """Placeholder client that keeps future provider details behind one boundary."""

    def __init__(self, token: str | None = None, account_id: str | None = None):
        self._token = token if token is not None else get_setting("YANGJIBAO_TOKEN")
        self._account_id = (
            account_id
            if account_id is not None
            else get_setting("YANGJIBAO_ACCOUNT_ID")
        )

    def is_configured(self) -> bool:
        """Return configuration status without exposing credential contents."""
        return bool(self._token and self._account_id)

    def get_holdings(self):
        """Fetch holdings after an official/stable integration is implemented."""
        raise NotImplementedError("养基宝数据连接尚未启用；当前版本不会发起网络请求。")
