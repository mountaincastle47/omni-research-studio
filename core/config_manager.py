"""Centralized Persistent Settings Manager:
Thread-safe configuration engine backed by user-space OS storage (%APPDATA% / QSettings)
with strict credential isolation ensuring API keys never touch project root or distribution binaries.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional

try:
    from PyQt6.QtCore import QSettings
    HAVE_QSETTINGS = True
except Exception:
    HAVE_QSETTINGS = False

from core.paths import get_cache_dir, get_settings_dir, get_app_root, SESSION_CACHE_DIR

logger = logging.getLogger("OmniConfigManager")

USER_CONFIG_FILE = get_cache_dir() / "user_config.json"
USER_SETTINGS_FILE = get_settings_dir() / "settings.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    # 1. API & Cloud Model Settings
    "gemini_api_key": "",
    "discovery_model": "gemini-3.8-flash",
    "synthesis_model": "gemini-4-argon",
    "audio_model": "gemini-3.8-flash",
    # 2. Local LLM Settings
    "local_llm_endpoint": "http://localhost:11434/v1",
    "default_local_model": "qwen2.5:7b",
    # 3. Audio & Voice Settings
    "audio_playback_rate": 1.0,
    "host_a_voice": "en-US-GuyNeural",
    "host_b_voice": "en-US-JennyNeural",
    "silence_padding_duration_ms": 200,
    # 4. Network & LAN Mirror
    "lan_server_port": 8484,
    "auto_start_lan_server": True,
    "network_check_timeout_s": 5,
    # 5. Storage & Vault Backup
    "cache_retention_days": 14,
    "autosave_interval_s": 60,
    "vault_backup_path": "session_cache/backups",
    "webdav_endpoint": "",
    # 6. UI & Typography
    "active_theme": "dark",
    "font_family": "Segoe UI",
    "base_font_size": 10,
    # 7. Epistemic Rules
    "contested_matrix_enforcement": True,
    "bm25_compression_threshold_tokens": 64000,
}


class ConfigManager:
    """Thread-safe persistent settings manager with atomic writes and credential isolation."""

    _instance: Optional[ConfigManager] = None
    _lock = threading.RLock()

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or USER_CONFIG_FILE
        self.settings_file = USER_SETTINGS_FILE
        self._data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.settings_dir = get_settings_dir()

        logger.info(
            f"[Credential Isolation] User storage directory: {self.settings_dir} | "
            f"Windows Registry: HKCU\\Software\\OmniResearch\\OmniResearchStudio | "
            f"Application root: {get_app_root()} (Isolated from secrets)"
        )
        self.load()

    @classmethod
    def get_instance(cls, config_path: Optional[Path] = None) -> ConfigManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = ConfigManager(config_path)
            return cls._instance

    def load(self) -> Dict[str, Any]:
        """Load configuration from disk with atomic fallback, user-space settings, and environment overrides."""
        with self._lock:
            if self.config_path.exists():
                try:
                    raw = self.config_path.read_text(encoding="utf-8")
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        for k, v in loaded.items():
                            self._data[k] = v
                except Exception as exc:
                    logger.warning(f"Error reading {self.config_path}: {exc}. Using defaults.")

            # Load persistent user settings from %APPDATA%/OmniResearchStudio/settings.json
            if self.settings_file.exists():
                try:
                    raw_settings = json.loads(self.settings_file.read_text(encoding="utf-8"))
                    if isinstance(raw_settings, dict):
                        stored_key = str(raw_settings.get("gemini_api_key", "") or "").strip()
                        if stored_key:
                            self._data["gemini_api_key"] = stored_key
                except Exception as exc:
                    logger.debug(f"Error reading user settings file {self.settings_file}: {exc}")

            # Check QSettings (Windows Registry: HKCU\Software\OmniResearch\OmniResearchStudio)
            if HAVE_QSETTINGS:
                try:
                    qs = QSettings("OmniResearch", "OmniResearchStudio")
                    reg_key = str(qs.value("gemini_api_key", "") or "").strip()
                    if reg_key:
                        self._data["gemini_api_key"] = reg_key
                except Exception:
                    pass

            # Environment override for GEMINI_API_KEY has highest precedence
            env_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if env_key:
                self._data["gemini_api_key"] = env_key

            return dict(self._data)

    def save(self, api_key: Optional[str] = None) -> None:
        """Atomically persist current configuration to disk, routing credentials to isolated user-space."""
        with self._lock:
            if api_key is not None:
                self.save_api_key(api_key)

            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.config_path.with_suffix(".tmp")
            try:
                # Sanitize data for local/cache config: never save raw API key to application/cache file
                persist_data = dict(self._data)
                if self.config_path != self.settings_file:
                    persist_data["gemini_api_key"] = ""

                content = json.dumps(persist_data, indent=2, ensure_ascii=False)
                tmp_path.write_text(content, encoding="utf-8")
                os.replace(tmp_path, self.config_path)
            except Exception as exc:
                logger.error(f"Failed to persist configuration atomically: {exc}")
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)

    def save_api_key(self, api_key: str) -> None:
        """Persist API key exclusively into user-space storage (QSettings & %APPDATA%/settings.json)."""
        with self._lock:
            key_clean = str(api_key or "").strip()
            self._data["gemini_api_key"] = key_clean

            # 1. Windows Registry / QSettings
            if HAVE_QSETTINGS:
                try:
                    qs = QSettings("OmniResearch", "OmniResearchStudio")
                    if key_clean:
                        qs.setValue("gemini_api_key", key_clean)
                    else:
                        qs.remove("gemini_api_key")
                    qs.sync()
                except Exception as e:
                    logger.debug(f"QSettings write failed: {e}")

            # 2. User-space %APPDATA%/OmniResearchStudio/settings.json
            try:
                self.settings_file.parent.mkdir(parents=True, exist_ok=True)
                current_settings = {}
                if self.settings_file.exists():
                    try:
                        current_settings = json.loads(self.settings_file.read_text(encoding="utf-8"))
                    except Exception:
                        current_settings = {}
                current_settings["gemini_api_key"] = key_clean
                self.settings_file.write_text(json.dumps(current_settings, indent=2), encoding="utf-8")
            except Exception as e:
                logger.error(f"Failed to write %APPDATA% settings.json: {e}")

            # 3. Environment sync
            if key_clean:
                os.environ["GEMINI_API_KEY"] = key_clean
            elif "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]

    def clear_api_key(self) -> None:
        """Purge API key completely from QSettings, %APPDATA%/settings.json, environment, and memory."""
        with self._lock:
            self._data["gemini_api_key"] = ""
            if "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]

            # 1. Clear QSettings
            if HAVE_QSETTINGS:
                try:
                    qs = QSettings("OmniResearch", "OmniResearchStudio")
                    qs.remove("gemini_api_key")
                    qs.sync()
                except Exception as e:
                    logger.debug(f"QSettings remove failed: {e}")

            # 2. Clear %APPDATA%/settings.json
            if self.settings_file.exists():
                try:
                    current_settings = json.loads(self.settings_file.read_text(encoding="utf-8"))
                    if "gemini_api_key" in current_settings:
                        current_settings["gemini_api_key"] = ""
                        self.settings_file.write_text(json.dumps(current_settings, indent=2), encoding="utf-8")
                except Exception as e:
                    logger.debug(f"Failed to clear %APPDATA% settings.json: {e}")

            # 3. Persist general config with empty key
            self.save()
            logger.info("[Credential Isolation] Cleared stored API key from QSettings and user-space storage.")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration setting with fallback default."""
        with self._lock:
            if key == "gemini_api_key":
                return self.get_api_key()
            return self._data.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        """Set a configuration value and automatically persist."""
        with self._lock:
            if key == "gemini_api_key":
                self.save_api_key(str(value or ""))
            else:
                self._data[key] = value

            if auto_save:
                self.save()

    def get_all(self) -> Dict[str, Any]:
        """Return a copy of all current configuration values."""
        with self._lock:
            res = dict(self._data)
            res["gemini_api_key"] = self.get_api_key()
            return res

    def update_bulk(self, settings: Dict[str, Any]) -> None:
        """Update multiple keys atomically and persist."""
        with self._lock:
            for k, v in settings.items():
                if k == "gemini_api_key":
                    self.save_api_key(str(v or ""))
                else:
                    self._data[k] = v
            self.save()

    def reset_defaults(self) -> None:
        """Reset all configuration values to defaults, without wiping isolated API key unless requested."""
        with self._lock:
            existing_key = self.get_api_key()
            self._data = dict(DEFAULT_CONFIG)
            self._data["gemini_api_key"] = existing_key
            self.save()

    # --- Backward-Compatibility Facade with legacy ConfigManager ---

    def get_api_key(self) -> str:
        """Return active Gemini API key from environment, QSettings, or user-space settings.json."""
        with self._lock:
            # 1. Environment variable override
            env_key = os.environ.get("GEMINI_API_KEY", "").strip()
            if env_key:
                return env_key

            # 2. QSettings (Windows Registry: HKCU\Software\OmniResearch\OmniResearchStudio)
            if HAVE_QSETTINGS:
                try:
                    qs = QSettings("OmniResearch", "OmniResearchStudio")
                    val = str(qs.value("gemini_api_key", "") or "").strip()
                    if val:
                        self._data["gemini_api_key"] = val
                        return val
                except Exception:
                    pass

            # 3. User-space %APPDATA%/OmniResearchStudio/settings.json
            if hasattr(self, "settings_file") and self.settings_file.exists():
                try:
                    raw = json.loads(self.settings_file.read_text(encoding="utf-8"))
                    val = str(raw.get("gemini_api_key", "") or "").strip()
                    if val:
                        self._data["gemini_api_key"] = val
                        return val
                except Exception:
                    pass

            return str(self._data.get("gemini_api_key", "") or "").strip()

    def has_api_key(self) -> bool:
        """Return True if a non-empty API key is present."""
        return bool(self.get_api_key())

    def create_client(self, api_key: Optional[str] = None):
        """Instantiate a configured google-genai Client with granular 180s read timeout."""
        api_key = api_key or self.get_api_key()
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Please set your Gemini API key in Preferences or setup bar."
            )
        from google import genai
        from google.genai import types

        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=180000.0),
        )

    @property
    def config(self):
        """Mock AppConfig facade for legacy access."""
        from core.config import AppConfig
        return AppConfig(
            api_key=self.get_api_key(),
            discovery_model=self.get("discovery_model", "gemini-3.8-flash"),
            synthesis_model=self.get("synthesis_model", "gemini-4-argon"),
            audio_model=self.get("audio_model", "gemini-3.8-flash"),
        )
