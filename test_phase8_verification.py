"""Phase 8 Verification Suite: Cognitive Dominance, Deep Telemetry, BM25 Pruning,
Figure Extraction, Streaming Markdown, Epistemic Critic, and State Checkpoints.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz  # PyMuPDF
from PIL import Image
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication

from core.context_pruner import ContextPruner, PrunedChunk
from core.critic_agent import CriticAgent, EntailmentVerdict
from core.document_loader import SourceDocument, load_pdf
from core.local_llm_client import LocalLLMClient, is_local_model
from core.notebook_synthesis import (
    NotebookSynthesizer,
    create_semantic_anchor_builder,
    sanitize_unclosed_markdown,
)
from core.project_manager import (
    ProjectState,
    WorkspaceTabState,
    create_checkpoint,
    list_checkpoints,
    load_project,
    restore_checkpoint,
    save_project,
)
from ui.components import CheckpointManagerDialog
from ui.streaming_renderer import StreamingMarkdownViewer, repair_streaming_markdown


class TestPhase8CognitiveDominance(unittest.TestCase):
    """Rigorous tests covering all Phase 8 architectural deliverables."""

    @classmethod
    def setUpClass(cls) -> None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="omni_phase8_test_")
        self.test_dir = Path(self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Mega-Corpora Hybrid BM25 Context Pruner
    # -------------------------------------------------------------------------
    def test_01_context_pruner_slicing_and_bm25_reduction(self) -> None:
        # Create a document spanning 3 pages
        p1 = "Alpha quantum superconducting state exhibits zero resistance below critical temperature."
        p2 = "Beta ceramic formulation requires high pressure annealing under argon atmosphere."
        p3 = "Gamma radiation shielding analysis shows high attenuation using tungsten composite."
        full_content = (
            f"<!--PAGE_START:1-->\n{p1}\n"
            f"<!--PAGE_START:2-->\n{p2}\n"
            f"<!--PAGE_START:3-->\n{p3}\n"
        )
        doc = SourceDocument(
            cite_id=1,
            title="Superconductivity Lab Report",
            path_or_uri="supercond.pdf",
            content=full_content,
            page_count=3,
        )

        pruner = ContextPruner(chunk_word_size=10, chunk_overlap=2)
        chunks = pruner.slice_document(doc)
        self.assertGreater(len(chunks), 0)
        # Verify page numbers were preserved
        page_nums = {c.page_num for c in chunks}
        self.assertTrue(1 in page_nums and 2 in page_nums and 3 in page_nums)

        # Build a large corpus exceeding threshold
        corpus: list[SourceDocument] = []
        for i in range(1, 6):
            filler = " ".join([f"metric_data_{j} calibration sample standard baseline" for j in range(2500)])
            target_topic = "Superconducting transition temperature was empirically measured at 93 Kelvin."
            c_text = f"<!--PAGE_START:1-->\n{filler}\n<!--PAGE_START:2-->\n{target_topic}\n<!--PAGE_START:3-->\n{filler}"
            corpus.append(
                SourceDocument(
                    cite_id=i,
                    title=f"Technical Journal Volume {i}",
                    path_or_uri=f"journal_{i}.pdf",
                    content=c_text,
                    page_count=3,
                )
            )

        # Test mode 'Off' -> no pruning
        pruned_docs, was_pruned, meta = pruner.prune(
            query="superconducting transition temperature Kelvin",
            documents=corpus,
            mode="Off",
        )
        self.assertFalse(was_pruned)
        self.assertEqual(len(pruned_docs), len(corpus))

        # Test mode 'Auto' with threshold override to trigger reduction
        pruned_docs, was_pruned, meta = pruner.prune(
            query="superconducting transition temperature Kelvin",
            documents=corpus,
            mode="Auto",
            threshold_override=1000,
            target_tokens=1500,
            top_k=15,
        )
        self.assertTrue(was_pruned)
        self.assertEqual(meta["status"], "pruned")
        self.assertLess(meta["pruned_tokens"], meta["original_tokens"])
        self.assertGreater(len(pruned_docs), 0)
        # Check that the most relevant sentence is present in the reconstructed docs
        found_target = any("93 Kelvin" in d.content for d in pruned_docs)
        self.assertTrue(found_target, "BM25 pruner should retain high-relevance query terms")

    # -------------------------------------------------------------------------
    # 2. Multi-Modal PDF Schematic & Figure Extractor
    # -------------------------------------------------------------------------
    def test_02_pdf_figure_extraction(self) -> None:
        pdf_path = self.test_dir / "diagram_test.pdf"

        # Create a PDF with PyMuPDF containing an embedded 200x200 red square image
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 50), "Figure 1 shows the experimental circuit topology.\n")

        # Create 200x200 PNG in memory
        img_temp = self.test_dir / "temp_box.png"
        img = Image.new("RGB", (200, 200), color="blue")
        img.save(str(img_temp), "PNG")

        # Insert image into PDF page
        rect = fitz.Rect(50, 80, 250, 280)
        page.insert_image(rect, filename=str(img_temp))
        page.insert_text((50, 310), "Empirical voltage characteristics match simulation [1:p.1].")
        doc.save(str(pdf_path))
        doc.close()

        # Load PDF using overhauled document_loader
        loaded = load_pdf(str(pdf_path))
        self.assertIn("content", loaded)
        self.assertIn("figures", loaded)
        figures = loaded["figures"]
        self.assertGreater(len(figures), 0, "Should extract embedded image >= 150x150")

        fig = figures[0]
        self.assertEqual(fig["page_num"], 1)
        self.assertTrue(Path(fig["file_path"]).exists())
        self.assertGreaterEqual(fig["width"], 150)
        self.assertGreaterEqual(fig["height"], 150)

        # Verify Figure anchor exists in Markdown
        self.assertIn("![Figure", loaded["content"])

    # -------------------------------------------------------------------------
    # 3. Live Incremental Streaming Markdown Renderer
    # -------------------------------------------------------------------------
    def test_03_streaming_markdown_viewer_and_repair(self) -> None:
        # Test repair function
        broken_code = "```python\ndef test():\n    return 42"
        repaired_code = repair_streaming_markdown(broken_code)
        self.assertTrue(repaired_code.endswith("\n```\n") or repaired_code.endswith("```\n"))

        broken_bold = "The **critical anomaly"
        repaired_bold = repair_streaming_markdown(broken_bold)
        self.assertTrue(repaired_bold.endswith("**"))

        broken_table = "| Col 1 | Col 2 |\n|---|---|\n| val 1 | val 2"
        repaired_table = repair_streaming_markdown(broken_table)
        self.assertTrue(repaired_table.strip().endswith("|"))

        # Test StreamingMarkdownViewer
        viewer = StreamingMarkdownViewer()
        viewer.append_chunk("# Heading\n\nLive **partial token")
        viewer.flush()
        html = viewer.toHtml()
        self.assertIn("Heading", html)

        # Test clickable citations and critic badges in anchor builder
        doc = SourceDocument(
            cite_id=1,
            title="Aviation Safety Record",
            path_or_uri="aviation.pdf",
            content="<!--PAGE_START:1-->\nEngine turbine failure occurred at 3000 hours runtime.",
            page_count=1,
        )

        critic_verdicts = {
            (1, 1): EntailmentVerdict(
                cite_id=1,
                page_num=1,
                claim_sentence="Engine turbine failure occurred prematurely.",
                source_excerpt="Engine turbine failure occurred at 3000 hours runtime.",
                entails=True,
                confidence=0.95,
                critique="Directly supported by runtime logs.",
            ),
            (1, None): EntailmentVerdict(
                cite_id=1,
                page_num=None,
                claim_sentence="Engine was completely destroyed by lightning.",
                source_excerpt="No lightning events recorded.",
                entails=False,
                confidence=0.92,
                critique="Source explicitly refutes lightning damage.",
            ),
        }

        builder = create_semantic_anchor_builder([doc], critic_verdicts=critic_verdicts)
        # Verified anchor
        tag_verified = builder("1", "1", "Engine turbine failure occurred prematurely.")
        self.assertIn("cite-verified", tag_verified)
        self.assertIn("비평 검증됨", tag_verified)

        # Refuted anchor
        tag_refuted = builder("1", None, "Engine was completely destroyed by lightning.")
        self.assertIn("cite-refuted", tag_refuted)
        self.assertIn("비평 반박 경고", tag_refuted)

    # -------------------------------------------------------------------------
    # 4. Epistemic Entailment Critic Agent
    # -------------------------------------------------------------------------
    def test_04_epistemic_critic_agent(self) -> None:
        agent = CriticAgent()

        # Test borderline identification
        doc = SourceDocument(
            cite_id=2,
            title="Thermal Dynamics Study",
            path_or_uri="thermal.pdf",
            content="<!--PAGE_START:1-->\nFluid dynamics simulations indicate localized thermal convection currents under standard gravity.",
        )

        # Sentence with moderate lexical overlap
        report = "Thermal simulations observe convection dynamics [2:p.1]."
        borderlines = agent.identify_borderline_citations(report, [doc], lower_bound=0.01, upper_bound=0.90)
        self.assertGreater(len(borderlines), 0)
        self.assertEqual(borderlines[0]["cite_id"], 2)
        self.assertEqual(borderlines[0]["page_num"], 1)

        # Test parse_critic_json
        json_resp = '{"entails": false, "confidence": 0.88, "critique": "Contradicts primary temperature log."}'
        verdict = agent.parse_critic_json(
            json_resp, cite_id=2, page_num=1,
            claim_sentence="Claim", source_excerpt="Excerpt"
        )
        self.assertFalse(verdict.entails)
        self.assertEqual(verdict.confidence, 0.88)
        self.assertIn("Contradicts", verdict.critique)

        # Test heuristic fallback
        fallback = agent._heuristic_fallback(
            claim_sentence="convection dynamics",
            source_excerpt="localized thermal convection currents",
            cite_id=2,
            page_num=1,
        )
        self.assertTrue(fallback.entails)

    # -------------------------------------------------------------------------
    # 5. Zero-Egress Air-Gapped Local LLM Bridge
    # -------------------------------------------------------------------------
    def test_05_local_llm_client(self) -> None:
        self.assertTrue(is_local_model("ollama:llama3"))
        self.assertTrue(is_local_model("vllm:mistral-7b"))
        self.assertTrue(is_local_model("local:qwen2.5"))
        self.assertFalse(is_local_model("gemini-2.5-flash"))
        self.assertFalse(is_local_model("gemini-3.8-flash"))

        client = LocalLLMClient()
        url, model = client._resolve_url_and_model("ollama:llama3:latest")
        self.assertEqual(url, "http://localhost:11434/v1")
        self.assertEqual(model, "llama3:latest")

        url2, model2 = client._resolve_url_and_model("vLLM: deepseek-r1")
        self.assertEqual(url2, "http://localhost:8000/v1")
        self.assertEqual(model2, "deepseek-r1")

        # Mock streaming response
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = [
            'data: {"choices": [{"delta": {"content": "Local "}}]}',
            'data: {"choices": [{"delta": {"content": "air-gapped "}}]}',
            'data: {"choices": [{"delta": {"content": "synthesis."}}]}',
            'data: [DONE]',
        ]
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.stream.return_value.__enter__.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client):
            chunks = list(client.stream_chat("ollama:llama3", [{"role": "user", "content": "Hello"}]))
            self.assertEqual("".join(chunks), "Local air-gapped synthesis.")

    # -------------------------------------------------------------------------
    # 6. Research Branching & State Checkpoints (.omni Snapshots)
    # -------------------------------------------------------------------------
    def test_06_state_checkpoints_and_branching(self) -> None:
        project_path = self.test_dir / "research_project.omni"

        doc1 = SourceDocument(cite_id=1, title="Doc 1", path_or_uri="doc1.txt", content="Content 1")
        ws1 = WorkspaceTabState(
            tab_id="ws_1",
            title="Hypothesis Alpha",
            topic="Quantum Computing",
            query="Analyze coherence time",
            synthesis_original="Report 1 with [1]",
        )
        ws2 = WorkspaceTabState(
            tab_id="ws_2",
            title="Hypothesis Beta",
            topic="Topological Braiding",
            query="Majorana zero modes",
            synthesis_original="Report 2 with [1]",
        )

        state = ProjectState(
            documents=[doc1],
            active_tab_index=0,
            workspaces=[ws1, ws2],
            topic="Quantum Computing",
            query="Analyze coherence time",
            synthesis_original="Report 1 with [1]",
        )

        # Save base project archive
        save_project(state, project_path)
        self.assertTrue(project_path.exists())

        # Create Checkpoint 1
        cp1_id = create_checkpoint(
            project_path,
            state,
            name="Milestone Alpha",
            description="Initial coherence baseline analysis",
        )
        self.assertTrue(cp1_id.startswith("cp_"))

        # Modify state and create Checkpoint 2
        ws1.synthesis_original = "Updated Report 1 with improved metrics"
        cp2_id = create_checkpoint(
            project_path,
            state,
            name="Milestone Beta",
            description="Revised metrics after parameter sweep",
        )

        # List Checkpoints
        checkpoints = list_checkpoints(project_path)
        self.assertEqual(len(checkpoints), 2)
        self.assertEqual(checkpoints[0]["name"], "Milestone Alpha")
        self.assertEqual(checkpoints[1]["name"], "Milestone Beta")

        # Restore Checkpoint 1
        restored = restore_checkpoint(project_path, cp1_id)
        self.assertEqual(len(restored.workspaces), 2)
        self.assertEqual(restored.workspaces[0].synthesis_original, "Report 1 with [1]")

        # Test CheckpointManagerDialog
        dialog = CheckpointManagerDialog(checkpoints=checkpoints, lang="en")
        self.assertEqual(dialog.table.rowCount(), 2)

    # -------------------------------------------------------------------------
    # 7. MainWindow Headless Verification & Phase 8 UI Integration
    # -------------------------------------------------------------------------
    def test_07_main_window_headless_boot_and_phase8_controls(self) -> None:
        from core.config import ConfigManager
        from ui.main_window import MainWindow

        config_manager = ConfigManager()
        window = MainWindow(config_manager=config_manager)

        # Verify compression combo exists with correct items
        self.assertTrue(hasattr(window, "compression_combo"))
        self.assertEqual(window.compression_combo.currentText(), "Auto")
        items = [window.compression_combo.itemText(i) for i in range(window.compression_combo.count())]
        self.assertIn("Auto", items)
        self.assertIn("64k", items)
        self.assertIn("128k", items)
        self.assertIn("Off", items)

        # Verify airgap badge exists and is initially hidden
        self.assertTrue(hasattr(window, "airgap_badge"))
        self.assertTrue(window.airgap_badge.isHidden())

        # Toggle local model
        window.synthesis_model_combo.addItem("ollama:llama3")
        window.synthesis_model_combo.setCurrentText("ollama:llama3")
        self.assertFalse(window.airgap_badge.isHidden())

        # Switch back to cloud model
        window.synthesis_model_combo.setCurrentText("gemini-4-argon")
        self.assertTrue(window.airgap_badge.isHidden())

        # Verify checkpoints menu action
        self.assertTrue(hasattr(window, "action_checkpoints"))
        self.assertEqual(window.action_checkpoints.shortcut().toString(), "Ctrl+Shift+C")

        # Verify StreamingMarkdownViewer is used in active workspace pane
        active_pane = window.active_workspace_pane
        self.assertIsInstance(active_pane.synthesis_viewer, StreamingMarkdownViewer)

        # Verify bilingual retranslation
        window._on_language_changed(1)  # Switch to Korean
        self.assertEqual(window.current_language, "ko")
        self.assertIn("압축", window.compression_label.text())

        window.close()


if __name__ == "__main__":
    unittest.main()
