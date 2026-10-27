"""First-Run Bootstrapper & Environment Initializer for OmniResearch Studio.

Prepares runtime directory structures, initializes empty SQLite FTS5 tables,
and seeds default configuration if absent before GUI boot.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from core.paths import get_cache_dir, get_logs_dir, get_settings_dir, get_app_root

logger = logging.getLogger("OmniBootstrap")


def bootstrap_runtime(
    cache_dir: Optional[Path] = None,
    logs_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Ensure all required directories and files exist before application lifecycle begins.
    Safe to call repeatedly (idempotent).
    """
    target_cache = cache_dir or get_cache_dir()
    target_logs = logs_dir or get_logs_dir()
    target_settings = get_settings_dir()

    logger.info(
        f"[Storage Isolation] User-space credentials directory: {target_settings} | "
        f"Registry: HKCU\\Software\\OmniResearch\\OmniResearchStudio | "
        f"App root: {get_app_root()} (Isolated from secrets)"
    )

    # 1. Recursively ensure core runtime directories
    dirs_to_create = [
        target_cache,
        target_cache / "figures",
        target_cache / "plots",
        target_cache / "academic",
        target_cache / "checkpoints",
        target_logs,
        target_settings,
    ]
    created_dirs: list[str] = []
    for d in dirs_to_create:
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(d))

    # 2. Ensure default user_config.json exists
    config_file = target_cache / "user_config.json"
    config_created = False
    if not config_file.exists():
        try:
            from core.config_manager import DEFAULT_CONFIG
            config_file.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
            config_created = True
        except Exception as e:
            logger.warning(f"Failed to seed user_config.json during bootstrap: {e}")

    # 3. Ensure SQLite FTS5 index table schema is initialized
    fts_db_path = target_cache / "corpus_search.sqlite"
    fts_initialized = False
    try:
        from core.search_index import CorpusSearchIndex
        idx = CorpusSearchIndex(db_path=str(fts_db_path))
        idx.close()
        fts_initialized = True
    except Exception as e:
        logger.warning(f"Failed to initialize SQLite FTS5 schema during bootstrap: {e}")

    # 4. Ensure Token Ledger SQLite database exists in LocalAppData
    from core.database import DB_PATH
    ledger_db_path = Path(DB_PATH)
    ledger_initialized = False
    try:
        from core.token_ledger import TokenLedger
        ledger = TokenLedger(db_path=ledger_db_path)
        ledger.close()
        ledger_initialized = True
    except Exception as e:
        logger.warning(f"Failed to initialize Token Ledger schema during bootstrap: {e}")

    return {
        "success": True,
        "cache_dir": str(target_cache),
        "logs_dir": str(target_logs),
        "created_dirs": created_dirs,
        "config_created": config_created,
        "fts_initialized": fts_initialized,
        "ledger_initialized": ledger_initialized,
    }
