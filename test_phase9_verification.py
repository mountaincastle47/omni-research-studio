"""Phase 9 Comprehensive Verification Suite.

Tests:
1. Sandboxed Document Loader (OS Segfault Immunity & Timeout Recovery)
2. Media Loader (YouTube URL & Local Audio Transcription with <!--TIME:S--> anchors)
3. Academic Protocol Resolvers (ArXiv Atom XML & CrossRef DOI JSON Resolvers)
4. Interactive Causal Failure & Argument Graphs (Mermaid SVG Generation & CausalGraphWidget)
5. Temporal Milestone & Chronology Engine (Markdown Table Parsing & ChronologyTimelineWidget)
6. System Diagnostics Suite (6 Health Probes & DiagnosticDialog UI)
7. Full Workspace & MainWindow Phase 9 Integration
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["GEMINI_API_KEY"] = "mock_key_for_testing"

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication

from core.academic_resolver import (
    AcademicResolver,
    extract_arxiv_id,
    extract_doi,
    is_academic_identifier,
)
from core.diagnostics import DiagnosticResult, SystemDiagnostics
from core.document_loader import DocumentCorpus, SourceDocument
from core.graph_generator import parse_mermaid_code, render_mermaid_to_svg
from core.media_loader import (
    AUDIO_EXTENSIONS,
    MediaLoader,
    build_youtube_timestamp_url,
    extract_youtube_video_id,
    format_seconds_to_timestamp,
    is_youtube_url,
    parse_timestamp_to_seconds,
)
from core.sandbox_loader import SandboxedDocumentLoader
from core.timeline_parser import ChronologyMilestone, parse_chronology_table
from ui.diagnostic_dialog import DiagnosticDialog
from ui.graph_viewer import CausalGraphWidget
from ui.main_window import MainWindow
from ui.timeline_widget import ChronologyTimelineWidget
from ui.workspace_tabs import WorkspaceReportPane


class TestPhase9ResilienceAndIntelligence(unittest.TestCase):
    """Rigorous tests covering all Phase 9 architectural deliverables."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="omni_phase9_test_")
        self.test_dir = Path(self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Sandboxed Document Loader & Crash Immunity
    # -------------------------------------------------------------------------
    def test_01_sandbox_loader_valid_file(self) -> None:
        loader = SandboxedDocumentLoader.get_instance()
        test_file = self.test_dir / "sample.txt"
        test_file.write_text("Sandboxed process test line.", encoding="utf-8")

        res = loader.extract_document(test_file)
        self.assertTrue(res["success"])
        self.assertIn("Sandboxed process test line.", res["content"])
        self.assertEqual(res["page_count"], 1)
        self.assertFalse(res["crashed"])

    def test_02_sandbox_loader_timeout_recovery(self) -> None:
        loader = SandboxedDocumentLoader.get_instance()
        dummy_file = self.test_dir / "huge_hang.txt"
        dummy_file.write_text("Hang simulation", encoding="utf-8")

        from concurrent.futures.process import BrokenProcessPool
        mock_future = MagicMock()
        mock_future.result.side_effect = BrokenProcessPool("Process crashed")
        with patch.object(loader._get_executor(), "submit", return_value=mock_future):
            res = loader.extract_document(dummy_file, timeout_seconds=1.0)
            self.assertFalse(res["success"])
            self.assertTrue(res["crashed"])
            self.assertIn("Corrupted Native Binary/Bitmap", res["title"])

    def test_03_corpus_sandboxed_ingestion(self) -> None:
        corpus = DocumentCorpus()
        good_doc = self.test_dir / "valid.md"
        good_doc.write_text("# Chapter 1\nDeep intelligence architecture.", encoding="utf-8")

        doc = corpus.ingest_file(good_doc, use_sandbox=True)
        self.assertEqual(doc.cite_id, 1)
        self.assertIn("Deep intelligence architecture.", doc.content)
        self.assertTrue(doc.enabled)

    # -------------------------------------------------------------------------
    # 2. YouTube & Local Audio Media Loader
    # -------------------------------------------------------------------------
    def test_04_media_loader_youtube_url_detection(self) -> None:
        urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
        ]
        for u in urls:
            self.assertTrue(is_youtube_url(u))
            self.assertEqual(extract_youtube_video_id(u), "dQw4w9WgXcQ")

        self.assertFalse(is_youtube_url("https://vimeo.com/123456"))
        self.assertIsNone(extract_youtube_video_id("https://google.com"))

    def test_05_media_timestamp_helpers(self) -> None:
        self.assertEqual(format_seconds_to_timestamp(0), "00:00")
        self.assertEqual(format_seconds_to_timestamp(75), "01:15")
        self.assertEqual(format_seconds_to_timestamp(3665), "01:01:05")

        self.assertEqual(parse_timestamp_to_seconds("00:00"), 0)
        self.assertEqual(parse_timestamp_to_seconds("01:15"), 75)
        self.assertEqual(parse_timestamp_to_seconds("01:01:05"), 3665)

        for s in [0, 42, 128, 3600, 7320]:
            formatted = format_seconds_to_timestamp(s)
            parsed = parse_timestamp_to_seconds(formatted)
            self.assertEqual(parsed, s)

        self.assertEqual(
            build_youtube_timestamp_url("dQw4w9WgXcQ", 125),
            "https://youtu.be/dQw4w9WgXcQ?t=125",
        )

    def test_06_media_loader_youtube_ingestion(self) -> None:
        mock_segments = [
            {"start": 0.0, "duration": 4.5, "text": "Welcome to the research debrief."},
            {"start": 4.5, "duration": 5.0, "text": "Today we examine fault domains in distributed systems."},
        ]

        with patch.object(
            MediaLoader,
            "fetch_youtube_metadata",
            return_value={"title": "Distributed Systems Analysis", "author": "Tech Academy", "thumbnail": ""},
        ), patch.object(
            MediaLoader,
            "fetch_youtube_transcript",
            return_value=mock_segments,
        ):
            res = MediaLoader.ingest_youtube_url("https://youtu.be/dQw4w9WgXcQ")
            self.assertEqual(res["video_id"], "dQw4w9WgXcQ")
            self.assertIn("<!--TIME:0-->[00:00] Welcome to the research debrief.", res["content"])
            self.assertIn("<!--TIME:4-->[00:04] Today we examine fault domains", res["content"])

            corpus = DocumentCorpus()
            doc = corpus.ingest_youtube_url("https://youtu.be/dQw4w9WgXcQ")
            self.assertEqual(doc.source_type, "web_youtube")
            self.assertEqual(doc.cite_id, 1)
            self.assertIn("Distributed Systems Analysis", doc.title)

    # -------------------------------------------------------------------------
    # 3. Academic Protocol Resolvers (ArXiv & DOI)
    # -------------------------------------------------------------------------
    def test_07_academic_identifier_detection(self) -> None:
        self.assertTrue(is_academic_identifier("https://arxiv.org/abs/2301.12345"))
        self.assertEqual(extract_arxiv_id("https://arxiv.org/abs/2301.12345"), "2301.12345")
        self.assertEqual(extract_arxiv_id("arxiv:2403.09999v2"), "2403.09999v2")

        doi_url = "https://doi.org/10.1038/s41586-020-2649-2"
        self.assertTrue(is_academic_identifier(doi_url))
        self.assertEqual(extract_doi(doi_url), "10.1038/s41586-020-2649-2")
        self.assertEqual(extract_doi("doi: 10.1145/3318464.3389700"), "10.1145/3318464.3389700")

        self.assertFalse(is_academic_identifier("https://example.com/regular-page"))

    def test_08_academic_arxiv_resolution(self) -> None:
        mock_atom_xml = """<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>Attention Is All You Need</title>
            <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</summary>
            <published>2017-06-12T17:52:16Z</published>
            <author><name>Ashish Vaswani</name></author>
            <author><name>Noam Shazeer</name></author>
          </entry>
        </feed>"""

        class MockResponse:
            status_code = 200
            text = mock_atom_xml
            content = b"Mock PDF Binary Payload Greater than 1000 bytes " * 30

            def raise_for_status(self):
                pass

        with patch("requests.get", return_value=MockResponse()):
            res = AcademicResolver.resolve_arxiv("1706.03762", download_pdf=False)
            self.assertEqual(res["title"], "[ACADEMIC / PEER-REVIEWED] Attention Is All You Need")
            self.assertIn("Ashish Vaswani", res["authors"])
            self.assertEqual(res["year"], "2017")
            self.assertIn("The dominant sequence transduction models", res["abstract"])

            # Polymorphic resolve
            res_poly = AcademicResolver.resolve("https://arxiv.org/abs/1706.03762", download_pdf=False)
            self.assertEqual(res_poly["title"], res["title"])

    def test_09_academic_doi_resolution(self) -> None:
        mock_crossref = {
            "message": {
                "title": ["Deep Residual Learning for Image Recognition"],
                "author": [{"given": "Kaiming", "family": "He"}, {"given": "Xiangyu", "family": "Zhang"}],
                "published": {"date-parts": [[2016]]},
                "container-title": ["CVPR"],
                "publisher": ["IEEE"],
                "abstract": "<jats:p>Deeper neural networks are more difficult to train.</jats:p>",
            }
        }

        class MockDoiResponse:
            status_code = 200
            text = ""

            def json(self):
                return mock_crossref

            def raise_for_status(self):
                pass

        with patch("requests.get", return_value=MockDoiResponse()):
            res = AcademicResolver.resolve_doi("10.1109/CVPR.2016.90")
            self.assertEqual(res["title"], "[ACADEMIC / PEER-REVIEWED] Deep Residual Learning for Image Recognition")
            self.assertIn("Kaiming He", res["authors"])
            self.assertEqual(res["year"], "2016")
            self.assertIn("Deeper neural networks are more difficult to train.", res["abstract"])

            corpus = DocumentCorpus()
            doc = corpus.ingest_academic("10.1109/CVPR.2016.90", download_pdf=False)
            self.assertEqual(doc.cite_id, 1)
            self.assertIn("Deep Residual Learning", doc.title)

    # -------------------------------------------------------------------------
    # 4. Interactive Causal Failure & Argument Graphs
    # -------------------------------------------------------------------------
    def test_10_mermaid_graph_parsing_and_svg(self) -> None:
        sample_mermaid = """
        graph TD
          A["Corrupted Ingestion Input [1]"] --> B{"Process Isolation Sandbox"}
          B -->|"Worker Crashes"| C["Isolated Fallback Document [2]"]
          B -->|"Extraction Normal"| D["Full Markdown Pipe Tables [3]"]
        """

        parsed = parse_mermaid_code(sample_mermaid)
        self.assertEqual(parsed.direction, "TD")
        self.assertGreaterEqual(len(parsed.nodes), 4)
        self.assertTrue(any(n.node_id == "A" for n in parsed.nodes.values()))
        self.assertTrue(any(n.node_id == "C" for n in parsed.nodes.values()))

        svg = render_mermaid_to_svg(sample_mermaid)
        self.assertIn("<svg", svg)
        self.assertIn("</svg>", svg)
        self.assertIn('xlink:href="node:A"', svg)
        self.assertIn('xlink:href="node:C"', svg)

    def test_11_causal_graph_widget(self) -> None:
        widget = CausalGraphWidget(lang="en")
        report_text = """
        # Grounded Research Synthesis

        ```mermaid
        graph LR
          Node1["Root Cause Vector [1]"] --> Node2["Secondary Failure Cascade [2]"]
          Node2 --> Node3["Mitigation via Process Sandboxing [3]"]
        ```
        """
        widget.set_markdown_report(report_text)
        self.assertIsNotNone(widget.svg_content)
        self.assertIn("Root Cause Vector", widget.svg_content)

        clicked_cites = []
        widget.citation_clicked.connect(lambda url: clicked_cites.append(url.toString()))
        widget._on_anchor_clicked(QUrl("cite:1"))
        self.assertEqual(clicked_cites, ["cite:1"])

    # -------------------------------------------------------------------------
    # 5. Temporal Milestone & Chronology Engine
    # -------------------------------------------------------------------------
    def test_12_timeline_parser_table(self) -> None:
        sample_md = """
        # Section 4: Chronology of Incidents

        | Date / Period | Historical Event / Action | Outcome / State Change | Sources |
        | :--- | :--- | :--- | :--- |
        | 2024-03-15 | Firmware deployment across primary edge gateways | Cascading memory pressure and buffer overrun [1] | [1] |
        | 2024-03-16 04:30 | Automated rollback trigger engaged | Subsystem telemetry restored to baseline [2] | [2:p.4] |
        | 2024-03-20 | Zero-day patch verified in test cluster | Final verification sign-off [3] | [3] |
        """

        milestones = parse_chronology_table(sample_md)
        self.assertEqual(len(milestones), 3)

        self.assertEqual(milestones[0].date_str, "2024-03-15")
        self.assertIn("Firmware deployment", milestones[0].event_title)
        self.assertIn("buffer overrun", milestones[0].outcome_desc)
        self.assertEqual(milestones[0].citations, ["[1]"])

        self.assertEqual(milestones[1].date_str, "2024-03-16 04:30")
        self.assertIn("Automated rollback", milestones[1].event_title)
        self.assertEqual(milestones[1].citations, ["[2:p.4]"])

    def test_13_chronology_timeline_widget(self) -> None:
        widget = ChronologyTimelineWidget(lang="en")
        sample_md = """
        | Date / Period | Historical Event / Action | Outcome / State Change | Sources |
        | :--- | :--- | :--- | :--- |
        | 2020-01-01 | Architecture Design Inception | Baseline draft established [1] | [1] |
        | 2022-05-10 | Production Launch | Scale exceeded initial targets [2] | [2] |
        """
        widget.set_markdown_report(sample_md)
        self.assertEqual(len(widget.milestones), 2)
        self.assertEqual(widget.count_badge.text(), "2 milestones")

        # Test real-time filter
        widget.filter_input.setText("Production")
        visible_cards = [c for c in widget.cards if not c.isHidden()]
        self.assertEqual(len(visible_cards), 1)
        self.assertIn("Production Launch", visible_cards[0].milestone.event_title)

        # Clear filter
        widget.filter_input.setText("")
        visible_cards_all = [c for c in widget.cards if not c.isHidden()]
        self.assertEqual(len(visible_cards_all), 2)

    # -------------------------------------------------------------------------
    # 6. System Diagnostics Health Suite & Dialog UI
    # -------------------------------------------------------------------------
    def test_14_system_diagnostics_suite(self) -> None:
        from core.config import ConfigManager
        cfg = ConfigManager()
        results = SystemDiagnostics.run_all_diagnostics(cfg)

        self.assertEqual(len(results), 6)
        subsystems = {r.subsystem_id for r in results}
        expected_subsystems = {
            "genai_api",
            "local_llm",
            "audio_devices",
            "neural_tts",
            "ocr_engine",
            "sqlite_storage",
        }
        self.assertEqual(subsystems, expected_subsystems)

        for r in results:
            self.assertIsInstance(r, DiagnosticResult)
            self.assertIn(r.status, ("PASS", "WARN", "FAIL"))
            self.assertGreater(len(r.details), 0)

        storage_res = next(r for r in results if r.subsystem_id == "sqlite_storage")
        self.assertEqual(storage_res.status, "PASS")

    def test_15_diagnostic_dialog_ui(self) -> None:
        from core.config import ConfigManager
        cfg = ConfigManager()
        dlg = DiagnosticDialog(config_manager=cfg, lang="en")
        self.assertEqual(dlg.windowTitle(), "OmniResearch System Health Diagnostics")
        self.assertEqual(dlg.results_table.rowCount(), 6)
        dlg.close()

    # -------------------------------------------------------------------------
    # 7. Full MainWindow Phase 9 Integration
    # -------------------------------------------------------------------------
    def test_16_main_window_phase9_integration(self) -> None:
        window = MainWindow()

        # 1. Verify Help menu & Diagnostics action
        self.assertTrue(hasattr(window, "help_menu"))
        self.assertTrue(hasattr(window, "action_diagnostics"))
        self.assertEqual(window.action_diagnostics.text(), "System Health Check...")

        # 2. Verify Workspace Tabs have Causal Graph (Tab 2) & Chronology (Tab 3)
        active_pane = window.active_workspace_pane
        self.assertIsInstance(active_pane, WorkspaceReportPane)
        self.assertGreaterEqual(active_pane.inner_tabs.count(), 4)
        self.assertEqual(active_pane.inner_tabs.tabText(2), "Causal Graph")
        self.assertEqual(active_pane.inner_tabs.tabText(3), "Chronology")

        # 3. Test timestamp citation navigation
        window.corpus.clear()
        doc_yt = SourceDocument(
            cite_id=1,
            title="[YOUTUBE TRANSCRIPT] Distributed Systems Talk",
            source_type="web_youtube",
            path_or_uri="https://youtu.be/dQw4w9WgXcQ",
            content="<!--PAGE_START:1-->\n<!--TIME:120-->[02:00] Quorum consensus protocol description",
            word_count=50,
            page_count=1,
        )
        window.corpus._documents.append(doc_yt)

        with patch("PyQt6.QtGui.QDesktopServices.openUrl") as mock_open_url:
            window.on_citation_clicked(QUrl("cite:1:time:02:00"))
            self.assertTrue(mock_open_url.called)
            called_url = mock_open_url.call_args[0][0].toString()
            self.assertTrue("youtu.be/dQw4w9WgXcQ?t=120s" in called_url or "youtu.be/dQw4w9WgXcQ&t=120s" in called_url)

        # 4. Test active workspace pane update_synthesis_views
        sample_report = """
        # Advanced System Analysis

        ```mermaid
        graph TD
          A["High Network Latency [1]"] --> B["Node Partition [1]"]
        ```

        | Date / Period | Historical Event / Action | Outcome / State Change | Sources |
        | :--- | :--- | :--- | :--- |
        | 2024-01-10 | Network Switch Outage | Partition triggered [1] | [1] |
        """

        active_pane.update_synthesis_views(sample_report)
        self.assertIsNotNone(active_pane.causal_graph_viewer.svg_content)
        self.assertEqual(len(active_pane.chronology_viewer.milestones), 1)

        window.close()


if __name__ == "__main__":
    unittest.main()
