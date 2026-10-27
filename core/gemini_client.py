"""Gemini client interface with thread-local database telemetry management."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional, Union

from core.database import get_db_connection

_local = threading.local()


def get_gemini_db_connection(db_path: Union[str, Path] = "gemini_telemetry.sqlite") -> sqlite3.Connection:
    """Fetch a thread-local SQLite connection for Gemini API telemetry."""
    return get_db_connection(db_path)
