"""OmniResearch Studio — Pass 3 Headless Verification Suite.

Tests:
1. Grounded Follow-Up Q&A Engine & Streaming Chat Drawer (prompts, [N] / [N:p.X] citations, chunk streaming).
2. Dynamic Multi-Tab Research Workspace (closable tabs, 1-tab minimum guard, renaming, auto-naming, per-tab encapsulation).
3. Session & Project Persistence (.omni container format with workspaces/, sources/, audio/ roundtrip).
4. 60-Second Crash Autosave & Recovery detection.
5. Executive Document Exporters (Interactive HTML with hover tooltips + Vector PDF via QPrinter).
6. Real-time Telemetry (Context token calculation, threshold colors: green, cyan, amber).
7. Global Keyboard Accelerators (Ctrl+Return, Ctrl+T, Ctrl+W, Ctrl+S, Ctrl+Shift+S, Escape, Space).
"""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication

# Initialize Headless QApplication
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from core.document_loader import DocumentCorpus, SourceDocument
from core.config import ConfigManager
from core.exporter import build_html_report, build_pdf_html, export_pdf_report, save_html_report
from core.followup_engine import FollowUpEngine
from core.i18n import get_text
from core.project_manager import (
    PROJECT_EXTENSION,
    ProjectState,
    WorkspaceTabState,
    load_project,
    save_project,
)
from ui.chat_drawer import FollowUpChatDrawer
from ui.main_window import MainWindow
from ui.workspace_tabs import ResearchWorkspaceTabs, WorkspaceReportPane, auto_tab_title


def test_1_followup_engine_and_chat_drawer() -> None:
    print("[1/7] Testing Grounded Follow-Up Q&A Engine & Chat Drawer...")

    # Mock client for FollowUpEngine
    mock_client = MagicMock()
    engine = FollowUpEngine(client=mock_client)

    doc1 = SourceDocument(
        cite_id=1,
        title="Solid State Battery Chemistry",
        path_or_uri="https://example.com/battery.pdf",
        content="Solid-state electrolytes offer 400 Wh/kg energy density.\n<!--PAGE_START:2-->\nThermal runaway is suppressed below 180C.",
    )
    docs = [doc1]
    report = "# Battery Analysis\nElectrolytes have advanced [1:p.2]."

    # 1. System Prompt Mandates Verification
    sys_prompt = engine.build_system_instruction(report, docs, "en")
    assert "strictly grounded in the provided synthesis report and active corpus" in sys_prompt
    assert "[N] or [N:p.X]" in sys_prompt
    assert "If the corpus does not contain the answer, explicitly state that the evidence is absent" in sys_prompt
    assert "=== SOURCE [1] ===" in sys_prompt

    # Korean mandate check
    sys_prompt_ko = engine.build_system_instruction(report, docs, "ko")
    assert "한국어" in sys_prompt_ko

    # 2. Chat Drawer streaming and history
    drawer = FollowUpChatDrawer(lang="en")
    drawer.add_user_message("What is the energy density?")
    drawer.begin_assistant_message()
    drawer.append_assistant_chunk("The solid-state electrolyte yields ")
    drawer.append_assistant_chunk("400 Wh/kg <a href='cite:1:2'>[1:p.2]</a>.")
    drawer.finish_assistant_message()

    hist = drawer.history()
    assert len(hist) == 2
    assert hist[0]["role"] == "user"
    assert "What is the energy density?" in hist[0]["text"]
    assert hist[1]["role"] == "assistant"
    assert "400 Wh/kg" in hist[1]["text"]

    # Slice access verification
    assert len(drawer.history[:-1]) == 1
    assert drawer.to_dict_list() == hist

    print("   -> Grounded Follow-Up Q&A engine & streaming chat drawer verified successfully!")


