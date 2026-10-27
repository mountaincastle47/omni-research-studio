"""OmniResearch Studio — i18n Dictionary Reconciliation & UI Repair Test Suite."""

import json
import logging
import os
import re
import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication

qapp = QApplication.instance()
if qapp is None:
    qapp = QApplication(sys.argv)

from core.compute_manager import ComputeManager
from core.i18n import STRINGS, get_text, humanize_key
from ui.compute_dialog import ComputeDialog


def test_1_bidirectional_parity() -> None:
    print("[1/4] Testing Bi-Directional Locale Parity & Dictionary Cleanliness...")
    prefix_regex = re.compile(r"^(btn_|lbl_|txt_|menu_|title_|tab_|action_|col_|sec\d+_)")

    en_keys = {k for k, v in STRINGS.items() if "en" in v and v["en"]}
    ko_keys = {k for k, v in STRINGS.items() if "ko" in v and v["ko"]}

    diff = en_keys.symmetric_difference(ko_keys)
    assert len(diff) == 0, f"Symmetric difference between en and ko detected: {diff}"

    for key, v in STRINGS.items():
        en_val = v.get("en", "")
        ko_val = v.get("ko", "")

        assert en_val, f"Key '{key}' has empty English translation"
        assert ko_val, f"Key '{key}' has empty Korean translation"

        assert en_val != key, f"English value for '{key}' is equal to raw key name"
        assert ko_val != key, f"Korean value for '{key}' is equal to raw key name"

        assert not prefix_regex.match(en_val), f"English value '{en_val}' matches raw prefix pattern"
        assert not prefix_regex.match(ko_val), f"Korean value '{ko_val}' matches raw prefix pattern"

    # Specific assertion mandated by requirements
    assert STRINGS["btn_view_translation"]["en"] == "View Translation"
    assert STRINGS["btn_view_original"]["en"] == "View Original"
    print(f"  [OK] All {len(STRINGS)} dictionary keys have complete, clean bi-directional parity")


def test_2_json_locale_files() -> None:
    print("[2/4] Validating External Locale JSON Files...")
    locales_dir = ROOT_DIR / "assets" / "locales"
    assert locales_dir.exists(), "assets/locales directory missing"

    en_json_path = locales_dir / "en.json"
    ko_json_path = locales_dir / "ko.json"

    assert en_json_path.exists(), "assets/locales/en.json missing"
    assert ko_json_path.exists(), "assets/locales/ko.json missing"

    with open(en_json_path, "r", encoding="utf-8") as fp:
        en_data = json.load(fp)
    with open(ko_json_path, "r", encoding="utf-8") as fp:
        ko_data = json.load(fp)

    assert len(en_data) == len(STRINGS)
    assert len(ko_data) == len(STRINGS)
    assert set(en_data.keys()) == set(STRINGS.keys())
    assert set(ko_data.keys()) == set(STRINGS.keys())
    print(f"  [OK] Validated JSON locale files with {len(en_data)} syntax-clean entries")


def test_3_defensive_fallback_and_warning(caplog=None) -> None:
    print("[3/4] Testing Localization Fallback Chain & Dev-Warning Architecture...")
    # 1. Existing key lookup
    assert get_text("btn_view_translation", "en") == "View Translation"
    assert get_text("btn_view_translation", "ko") == "번역본 보기"

    # 2. Key with missing Korean translation (fallback to English)
    test_key = "_test_mock_fallback_key"
    STRINGS[test_key] = {"en": "Mocked English Fallback"}
    try:
        assert get_text(test_key, "ko") == "Mocked English Fallback"
    finally:
        STRINGS.pop(test_key, None)

    # 3. Completely missing key (defensive humanization)
    assert humanize_key("btn_view_translation") == "View Translation"
    assert humanize_key("lbl_deep_quantum_telemetry") == "Deep Quantum Telemetry"
    assert humanize_key("menu_hardware_acceleration") == "Hardware Acceleration"

    unknown_key = "btn_automated_quantum_audit"
    humanized = get_text(unknown_key, "en")
    assert humanized == "Automated Quantum Audit"
    print("  [OK] Fallback chain (Target -> Default -> Humanized Key) verified successfully")


def test_4_interactive_compute_dialog() -> None:
    print("[4/4] Testing Interactive Compute Telemetry Badge & Provider Dialog...")
    cm = ComputeManager.get_instance()
    initial_profile = cm.profile
    assert initial_profile.device_type in ("cpu", "cuda", "directml", "vulkan")
    assert initial_profile.cpu_cores >= 1

    badge_en = cm.get_badge_text("en")
    badge_ko = cm.get_badge_text("ko")
    assert "Compute:" in badge_en
    assert "연산" in badge_ko

    supported = cm.get_supported_providers()
    assert len(supported) >= 4
    provider_ids = [p["id"] for p in supported]
    assert "CPUExecutionProvider" in provider_ids
    assert "CUDAExecutionProvider" in provider_ids
    assert "DmlExecutionProvider" in provider_ids
    assert "VulkanExecutionProvider" in provider_ids

    # Switch provider test
    cm.set_provider("CUDAExecutionProvider")
    assert cm.profile.device_type == "cuda"
    assert cm.profile.precision == "float16"

    # Restore CPU INT8 profile
    cm.set_provider("CPUExecutionProvider")
    assert cm.profile.device_type == "cpu"
    assert cm.profile.precision == "int8"

    # Instantiate dialog
    dlg = ComputeDialog(lang="en")
    assert dlg.windowTitle() == "Compute & Hardware Acceleration"
    assert dlg.combo_providers.count() == len(supported)
    dlg.close()
    print("  [OK] Compute provider switching and interactive dialog verified successfully")


def main() -> None:
    print("======================================================================")
    print("     OmniResearch Studio — i18n & UI Repair Verification Suite        ")
    print("======================================================================")
    test_1_bidirectional_parity()
    test_2_json_locale_files()
    test_3_defensive_fallback_and_warning()
    test_4_interactive_compute_dialog()
    print("\n======================================================================")
    print("             ALL i18n & UI REPAIR TESTS PASSED (100%)                 ")
    print("======================================================================")


if __name__ == "__main__":
    main()
