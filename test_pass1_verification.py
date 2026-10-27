"""Comprehensive headless verification script for Pass 1 of OmniResearch Studio overhaul.

Tests:
1. render_markdown_safely & core.markdown_utils (cite:N, cite:N:P, groups, code block protection)
2. SourceInspectorDock (metadata, origin badge, non-modal plain text view, keyword search & navigation)
3. AudioPlayerWidget (transport, speed combo: 1.0x, 1.25x, 1.5x, 2.0x, volume, save)
4. NeuralVoiceSynthesizer (edge-tts multi-turn dialogue generation to MP3)
5. MainWindow instantiation (layout guards: prompt >= 135px, directive >= 120px, dock attached, citation click routing)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Force Qt offscreen platform for headless terminal execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication, QTextBrowser

from core.audio_studio import DialogueTurn, NeuralVoiceSynthesizer, PodcastScript
from core.citation_audit import audit_citations
from core.document_loader import SourceDocument
from core.markdown_utils import build_dark_html, markdown_to_html
from ui.components import AudioPlayerWidget
from ui.main_window import MainWindow, render_markdown_safely
from ui.source_dock import SourceInspectorDock


def test_markdown_and_citations() -> None:
    print("[1/5] Testing Markdown rendering and interactive citations...")

    md_input = """# Research Synthesis

According to initial findings [1], the performance is verified.
Further page citations [2:p.15] confirm the latency bounds.
Combined evidence [1, 3] and mixed page evidence [2:p.15, 4] corroborate this.

Do not convert inside code blocks:
`[1]` should stay as code.

Do not convert existing anchors:
<a href="https://example.com">[1]</a>

