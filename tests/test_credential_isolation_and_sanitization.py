"""Test suite for Credential Isolation, Storage Standard, Key Lifecycle, and Packaging Sanitization."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Headless Qt environment setup
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import QApplication

from core.paths import get_app_root, get_settings_dir
from core.config_manager import ConfigManager
from package import is_blacklisted_artifact, verify_dist_sanitization
from ui.components import ApiKeyBanner


KEY_PREFIX = "".join(["A", "I", "z", "a"])


class TestCredentialIsolation(unittest.TestCase):
    """Verify that credentials are never stored in or read from the executable/project root directory."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_config_path = Path(self.temp_dir.name) / "cache" / "user_config.json"
        self.mock_settings_file = Path(self.temp_dir.name) / "appdata" / "settings.json"

        self.cfg = ConfigManager(config_path=self.mock_config_path)
        self.cfg.settings_file = self.mock_settings_file

    def tearDown(self) -> None:
        self.cfg.clear_api_key()
        self.temp_dir.cleanup()

    def test_settings_dir_isolated_from_app_root(self) -> None:
        settings_dir = get_settings_dir()
        app_root = get_app_root()
        self.assertNotEqual(settings_dir, app_root)
        self.assertNotIn(str(app_root).lower(), str(settings_dir).lower())

    def test_api_key_lifecycle_save_and_clear(self) -> None:
        test_key = KEY_PREFIX + "SyTest_Key_For_Unit_Testing_12345"

        # 1. Save Key
        self.cfg.save_api_key(test_key)
        self.assertEqual(self.cfg.get_api_key(), test_key)
        self.assertTrue(self.cfg.has_api_key())

        # Verify QSettings holds the key
        qs = QSettings("OmniResearch", "OmniResearchStudio")
        self.assertEqual(qs.value("gemini_api_key"), test_key)

        # Verify isolated user settings file holds the key
        self.assertTrue(self.mock_settings_file.exists())
        self.assertIn(test_key, self.mock_settings_file.read_text(encoding="utf-8"))

        # Verify local user_config.json NEVER contains the raw key
        if self.mock_config_path.exists():
            self.assertNotIn(test_key, self.mock_config_path.read_text(encoding="utf-8"))

        # 2. Clear Key
        self.cfg.clear_api_key()
        self.assertEqual(self.cfg.get_api_key(), "")
        self.assertFalse(self.cfg.has_api_key())
        self.assertNotIn("GEMINI_API_KEY", os.environ)

        # Verify purged from QSettings
        self.assertFalse(bool(qs.value("gemini_api_key")))

        # Verify purged from settings.json
        if self.mock_settings_file.exists():
            self.assertNotIn(test_key, self.mock_settings_file.read_text(encoding="utf-8"))


class TestApiKeyBannerClearFeature(unittest.TestCase):
    """Verify Clear Stored Key button and badge state transitions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_clear_credentials_button_and_badge_revert(self) -> None:
        initial_key = KEY_PREFIX + "SyFakeKeyForUiTest_98765"
        banner = ApiKeyBanner(initial_key=initial_key, lang="en")
        banner.show()

        # 1. Initial active key state
        self.assertIn("Active Key", banner.badge_label.text())
        self.assertIn("...8765", banner.badge_label.text())

        # 2. Start editing
        banner._on_start_editing()
        self.assertTrue(banner._editing)
        self.assertTrue(banner.key_input.isVisible())
        self.assertTrue(banner.save_btn.isVisible())
        self.assertTrue(banner.clear_btn.isVisible())
        self.assertFalse(banner.change_btn.isVisible())

        # 3. Click Clear Stored Key
        cleared_emitted = []
        banner.api_key_Cleared.connect(lambda: cleared_emitted.append(True))

        banner.clear_btn.click()
        self.app.processEvents()

        # 4. Verify cleared state
        self.assertEqual(len(cleared_emitted), 1)
        self.assertEqual(banner._current_key, "")
        self.assertEqual(banner.key_input.text(), "")
        self.assertFalse(banner._editing)

        # 5. Verify badge reverted to "No Key Configured" with #e74c3c
        self.assertIn("No Key Configured", banner.badge_label.text())
        self.assertIn("#e74c3c", banner.badge_label.styleSheet())
        banner.close()


class TestPackagingSanitizationAudit(unittest.TestCase):
    """Verify blacklist pattern enforcement and post-build verification logic."""

    def test_blacklist_pattern_matching(self) -> None:
        blacklisted = [
            ".env",
            ".env.local",
            ".env.production",
            "production.env",
            "private.key",
            "cert.key",
            "credentials.json",
            "config.json",
            "user_config.json",
            "token_ledger.sqlite",
            "token_ledger.sqlite3",
            "corpus.db",
            "session.log",
            "logs/debug.log",
            "__pycache__/engine.cpython-314.pyc",
            ".pytest_cache/v/cache/lastfailed",
        ]
        for path_str in blacklisted:
            self.assertTrue(
                is_blacklisted_artifact(Path(path_str)),
                f"Expected {path_str} to be blacklisted",
            )

        allowed = [
            "OmniResearchStudio.exe",
            "python314.dll",
            "assets/locales/en.json",
            "assets/locales/ko.json",
            "assets/icons/app_icon.png",
            "PyQt6/QtCore.pyd",
        ]
        for path_str in allowed:
            self.assertFalse(
                is_blacklisted_artifact(Path(path_str)),
                f"Expected {path_str} to be allowed in release",
            )

    def test_post_build_verification_detects_leaked_key(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            target_dir = Path(td)
            # Create harmless file
            (target_dir / "app.txt").write_text("Hello world", encoding="utf-8")

            # Must pass clean scan
            verify_dist_sanitization(target_dir)

            # Plant raw Gemini API key
            (target_dir / "leaked.txt").write_text(
                f"API_KEY={KEY_PREFIX}SyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q", encoding="utf-8"
            )
            with self.assertRaises(RuntimeError):
                verify_dist_sanitization(target_dir)


if __name__ == "__main__":
    unittest.main()
