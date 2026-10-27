"""Persistent cache layer using thread-local SQLite connection management."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional, Union

from core.database import get_db_connection

_local = threading.local()


def get_cache_db_connection(db_path: Union[str, Path] = "cache.sqlite") -> sqlite3.Connection:
    """Fetch a thread-local SQLite database connection for persistent caching."""
    return get_db_connection(db_path)


class StorageCache:
    """Thread-safe persistent cache backed by thread-local SQLite connections."""

    def __init__(self, db_path: Union[str, Path] = "cache.sqlite") -> None:
        self.db_path = str(db_path)
        self._init_db()

    @property
    def connection(self) -> sqlite3.Connection:
        return get_db_connection(self.db_path)

    def _init_db(self) -> None:
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS response_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT,
                    created_at REAL
                );
                """
            )
