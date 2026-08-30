# -*- coding: utf-8 -*-
"""Optional Supabase persistence for watchlist and portfolio data."""

import copy
import time
from datetime import datetime, timezone
from typing import Dict, Optional

import requests

from modules.watchlist import WatchlistManager


class CloudStorageError(RuntimeError):
    """Raised when the remote portfolio store cannot be read or written."""


def _is_watchlist_document(value) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("groups"), list)
        and isinstance(value.get("items"), list)
    )


class SupabaseJsonStore:
    """Store one complete watchlist document in a Supabase JSONB row."""

    def __init__(
        self,
        project_url: str,
        secret_key: str,
        record_id: str = "primary",
        timeout: float = 8.0,
        session=None,
    ):
        self.project_url = str(project_url).strip().rstrip("/")
        self.secret_key = str(secret_key).strip()
        self.record_id = str(record_id).strip() or "primary"
        self.timeout = float(timeout)
        self.session = session or requests
        if not self.project_url or not self.secret_key:
            raise ValueError("Supabase URL and secret key are required")

    @property
    def endpoint(self) -> str:
        return f"{self.project_url}/rest/v1/stockpulse_state"

    def _headers(self, prefer: str = "") -> Dict[str, str]:
        headers = {
            "apikey": self.secret_key,
            "Content-Type": "application/json",
        }
        # Legacy service_role keys are JWTs and still require the Bearer header.
        # New sb_secret_* keys should only be sent through the apikey header.
        if not self.secret_key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {self.secret_key}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def load(self) -> Optional[Dict]:
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
            raise CloudStorageError(f"读取云端持仓失败：{exc}") from exc

        if not rows:
            return None
        payload = rows[0].get("payload") if isinstance(rows[0], dict) else None
        if not _is_watchlist_document(payload):
            raise CloudStorageError("云端持仓数据格式无效")
        return copy.deepcopy(payload)

    def save(self, payload: Dict) -> None:
        if not _is_watchlist_document(payload):
            raise CloudStorageError("拒绝写入格式无效的持仓数据")
        body = {
            "id": self.record_id,
            "payload": copy.deepcopy(payload),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            response = self.session.post(
                self.endpoint,
                params={"on_conflict": "id"},
                json=body,
                headers=self._headers("resolution=merge-duplicates,return=minimal"),
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            raise CloudStorageError(f"保存云端持仓失败：{exc}") from exc


class CloudBackedWatchlistManager(WatchlistManager):
    """Use Supabase as primary storage and keep the local JSON as a cache."""

    def __init__(
        self,
        data_file: str = None,
        project_url: str = "",
        secret_key: str = "",
        record_id: str = "primary",
        refresh_interval: float = 1.5,
        session=None,
    ):
        self.remote_store = SupabaseJsonStore(
            project_url=project_url,
            secret_key=secret_key,
            record_id=record_id,
            session=session,
        )
        self.refresh_interval = max(0.0, float(refresh_interval))
        self.last_remote_sync = 0.0
        self.remote_error = ""
        self.persistence_mode = "cloud"
        super().__init__(data_file=data_file)
        self._sync_from_cloud(seed=copy.deepcopy(self.data))

    def _save_local_cache(self) -> None:
        WatchlistManager.save(self)

    def _sync_from_cloud(self, seed: Dict) -> Dict:
        try:
            cloud_data = self.remote_store.load()
            if cloud_data is None:
                self.remote_store.save(seed)
                self.data = copy.deepcopy(seed)
            else:
                self.data = cloud_data
                self._save_local_cache()
            self.remote_error = ""
        except CloudStorageError as exc:
            self.remote_error = str(exc)
            self.data = copy.deepcopy(seed)
        self.last_remote_sync = time.monotonic()
        return self.data

    def reload(self) -> Dict:
        if time.monotonic() - self.last_remote_sync < self.refresh_interval:
            return self.data
        return self._sync_from_cloud(seed=copy.deepcopy(self.data))

    def save(self):
        self._save_local_cache()
        try:
            self.remote_store.save(self.data)
            self.remote_error = ""
            self.last_remote_sync = time.monotonic()
        except CloudStorageError as exc:
            self.remote_error = str(exc)


def create_watchlist_manager(
    data_file: str = None,
    supabase_url: str = "",
    supabase_secret_key: str = "",
    record_id: str = "primary",
):
    """Create a cloud manager only when both Supabase settings are present."""
    if str(supabase_url).strip() and str(supabase_secret_key).strip():
        return CloudBackedWatchlistManager(
            data_file=data_file,
            project_url=supabase_url,
            secret_key=supabase_secret_key,
            record_id=record_id,
        )
    manager = WatchlistManager(data_file=data_file)
    manager.persistence_mode = "local"
    manager.remote_error = ""
    return manager
