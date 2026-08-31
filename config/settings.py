"""Safe configuration access for local and Streamlit Cloud deployments.

Environment variables take precedence over Streamlit Secrets. Missing values
always fall back to the supplied default so optional integrations never prevent
the application from starting.
"""

from __future__ import annotations

import os
from typing import Any


def _streamlit_secret(name: str, default: Any = "") -> Any:
    """Read one Streamlit secret without requiring Streamlit or a secrets file."""
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:
        return default


def get_setting(name: str, default: Any = "") -> str:
    """Return a normalized setting without logging or exposing its value."""
    environment_value = os.getenv(name)
    if environment_value is not None and str(environment_value).strip():
        return str(environment_value).strip()

    secret_value = _streamlit_secret(name, default)
    if secret_value is None:
        return str(default or "").strip()
    return str(secret_value).strip()


def is_configured(name: str) -> bool:
    """Report whether a setting exists without returning the sensitive value."""
    return bool(get_setting(name))
