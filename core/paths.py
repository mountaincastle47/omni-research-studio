"""Universal Asset & Path Virtualization for OmniResearch Studio.

Provides deterministic path resolution whether executing from source checkout
or bundled as a frozen PyInstaller binary distribution.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_app_root() -> Path:
    """
    Resolve the immutable application root directory.
    When frozen with PyInstaller, returns the temporary extraction root `sys._MEIPASS`.
    When running from source, returns the workspace project root.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent.parent


def get_cache_dir() -> Path:
    """
    Resolve the runtime mutable cache directory.
    Defaults to `%LOCALAPPDATA%/OmniResearchStudio/cache` on Windows.
    Falls back to `~/.cache/OmniResearchStudio` if frozen, or `session_cache/` in project root.
    """
    if os.environ.get("OMNI_FORCE_LOCAL_CACHE") == "1":
        cache_dir = get_app_root() / "session_cache"
    else:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            cache_dir = Path(local_app_data) / "OmniResearchStudio" / "cache"
        elif getattr(sys, "frozen", False):
            cache_dir = Path.home() / ".cache" / "OmniResearchStudio"
        else:
            cache_dir = get_app_root() / "session_cache"

    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_logs_dir() -> Path:
    """
    Resolve the runtime log directory.
    Defaults to `%LOCALAPPDATA%/OmniResearchStudio/logs` on Windows.
    Falls back to `~/.cache/OmniResearchStudio/logs` if frozen, or `logs/` in project root.
    """
    if os.environ.get("OMNI_FORCE_LOCAL_LOGS") == "1":
        logs_dir = get_app_root() / "logs"
    else:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            logs_dir = Path(local_app_data) / "OmniResearchStudio" / "logs"
        elif getattr(sys, "frozen", False):
            logs_dir = Path.home() / ".cache" / "OmniResearchStudio" / "logs"
        else:
            logs_dir = get_app_root() / "logs"

    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_settings_dir() -> Path:
    """
    Resolve standard OS user-space settings storage directory.
    Defaults to `%APPDATA%/OmniResearchStudio` on Windows.
    Falls back to `~/.config/OmniResearchStudio` or `%LOCALAPPDATA%/OmniResearchStudio`.
    Guarantees credential isolation: NEVER points to application root or dist directory.
    """
    app_data = os.environ.get("APPDATA")
    if app_data:
        settings_dir = Path(app_data) / "OmniResearchStudio"
    else:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            settings_dir = Path(local_app_data) / "OmniResearchStudio"
        else:
            settings_dir = Path.home() / ".config" / "OmniResearchStudio"

    settings_dir.mkdir(parents=True, exist_ok=True)
    return settings_dir


def resource_path(relative_path: str | Path) -> Path:
    """
    Centralized dynamic runtime resource path resolver for --onefile standalone binaries:
    - If running in frozen state (`getattr(sys, 'frozen', False)`), resolves relative to `sys._MEIPASS`.
    - Otherwise, resolves relative to the workspace project root directory.
    - Also checks `assets/` subfolder fallback if direct path does not exist.
    """
    rel = Path(relative_path)
    root = get_app_root()
    candidate = (root / rel).resolve()
    if candidate.exists():
        return candidate

    candidate_assets = (root / "assets" / rel).resolve()
    if candidate_assets.exists():
        return candidate_assets

    return candidate


def get_app_data_dir() -> Path:
    """
    Resolve the OS-standard application data root directory (%LOCALAPPDATA%/OmniResearchStudio on Windows).
    """
    from core.database import get_app_data_dir as _get_app_data_dir
    return _get_app_data_dir()


def get_asset_path(relative_path: str) -> str:
    """
    Safely locate static application assets (icons, locales, stylesheets, schemas).
    Checks both direct relative path from root and inside `assets/` subfolder.
    """
    return str(resource_path(relative_path))


# Convenience module-level path handles
APP_ROOT = get_app_root()
CACHE_DIR = get_cache_dir()
LOGS_DIR = get_logs_dir()
SETTINGS_DIR = get_settings_dir()
SESSION_CACHE_DIR = get_cache_dir()
APP_DATA_DIR = get_app_data_dir()