def test_2_workspace_tabs_and_isolation() -> None:
    print("[2/7] Testing Dynamic Multi-Tab Research Workspace...")

    tabs = ResearchWorkspaceTabs(lang="en")
    assert tabs.count() == 1
    pane1 = tabs.current_workspace_pane()
    assert isinstance(pane1, WorkspaceReportPane)

    # Auto-tab title generation
    test_query = "Quantum Error Correction in Neutral Atom Systems Under Cryogenic Conditions"
    title = auto_tab_title(test_query)
    assert title == "Quantum Error Correction in Neutral..."
    tabs.auto_name_active_tab(test_query)
    assert tabs.tabText(0) == title

    # Per-tab data encapsulation
    pane1.query = test_query
    pane1.synthesis_original_text = "Synthesis Report for Quantum Error Correction"
    pane1.audio_directive = "Focus on decoherence mitigation"

    # Add second workspace
    pane2 = tabs.add_new_workspace(title="Workspace 2")
    assert tabs.count() == 2
    pane2.query = "Photonic Interconnects in Datacenters"
    pane2.synthesis_original_text = "Synthesis Report for Photonic Interconnects"
    pane2.audio_directive = "Focus on laser power efficiency"

    # Verify tab isolation
    assert pane1.query != pane2.query
    assert pane1.synthesis_original_text != pane2.synthesis_original_text
    assert pane1.audio_directive != pane2.audio_directive

    # Close second tab
    tabs._on_tab_close_requested(1)
    assert tabs.count() == 1

    # 1-Tab Minimum Guard: closing the last remaining tab MUST NOT remove it
    tabs._on_tab_close_requested(0)
    assert tabs.count() == 1, "1-Tab minimum guard violated: tab was deleted!"
    assert tabs.tabText(0) == "Research Workspace 1"
    assert tabs.current_workspace_pane().query == ""

    print("   -> Dynamic multi-tab research workspace & 1-tab minimum guard verified successfully!")


def test_3_project_persistence_multi_tab() -> None:
    print("[3/7] Testing Session & Project Persistence (.omni ZIP format with workspaces/)...")

    with tempfile.TemporaryDirectory() as tmpdir:
        omni_file = Path(tmpdir) / "test_research.omni"

        doc = SourceDocument(
            cite_id=1,
            title="Neuromorphic Computing",
            path_or_uri="https://example.org/neuro.html",
            content="Spiking neural networks achieve high energy efficiency.",
        )

        ws1 = WorkspaceTabState(
            tab_id="tab_1",
            title="Neuromorphic Hardware",
            query="Neuromorphic architecture benchmarks",
            synthesis_original="Report 1 Markdown with [1]",
            synthesis_translated="보고서 1 한국어 번역",
            audio_directive="Discuss memristor crossbars",
            chat_history=[{"role": "user", "text": "What is the efficiency?"}, {"role": "assistant", "text": "High [1]"}],
        )

        ws2 = WorkspaceTabState(
            tab_id="tab_2",
            title="Optical Computing",
            query="Mach-Zehnder optical computing",
            synthesis_original="Report 2 Optical Markdown",
            synthesis_translated="광학 보고서 한국어",
            audio_directive="Explain beam splitters",
        )

        state = ProjectState(
            documents=[doc],
            active_tab_index=1,
            workspaces=[ws1, ws2],
            topic="Next-Gen Computing",
            language="en",
        )

        # Save project
        saved_path = save_project(omni_file, state)
        assert saved_path.exists()
        assert zipfile.is_zipfile(saved_path)

        # Inspect ZIP container internals
        with zipfile.ZipFile(saved_path, "r") as archive:
            names = set(archive.namelist())
            assert "manifest.json" in names
            assert "workspaces/workspace_0.json" in names
            assert "workspaces/workspace_1.json" in names
            assert any(n.startswith("sources/") for n in names)

        # Load project and verify roundtrip
        loaded_state = load_project(saved_path)
        assert len(loaded_state.workspaces) == 2
        assert loaded_state.active_tab_index == 1
        assert loaded_state.workspaces[0].title == "Neuromorphic Hardware"
        assert loaded_state.workspaces[1].title == "Optical Computing"
        assert len(loaded_state.workspaces[0].chat_history) == 2
        assert loaded_state.workspaces[0].chat_history[0]["role"] == "user"
        assert len(loaded_state.documents) == 1
        assert loaded_state.documents[0].title == "Neuromorphic Computing"

    print("   -> .omni ZIP package persistence & multi-workspace serialization verified successfully!")


