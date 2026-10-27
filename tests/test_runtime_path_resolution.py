"""Unit and regression tests for dynamic runtime path resolution in --onefile mode."""

import sys
import tempfile
import unittest
from pathlib import Path

from core.paths import get_app_root, get_asset_path, get_cache_dir, get_logs_dir, resource_path


class TestRuntimePathResolution(unittest.TestCase):
    """Verify resource_path and asset resolvers in standard and frozen --onefile execution."""

    def test_live_source_resolution(self) -> None:
        # 1. Direct asset path
        en_locale = resource_path("assets/locales/en.json")
        self.assertTrue(en_locale.exists())
        self.assertTrue(en_locale.is_file())

        # 2. Subfolder fallback (locales/ko.json -> assets/locales/ko.json)
        ko_locale = resource_path("locales/ko.json")
        self.assertTrue(ko_locale.exists())

        # 3. get_asset_path returns string
        asset_str = get_asset_path("locales/en.json")
        self.assertTrue(isinstance(asset_str, str))
        self.assertTrue(Path(asset_str).exists())

    def test_frozen_onefile_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mock_meipass = Path(td)
            mock_asset = mock_meipass / "assets" / "locales" / "en.json"
            mock_asset.parent.mkdir(parents=True, exist_ok=True)
            mock_asset.write_text("{}", encoding="utf-8")

            # Mock PyInstaller frozen state
            orig_frozen = getattr(sys, "frozen", None)
            orig_meipass = getattr(sys, "_MEIPASS", None)
            try:
                sys.frozen = True
                sys._MEIPASS = str(mock_meipass)

                self.assertEqual(get_app_root(), mock_meipass.resolve())
                resolved = resource_path("locales/en.json")
                self.assertEqual(resolved, mock_asset.resolve())
                self.assertTrue(resolved.exists())

                # Caches and logs must never point inside _MEIPASS
                cache_dir = get_cache_dir()
                logs_dir = get_logs_dir()
                self.assertNotIn(str(mock_meipass), str(cache_dir))
                self.assertNotIn(str(mock_meipass), str(logs_dir))
            finally:
                if orig_frozen is None:
                    delattr(sys, "frozen")
                else:
                    sys.frozen = orig_frozen

                if orig_meipass is None:
                    delattr(sys, "_MEIPASS")
                else:
                    sys._MEIPASS = orig_meipass


if __name__ == "__main__":
    unittest.main()
