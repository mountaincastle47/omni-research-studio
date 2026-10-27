"""Execution history store using thread-local SQLite connection management."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, List, Optional, Union

from core.database import get_app_data_dir, get_db_connection

_local = threading.local()
DEFAULT_HISTORY_DB = str(get_app_data_dir() / "history.sqlite")


def get_history_db_connection(db_path: Union[str, Path] = DEFAULT_HISTORY_DB) -> sqlite3.Connection:
    """Fetch a thread-local SQLite connection for execution history."""
    return get_db_connection(db_path)


class ExecutionHistory:
    """Thread-safe execution history manager backed by thread-local SQLite connections."""

    def __init__(self, db_path: Union[str, Path] = DEFAULT_HISTORY_DB) -> None:
        self.db_path = str(db_path)
        self._init_db()

    @property
    def connection(self) -> sqlite3.Connection:
        return get_db_connection(self.db_path)

    def _init_db(self) -> None:
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    stage TEXT,
                    status TEXT,
                    created_at REAL
                );
                """
            )