def test_4_crash_autosave_and_recovery() -> None:
    print("[4/7] Testing 60-Second Crash Autosave & Startup Recovery Detection...")

    config_mgr = ConfigManager()
    window = MainWindow(config_manager=config_mgr)
    window.show()

    # Populate dummy document and workspace text
    doc = SourceDocument(
        cite_id=1,
        title="Autosave Test Document",
        path_or_uri="local://autosave.txt",
        content="Autosave verification content.",
    )
    window.corpus.add_document(doc)
    window.synthesis_original_text = "Autosave report text [1]"

    # Trigger autosave timer callback
    from core.audio_studio import SESSION_CACHE_DIR
    SESSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    autosave_path = SESSION_CACHE_DIR / "autosave.omni"

    window._on_autosave_timer()
    assert autosave_path.exists(), f"Autosave file was not created at {autosave_path}"
    assert autosave_path.stat().st_size > 500

    # Test load of autosave
    recovered_state = load_project(autosave_path)
    assert len(recovered_state.documents) == 1
    assert "Autosave report text" in recovered_state.synthesis_original

    # Test clean exit removes autosave file
    window.close()
    assert not autosave_path.exists(), "Clean exit failed to remove autosave.omni"

    print("   -> 60-Second crash autosave & clean shutdown lifecycle verified successfully!")


def test_5_executive_document_exporters() -> None:
    print("[5/7] Testing Executive Document Exporter (Interactive HTML + Vector PDF)...")

    with tempfile.TemporaryDirectory() as tmpdir:
        html_out = Path(tmpdir) / "report.html"
        pdf_out = Path(tmpdir) / "report.pdf"

        doc = SourceDocument(
            cite_id=1,
            title="High-Energy Density Battery Research",
            path_or_uri="https://nature.com/articles/battery-400wh",
            content="Solid state batteries with lithium metal anodes demonstrate cycle stability over 1000 cycles.",
        )
        report_md = (
            "# Grounded Synthesis Report\n\n"
            "## Executive Summary\n"
            "Lithium metal batteries achieve superior cycle stability [1].\n\n"
            "| Parameter | Value |\n"
            "| :--- | :--- |\n"
            "| Energy Density | 400 Wh/kg |\n"
        )

        # 1. Interactive HTML Export
        save_html_report(
            path=html_out,
            markdown_text=report_md,
            documents=[doc],
            title="Battery Synthesis",
            model_name="gemini-4-argon",
            language="en",
        )
        assert html_out.exists()
        html_content = html_out.read_text(encoding="utf-8")
        assert "<title>Battery Synthesis</title>" in html_content
        assert 'class="tip"' in html_content, "Missing hover citation tooltip element in HTML"
        assert "@media print" in html_content, "Missing print stylesheet in HTML"
        assert "section class=\"bibliography\"" in html_content, "Missing bibliography section in HTML"

        # 2. Vector PDF Export via QPrinter
        export_pdf_report(
            path=pdf_out,
            markdown_text=report_md,
            documents=[doc],
            title="Battery Executive Briefing",
            model_name="gemini-4-argon",
            language="en",
        )
        assert pdf_out.exists()
        pdf_bytes = pdf_out.read_bytes()
        assert len(pdf_bytes) > 2000, "PDF output is too small to be a valid rendered document"
        assert pdf_bytes.startswith(b"%PDF"), "File does not start with %PDF magic header"

    print("   -> Executive document exporter (Interactive HTML & Vector PDF via QPrinter) verified successfully!")


