"""Thread-local SQLite database connection management for cross-thread access isolation."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Dict, Optional, Union

_local = threading.local()


def _is_connection_valid(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1;")
        return True
    except Exception:
        return False


def get_db_connection(db_path: Union[str, Path] = "token_ledger.sqlite") -> sqlite3.Connection:
    """
    Fetch or initialize a thread-local SQLite database connection.
    Guarantees that background workers and the main thread never share connection instances.
    Configures WAL journaling, NORMAL synchronization, and 5000ms busy timeout.
    """
    path_str = str(db_path)
    if not hasattr(_local, "connections"):
        _local.connections: Dict[str, sqlite3.Connection] = {}

    conn = _local.connections.get(path_str)
    if conn is None or not _is_connection_valid(conn):
        if path_str != ":memory:":
            Path(path_str).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path_str, check_same_thread=False, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
        except sqlite3.OperationalError:
            pass
        _local.connections[path_str] = conn
        _local.connection = conn

    return conn


def close_thread_connection(db_path: Optional[Union[str, Path]] = None) -> None:
    """Close and discard a specific connection or all connections held by the current thread."""
    if not hasattr(_local, "connections"):
        return

    if db_path is not None:
        path_str = str(db_path)
        conn = _local.connections.pop(path_str, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        if getattr(_local, "connection", None) is conn:
            _local.connection = None
    else:
        for conn in list(_local.connections.values()):
            try:
                conn.close()
            except Exception:
                pass
        _local.connections.clear()
        _local.connection = None


def close_thread_connections() -> None:
    close_thread_connection(None)
