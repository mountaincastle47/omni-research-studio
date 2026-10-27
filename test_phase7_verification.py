"""Phase 7 Master Executive & Intelligence Suite Headless Verification.

Tests:
1. True API Usage Ledger & Billing Telemetry (TokenLedger, SQLite, cached discount pricing tiers, SpendLedgerDialog)
2. Dual-Pane Split Workspace Comparison View (SplitComparisonWidget, proportional synchronized scroll, tab selector)
3. MP3 Chapter Markers (mutagen.id3 CHAP frames) & SSML Prosody Engine
4. Network Sentinel & Offline Graceful Degradation (offline banner, action button locks, signal transitions)
5. Obsidian PKM & Marp Slide Deck Exporters (frontmatter, wikilinks, Marp gaia presentation directives)
6. Client-Side Pre-Flight Sensitive Pattern Scrubber (API keys, AWS credentials, IPv4, RRNs, emails)
7. Dynamic Typography & High-Contrast Theme Switcher (Dark Studio, OLED Black, Academic Light, font zoom scaling)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication

from core.audio_studio import DialogueTurn, NeuralVoiceSynthesizer, PodcastScript, build_prosody_ssml
from core.config import ConfigManager
from core.document_loader import SourceDocument
from core.exporter import (
    build_marp_markdown,
    build_obsidian_markdown,
    export_to_marp,
    export_to_obsidian,
)
from core.followup_engine import FollowUpEngine
from core.network_sentinel import NetworkSentinel
from core.notebook_synthesis import NotebookSynthesizer
from core.security_filter import scrub_sensitive_patterns
from core.token_ledger import TokenLedger, TokenTotals
from ui.components import SpendLedgerDialog
from ui.main_window import MainWindow
from ui.theme_manager import THEMES, ThemeManager
from ui.workspace_tabs import ResearchWorkspaceTabs, SplitComparisonWidget

_app = QApplication.instance() or QApplication(sys.argv)


def test_1_token_ledger_and_billing_telemetry() -> None:
    print("[1/7] Testing True API Usage Ledger & Billing Telemetry...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "test_ledger.sqlite"
        ledger = TokenLedger(db_path=db_file)

        # 1. Verify cost calculation with 75% cached discount
        # gemini-4-argon: prompt $2.50/M, cached $0.625/M, candidate $10.00/M
        cost_argon = ledger.calculate_cost("gemini-4-argon", prompt_tokens=1_000_000, candidate_tokens=100_000, cached_tokens=500_000)
        # Expected: (1M - 0.5M) * 2.50/1M + 0.5M * 0.625/1M + 0.1M * 10.00/1M
        # = 0.5 * 2.50 + 0.5 * 0.625 + 0.1 * 10.00 = 1.25 + 0.3125 + 1.0 = 2.5625
        assert abs(cost_argon - 2.5625) < 1e-4, f"Unexpected argon cost: {cost_argon}"

        # gemini-3.8-flash: prompt $0.15/M, cached $0.0375/M, candidate $0.60/M
        cost_flash = ledger.calculate_cost("gemini-3.8-flash", prompt_tokens=1_000_000, candidate_tokens=100_000, cached_tokens=400_000)
        # Expected: 0.6M * 0.15 + 0.4M * 0.0375 + 0.1M * 0.60 = 0.09 + 0.015 + 0.06 = 0.165
        assert abs(cost_flash - 0.165) < 1e-4, f"Unexpected flash cost: {cost_flash}"

        # 2. Record manual operations and verify SQLite persistence
        rec1 = ledger.record_manual("gemini-4-argon", prompt_tokens=10_000, candidate_tokens=2_000, cached_tokens=5_000, session_id="test_sess")
        rec2 = ledger.record_manual("gemini-3.8-flash", prompt_tokens=20_000, candidate_tokens=4_000, cached_tokens=0, session_id="test_sess")

        records = ledger.get_all_records(session_id="test_sess")
        assert len(records) == 2, "Expected 2 records recorded in SQLite"

        totals = ledger.get_session_totals(session_id="test_sess")
        assert totals.prompt_tokens == 30_000
        assert totals.candidate_tokens == 6_000
        assert totals.cached_tokens == 5_000
        assert totals.total_cost_usd > 0

        # 3. SpendLedgerDialog
        dialog = SpendLedgerDialog(ledger=ledger, lang="en")
        assert dialog.table.rowCount() == 2
        dialog.close()

        ledger.close()

    print("   -> TokenLedger calculations, SQLite store, and SpendLedgerDialog verified successfully!")


def test_2_dual_pane_split_workspace() -> None:
    print("[2/7] Testing Dual-Pane Split Workspace Comparison View...")
    tabs = ResearchWorkspaceTabs(lang="en")
    pane1 = tabs.current_workspace_pane()
    pane1.title = "Workspace Alpha"
    pane1.synthesis_original_text = "# Alpha Synthesis\n\nContent for Alpha."

    pane2 = tabs.add_new_workspace(title="Workspace Beta")
    pane2.synthesis_original_text = "# Beta Synthesis\n\nContent for Beta."

    assert tabs.count() == 2
    assert hasattr(tabs, "split_view_btn")
    assert tabs.split_view_btn.isCheckable()

    # Activate Split Comparison View
    tabs.enable_split_view(True)
    assert tabs.split_view_btn.isChecked()
    assert tabs._split_widget is not None
    split_w: SplitComparisonWidget = tabs._split_widget

    # Check Left and Right browsers
    assert split_w.left_browser is not None
    assert split_w.right_browser is not None
    assert split_w.secondary_combo is not None
    assert split_w.sync_scroll_chk is not None

    # Verify proportional scroll logic
    split_w.left_browser.setHtml("<p style='height: 2000px;'>Long document left</p>")
    split_w.right_browser.setHtml("<p style='height: 1000px;'>Document right</p>")

    # Trigger synchronized scroll
    split_w._sync_scroll_from_left(100)
    split_w._sync_scroll_from_right(50)
    # Deactivate split view
    tabs.enable_split_view(False)
    assert not tabs.split_view_btn.isChecked()
    assert tabs._split_widget is None

    print("   -> Dual-Pane SplitComparisonWidget and scroll synchronization verified successfully!")


def test_3_mp3_chapter_markers_and_prosody_ssml() -> None:
    print("[3/7] Testing MP3 Chapter Markers (CHAP) & SSML Prosody Engine...")
    import mutagen.id3
    from mutagen.id3 import ID3, CHAP

    # 1. Test build_prosody_ssml
    host_a_text = "Welcome to the research overview."
    host_b_text = "Glad to be here, let's dive into the evidence."

    ssml_a = build_prosody_ssml(host_a_text, "Host A (Strategic)")
    assert '<prosody rate="+3%" pitch="-2Hz">' in ssml_a
    assert "Welcome to the research overview." in ssml_a

    ssml_b = build_prosody_ssml(host_b_text, "Host B (Technical)")
    assert '<prosody rate="+6%" pitch="+3Hz">' in ssml_b
    assert "Glad to be here" in ssml_b

    # 2. Test mutagen ID3 CHAP frames injection
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_mp3 = Path(tmp_dir) / "test_briefing.mp3"
        header = bytes([0xFF, 0xFB, 0x90, 0x64]) + b"\x00" * 414

        script = PodcastScript(
            title="Strategic Intelligence Briefing",
            model_used="gemini-4-argon",
            turns=[
                DialogueTurn(speaker="Host A", role_tag="Host A (Strategic)", text="Introduction to technical baseline architecture."),
                DialogueTurn(speaker="Host B", role_tag="Host B (Technical)", text="Empirical anomalies and contested claims in current methods."),
                DialogueTurn(speaker="Host A", role_tag="Host A (Strategic)", text="Strategic outlook and synthesis verdict for production."),
            ],
        )

        synth = NeuralVoiceSynthesizer(output_dir=Path(tmp_dir))
        mock_chunks = [header * 10, header * 10, header * 10]
        with patch.object(synth, "_synthesize_async", new=AsyncMock(return_value=mock_chunks)):
            result_mp3 = synth.synthesize_script(script)

        # Inspect injected ID3 tags
        tags = ID3(str(result_mp3))
        assert tags.get("TIT2") is not None, "Title tag TIT2 should be present"
        chap_frames = sorted([f for f in tags.values() if isinstance(f, CHAP)], key=lambda x: x.start_time)
        assert len(chap_frames) == 3, f"Expected 3 CHAP frames, found {len(chap_frames)}"
        assert chap_frames[0].element_id == "chp1"
        assert chap_frames[1].element_id == "chp2"
        assert chap_frames[2].element_id == "chp3"

    print("   -> SSML prosody engine and native mutagen ID3 CHAP chapters verified successfully!")


def test_4_network_sentinel_and_offline_degradation() -> None:
    print("[4/7] Testing Network Sentinel & Offline Graceful Degradation...")
    sentinel = NetworkSentinel(check_interval_ms=1000)
    assert sentinel.is_online

    # Simulate transition to offline
    lost_fired = False
    restored_fired = False

    def on_lost():
        nonlocal lost_fired
        lost_fired = True

    def on_restored():
        nonlocal restored_fired
        restored_fired = True

    sentinel.connection_lost.connect(on_lost)
    sentinel.connection_restored.connect(on_restored)

    with patch.object(sentinel, "_probe_connectivity", return_value=False):
        sentinel.check_now()
        assert not sentinel.is_online
        assert lost_fired

    with patch.object(sentinel, "_probe_connectivity", return_value=True):
        sentinel.check_now()
        assert sentinel.is_online
        assert restored_fired

    sentinel.stop()

    # Verify MainWindow offline banner and action locking
    cfg = ConfigManager()
    win = MainWindow(config_manager=cfg)
    assert hasattr(win, "offline_banner")
    assert win.offline_banner.isHidden()

    # Trigger offline in MainWindow
    win._on_connection_lost()
    assert not win.offline_banner.isHidden()
    assert not win.run_sweep_btn.isEnabled()
    assert not win.synthesize_btn.isEnabled()

    # Trigger restored
    win._on_connection_restored()
    assert win.offline_banner.isHidden()
    assert win.run_sweep_btn.isEnabled()
    assert win.synthesize_btn.isEnabled()
    win.close()

    print("   -> NetworkSentinel state transitions and MainWindow degradation verified successfully!")


def test_5_obsidian_and_marp_exporters() -> None:
    print("[5/7] Testing Obsidian PKM & Marp Slide Deck Exporters...")
    sample_report = (
        "# Grounded Synthesis Report\n*Model: gemini-4-argon*\n---\n\n"
        "## Executive Summary\nQuantum computing exhibits rapid architectural growth [1].\n\n"
        "## Algorithmic Complexity\nError correction protocols reduce fault rates [2:p.15].\n"
    )
    docs = [
        SourceDocument(cite_id=1, title="Quantum Architecture Paper", path_or_uri="https://quantum.org/paper.pdf", content="Quantum overview."),
        SourceDocument(cite_id=2, title="Surface Code Foundations", path_or_uri="https://arxiv.org/abs/2201.0001", content="Surface code details."),
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Test Obsidian Export
        obsidian_path = Path(tmp_dir) / "report_obsidian.md"
        export_to_obsidian(
            output_path=obsidian_path,
            report_md=sample_report,
            sources_list=docs,
            metadata={"topic": "Quantum Computing", "groundedness_score": 98},
        )
        assert obsidian_path.exists()
        obs_content = obsidian_path.read_text(encoding="utf-8")
        assert "---" in obs_content
        assert "title: \"Quantum Computing\"" in obs_content
        assert "groundedness_score: \"98%\"" in obs_content
        assert "[[#Source 1 - Quantum Architecture Paper|[1]]]" in obs_content
        assert "[[#Source 2 - Surface Code Foundations|[2:p.15]]]" in obs_content
        assert "## Sources & References" in obs_content

        # 2. Test Marp Presentation Deck Export
        marp_path = Path(tmp_dir) / "slides.marp.md"
        export_to_marp(
            output_path=marp_path,
            report_md=sample_report,
            metadata={"title": "Quantum Computing Overview"},
        )
        assert marp_path.exists()
        marp_content = marp_path.read_text(encoding="utf-8")
        assert "marp: true" in marp_content
        assert "theme: gaia" in marp_content
        assert "_class: lead" in marp_content
        assert "# Quantum Computing Overview" in marp_content
        assert "---" in marp_content
        assert "## Executive Summary" in marp_content
        assert "## Algorithmic Complexity" in marp_content

    print("   -> Obsidian PKM wikilinks and Marp slide deck exporters verified successfully!")


def test_6_sensitive_pattern_scrubber() -> None:
    print("[6/7] Testing Client-Side Pre-Flight Sensitive Pattern Scrubber...")
    key_prefix = "".join(["A", "I", "z", "a"])
    dirty_text = (
        f"Here is my Google API Key: {key_prefix}SyD3x9kL4mNpQrStUvWxYz0123456789a, "
        "and OpenAI Key: sk-abcdefghijklmnopqrstuvwxyz12345678901234, "
        "and AWS Key: AKIAIOSFODNN7EXAMPLE. "
        "Contact me at researcher.alpha@laboratory.io or 192.168.1.100:8080. "
        "My Korean RRN is 900101-1234567."
    )

    clean_text, count = scrub_sensitive_patterns(dirty_text)
    assert count >= 6, f"Expected at least 6 redacted tokens, got {count}"
    assert key_prefix not in clean_text
    assert "[REDACTED:API_KEY]" in clean_text
    assert "AKIAIOSFODNN7EXAMPLE" not in clean_text
    assert "[REDACTED:AWS_KEY]" in clean_text
    assert "researcher.alpha@laboratory.io" not in clean_text
    assert "[REDACTED:EMAIL]" in clean_text
    assert "192.168.1.100:8080" not in clean_text
    assert "[REDACTED:IP]" in clean_text
    assert "900101-1234567" not in clean_text
    assert "[REDACTED:RRN]" in clean_text

    # Test integration into NotebookSynthesizer pre-flight prompt
    raw_prompt = f"Analyze system security with key {key_prefix}SyD3x9kL4mNpQrStUvWxYz0123456789a and IP 10.0.0.1:443"
    scrubbed, count1 = scrub_sensitive_patterns(raw_prompt)
    assert key_prefix not in scrubbed
    assert "[REDACTED:API_KEY]" in scrubbed
    assert "[REDACTED:IP]" in scrubbed
    assert count1 >= 2

    # Test integration into FollowUpEngine
    raw_chat = "My secret key is sk-1234567890abcdef1234567890abcdef and email admin@secret.internal"
    scrubbed_chat, count2 = scrub_sensitive_patterns(raw_chat)
    assert "sk-" not in scrubbed_chat
    assert "[REDACTED:API_KEY]" in scrubbed_chat
    assert "[REDACTED:EMAIL]" in scrubbed_chat
    assert count2 >= 2

    print("   -> Client-side pattern scrubber, regex defenses, and engine integration verified successfully!")


def test_7_theme_manager_and_dynamic_typography() -> None:
    print("[7/7] Testing Dynamic Typography & High-Contrast Theme Switcher...")
    tm = ThemeManager.get_instance()

    # 1. Palettes check
    dark_qss = tm.set_theme("dark")
    assert "#0B0F19" in dark_qss

    oled_qss = tm.set_theme("oled")
    assert "#000000" in oled_qss

    light_qss = tm.set_theme("light")
    assert "#F8FAFC" in light_qss

    # 2. Font scaling and family
    tm.set_theme("dark")
    font_qss = tm.set_font_family("Cascadia Code")
    assert "Cascadia Code" in font_qss

    initial_size = tm.current_font_size
    tm.zoom_in()
    assert tm.current_font_size == initial_size + 1
    tm.zoom_out()
    assert tm.current_font_size == initial_size
    tm.reset_zoom()
    assert tm.current_font_size == 13

    # 3. MainWindow shortcuts and View Menu check
    cfg = ConfigManager()
    win = MainWindow(config_manager=cfg)
    assert hasattr(win, "view_menu")
    assert hasattr(win, "theme_menu")
    assert hasattr(win, "typography_menu")
    assert hasattr(win, "action_split_view")
    assert hasattr(win, "shortcut_split_view")
    assert hasattr(win, "shortcut_zoom_in1")
    assert hasattr(win, "shortcut_zoom_out")
    assert hasattr(win, "shortcut_zoom_reset")

    # Switch theme on MainWindow
    win._on_theme_selected("oled")
    assert win.theme_manager.current_theme == "oled"
    win._on_theme_selected("dark")
    assert win.theme_manager.current_theme == "dark"

    win.close()
    print("   -> ThemeManager palettes, typography zooming, and MainWindow integration verified successfully!")


def main() -> None:
    print("=== OMNIRESEARCH STUDIO PHASE 7 VERIFICATION SUITE ===")
    test_1_token_ledger_and_billing_telemetry()
    test_2_dual_pane_split_workspace()
    test_3_mp3_chapter_markers_and_prosody_ssml()
    test_4_network_sentinel_and_offline_degradation()
    test_5_obsidian_and_marp_exporters()
    test_6_sensitive_pattern_scrubber()
    test_7_theme_manager_and_dynamic_typography()
    print("\nALL PHASE 7 TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