| Parameter | Value |
| --- | --- |
| Accuracy | 99.4% |
"""
    # Test html generation
    html_out = markdown_to_html(md_input, interactive_citations=True)

    assert 'href="cite:1"' in html_out, f"Missing cite:1 in HTML:\n{html_out}"
    assert '>[1]</a>' in html_out, f"Missing [1] anchor label:\n{html_out}"
    assert 'href="cite:2:15"' in html_out, f"Missing cite:2:15 in HTML:\n{html_out}"
    assert '>[2:p.15]</a>' in html_out, f"Missing [2:p.15] anchor label:\n{html_out}"
    assert 'href="cite:3"' in html_out, f"Missing cite:3 in HTML:\n{html_out}"
    assert 'href="cite:4"' in html_out, f"Missing cite:4 in HTML:\n{html_out}"

    # Verify code block preserved
    assert "<code>[1]</code>" in html_out or "<code>[1]" in html_out, "Code block was incorrectly converted"

    # Verify dark html wrapper
    dark_html = build_dark_html(md_input)
    assert "<style>" in dark_html and "color: #c9d1d9;" in dark_html
    assert "<table>" in dark_html

    # Test widget rendering
    browser = QTextBrowser()
    render_markdown_safely(browser, md_input)
    browser_html = browser.toHtml()
    assert "cite:1" in browser_html
    assert "cite:2:15" in browser_html

    print("   -> Markdown and clickable citations [N] & [N:p.P] verified successfully!")


def test_source_inspector_dock(app: QApplication) -> None:
    print("[2/5] Testing SourceInspectorDock...")

    dock = SourceInspectorDock(lang="en")
    assert dock.objectName() == "SourceInspectorDock"
    assert not dock.isModal(), "SourceInspectorDock must be non-modal"

    mock_doc = SourceDocument(
        cite_id=1,
        title="[WEB FULL-TEXT] Deep Learning Architectures",
        source_type="web_sweep",
        path_or_uri="https://arxiv.org/abs/2301.00000",
        content="Deep learning architectures have revolutionized artificial intelligence. Multi-head attention is critical. Deep learning scaling laws apply.",
        word_count=18,
        metadata={"grounding_links": [{"uri": "https://arxiv.org/abs/2301.00000"}]},
    )

    dock.inspect_document(mock_doc, lang="en")
    assert "[1]" in dock.title_label.text()
    assert "Deep Learning Architectures" in dock.title_label.text()
    assert dock.origin_badge.text() != "—"
    assert "18 words" in dock.stats_label.text()
    assert dock.open_url_btn.isVisible()
    assert "Multi-head attention" in dock.text_view.toPlainText()

    # Keyword search
    matches = dock.search("Deep learning")
    assert matches == 2, f"Expected 2 matches for 'Deep learning', got {matches}"
    assert "2 match(es)" in dock.match_label.text()

    # Search navigation
    dock.find_next()
    dock.find_prev()

    # Retranslate
    dock.retranslate_ui(lang="ko")
    assert "18 단어" in dock.stats_label.text()

    # Clear
    dock.clear()
    assert dock.text_view.toPlainText() == ""
    assert dock.origin_badge.text() == "—"

    print("   -> SourceInspectorDock non-modal split-screen verified successfully!")


def test_audio_player_widget(app: QApplication) -> None:
    print("[3/5] Testing AudioPlayerWidget...")

    player_widget = AudioPlayerWidget(lang="en")
    assert player_widget.play_btn is not None
    assert player_widget.position_slider is not None
    assert player_widget.volume_slider is not None
    assert player_widget.save_btn is not None
    assert player_widget.speed_combo is not None

    # Verify speed choices
    speeds = [player_widget.speed_combo.itemText(i) for i in range(player_widget.speed_combo.count())]
    assert speeds == ["1.0x", "1.25x", "1.5x", "2.0x"], f"Unexpected speed options: {speeds}"

    # Verify default state disabled until audio is loaded
    assert not player_widget.play_btn.isEnabled()
    assert not player_widget.position_slider.isEnabled()
    assert not player_widget.speed_combo.isEnabled()

    print("   -> AudioPlayerWidget controls and speed selector verified successfully!")


def test_neural_audio_synthesis() -> None:
    print("[4/5] Testing NeuralVoiceSynthesizer with edge-tts...")

    test_dir = Path("session_cache/test_verification_audio")
    synthesizer = NeuralVoiceSynthesizer(language="en", output_dir=str(test_dir))

    script = PodcastScript(
        title="Verification Podcast",
        model_used="gemini-2.5-pro",
        turns=[
            DialogueTurn(speaker="Host A (Alex)", text="Welcome to the OmniResearch briefing.", role_tag="Host"),
            DialogueTurn(speaker="Host B (Morgan)", text="Great to be here, let us explore the data.", role_tag="Analyst"),
        ],
        raw_script="",
    )

    out_mp3 = synthesizer.synthesize_script(script, force=True)
    assert out_mp3.exists(), f"Output MP3 does not exist: {out_mp3}"
    mp3_size = out_mp3.stat().st_size
    assert mp3_size > 5000, f"MP3 size too small ({mp3_size} bytes)"

    # Test fingerprint caching reuse
    reused_mp3 = synthesizer.synthesize_script(script, force=False)
    assert synthesizer.last_run_reused is True, "Expected synthesizer to reuse cached fingerprint"
    assert reused_mp3 == out_mp3

    # Clean up test output
    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)

    print(f"   -> edge-tts synthesized multi-turn dialogue ({mp3_size} bytes) verified successfully!")


def test_main_window_integration(app: QApplication) -> None:
    print("[5/5] Testing MainWindow integration & layout preservation...")

    window = MainWindow()
    window.show()

    # Verify layout sizing guards
    prompt_min_h = window.sweep_topic_input.minimumHeight()
    assert prompt_min_h >= 135, f"Discovery Prompt minimum height is {prompt_min_h}px, expected >= 135px"

    directive_min_h = window.audio_focus_input.minimumHeight()
    assert directive_min_h >= 120, f"Audio Directive minimum height is {directive_min_h}px, expected >= 120px"

    # Verify dock integration
    assert hasattr(window, "source_dock"), "MainWindow missing source_dock attribute"
    assert window.source_dock is not None
    assert window.dockWidgetArea(window.source_dock) == Qt.DockWidgetArea.RightDockWidgetArea

    # Verify links navigation routing
    assert window.synthesis_viewer.openExternalLinks() is False, "synthesis_viewer must not open links externally"
    assert window.sweep_report_viewer.openExternalLinks() is False, "sweep_report_viewer must not open links externally"

    # Add a mock doc to corpus and test double-click / citation click
    mock_doc = SourceDocument(
        cite_id=1,
        title="Test Citation Source",
        source_type="local_txt",
        path_or_uri="test.txt",
        content="Test content in source document 1.",
        word_count=6,
    )
    window.corpus.add_document(mock_doc)

    # Trigger citation click
    window.on_citation_clicked(QUrl("cite:1"))
    assert window.right_tabs.currentIndex() == 0

    # Trigger double click on source list
    window._open_source_inspector(1)
    assert window.source_dock.isVisible()
    assert "[1]" in window.source_dock.title_label.text()

    # Retranslate
    window.language_combo.setCurrentIndex(1)
    assert window.current_language == "ko"
    assert window.source_dock._lang == "ko"

    window.close()
    print("   -> MainWindow integration, docking, layout guards, and citation routing verified successfully!")


def main() -> None:
    print("=== OMNIRESEARCH STUDIO PASS 1 VERIFICATION SUITE ===")
    app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])

    test_markdown_and_citations()
    test_source_inspector_dock(app)
    test_audio_player_widget(app)
    test_neural_audio_synthesis()
    test_main_window_integration(app)

    print("\nALL PASS 1 TESTS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
