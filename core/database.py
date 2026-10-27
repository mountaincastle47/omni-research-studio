"""Thread-local SQLite database connection management for cross-thread access isolation."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Optional, Union

try:
    from PySide6.QtCore import QStandardPaths
except ImportError:
    try:
        from PyQt6.QtCore import QStandardPaths
    except ImportError:
        QStandardPaths = None


def get_app_data_dir() -> Path:
    # Resolves to %LOCALAPPDATA%\OmniResearchStudio on Windows
    base_path = ""
    if QStandardPaths is not None:
        try:
            base_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        except Exception:
            base_path = ""

    if base_path:
        p = Path(base_path)
        app_dir = p if p.name.lower() == "omniresearchstudio" else p / "OmniResearchStudio"
    else:
        app_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "OmniResearchStudio"

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


DB_PATH = str(get_app_data_dir() / "token_ledger.sqlite")


def resolve_db_path(db_path: Union[str, Path] = DB_PATH) -> str:
    """
    Reroute any relative or unqualified SQLite database path to the OS-standard AppData directory.
    Guarantees no .sqlite, .sqlite-wal, or .sqlite-shm files are created in the current working directory.
    Preserves in-memory databases and explicit absolute paths.
    """
    path_str = str(db_path)
    if path_str in (":memory:", ""):
        return path_str or ":memory:"
    p = Path(path_str)
    if not p.is_absolute():
        return str(get_app_data_dir() / p.name)
    return str(p)


_local = threading.local()


def _is_connection_valid(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1;")
        return True
    except Exception:
        return False


def get_db_connection(db_path: Union[str, Path] = DB_PATH) -> sqlite3.Connection:
    """
    Fetch or initialize a thread-local SQLite database connection.
    Guarantees that background workers and the main thread never share connection instances.
    Configures WAL journaling, NORMAL synchronization, and 5000ms busy timeout.
    Enforces OS-standard LocalAppData storage for database and journal artifacts.
    """
    path_str = resolve_db_path(db_path)
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
            conn.execute("PRAGMA cache_size = -64000;")       # 64MB dedicated RAM cache
            conn.execute("PRAGMA mmap_size = 268435456;")     # 256MB memory-mapped direct I/O
            conn.execute("PRAGMA temp_store = MEMORY;")
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
        path_str = resolve_db_path(db_path)
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
