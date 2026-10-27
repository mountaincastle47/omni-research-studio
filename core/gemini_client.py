"""Gemini client interface with thread-local database telemetry management."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional, Union

from core.database import DB_PATH, get_app_data_dir, get_db_connection

_local = threading.local()
DEFAULT_GEMINI_DB = str(get_app_data_dir() / "gemini_telemetry.sqlite")


def get_gemini_db_connection(db_path: Union[str, Path] = DEFAULT_GEMINI_DB) -> sqlite3.Connection:
    """Fetch a thread-local SQLite connection for Gemini API telemetry."""
    return get_db_connection(db_path)
