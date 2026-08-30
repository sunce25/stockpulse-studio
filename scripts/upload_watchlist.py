# -*- coding: utf-8 -*-
"""Upload the current local watchlist document to the configured Supabase row."""

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.cloud_storage import SupabaseJsonStore  # noqa: E402


def load_local_secrets() -> dict:
    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return {}
    with secrets_path.open("rb") as secrets_file:
        return tomllib.load(secrets_file)


def get_setting(name: str, secrets: dict, default: str = "") -> str:
    return str(os.getenv(name) or secrets.get(name) or default).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload StockPulse watchlist to Supabase")
    parser.add_argument(
        "--data-file",
        type=Path,
        default=PROJECT_ROOT / "data" / "watchlist.json",
        help="Path to the local watchlist JSON file",
    )
    args = parser.parse_args()

    secrets = load_local_secrets()
    project_url = get_setting("SUPABASE_URL", secrets)
    secret_key = get_setting("SUPABASE_SECRET_KEY", secrets)
    record_id = get_setting("WATCHLIST_RECORD_ID", secrets, "primary")
    if not project_url or not secret_key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SECRET_KEY")

    with args.data_file.resolve().open(encoding="utf-8") as data_file:
        payload = json.load(data_file)

    SupabaseJsonStore(project_url, secret_key, record_id=record_id).save(payload)
    print(f"Uploaded {len(payload.get('items', []))} watchlist items to record '{record_id}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