def test_6_context_telemetry_and_thresholds() -> None:
    print("[6/7] Testing Context Telemetry & Threshold Styling...")

    config_mgr = ConfigManager()
    window = MainWindow(config_manager=config_mgr)

    # 1. Low usage (< 200k tokens) -> Green
    doc_small = SourceDocument(cite_id=1, title="Small Doc", path_or_uri="test", content="A" * 4000)  # ~1000 tokens
    window.corpus.clear()
    window.corpus.add_document(doc_small)
    window.update_telemetry()
    assert "#3FB950" in window.telemetry_label.styleSheet(), "Telemetry should be Green for < 200k tokens"
    assert ("/ 1M" in window.telemetry_label.text()) or ("Prompt:" in window.telemetry_label.text())
    assert ("Spend: ~$" in window.telemetry_label.text()) or ("Spend: $" in window.telemetry_label.text())

    # 2. Medium usage (200k - 600k tokens) -> Cyan
    doc_med = SourceDocument(cite_id=2, title="Med Doc", path_or_uri="test", content="A" * 1_200_000)  # ~300k tokens
    window.corpus.add_document(doc_med)
    window.update_telemetry()
    assert "#38BDF8" in window.telemetry_label.styleSheet(), "Telemetry should be Cyan for 200k-600k tokens"

    # 3. High usage (> 600k tokens) -> Amber
    doc_large = SourceDocument(cite_id=3, title="Large Doc", path_or_uri="test", content="A" * 1_600_000)  # +400k = ~700k tokens
    window.corpus.add_document(doc_large)
    window.update_telemetry()
    assert "#F59E0B" in window.telemetry_label.styleSheet(), "Telemetry should be Amber for > 600k tokens"

    window.close()
    print("   -> Context telemetry calculation & threshold color styling verified successfully!")


def test_7_global_keyboard_shortcuts() -> None:
    print("[7/7] Testing Global Keyboard Accelerators & Menu Actions...")

    config_mgr = ConfigManager()
    window = MainWindow(config_manager=config_mgr)

    # Verify shortcut key sequences
    assert window.shortcut_synth1.key().toString() == "Ctrl+Return"
    assert window.shortcut_synth2.key().toString() == "Ctrl+Enter"
    assert window.shortcut_new_tab.key().toString() == "Ctrl+T"
    assert window.shortcut_close_tab.key().toString() == "Ctrl+W"
    assert window.shortcut_esc.key().toString() == "Esc"
    assert window.shortcut_space.key().toString() == "Space"

    # Verify menu actions
    assert hasattr(window, "action_new_project")
    assert window.action_new_project.shortcut().toString() == "Ctrl+N"
    assert hasattr(window, "action_open_project")
    assert window.action_open_project.shortcut().toString() == "Ctrl+O"
    assert hasattr(window, "action_save_project")
    assert window.action_save_project.shortcut().toString() == "Ctrl+S"
    assert hasattr(window, "action_save_as_project")
    assert window.action_save_as_project.shortcut().toString() == "Ctrl+Shift+S"

    # Test Ctrl+T creates a new tab
    init_count = window.workspace_tabs.count()
    window._on_shortcut_new_tab()
    assert window.workspace_tabs.count() == init_count + 1

    # Test Ctrl+W closes active tab
    window._on_shortcut_close_tab()
    assert window.workspace_tabs.count() == init_count

    window.close()
    print("   -> Global keyboard shortcuts and menu actions verified successfully!")


def main() -> None:
    print("=== OMNIRESEARCH STUDIO PASS 3 VERIFICATION SUITE ===")
    test_1_followup_engine_and_chat_drawer()
    test_2_workspace_tabs_and_isolation()
    test_3_project_persistence_multi_tab()
    test_4_crash_autosave_and_recovery()
    test_5_executive_document_exporters()
    test_6_context_telemetry_and_thresholds()
    test_7_global_keyboard_shortcuts()
    print("\nALL PASS 3 TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
