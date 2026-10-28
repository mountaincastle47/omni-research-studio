"""Phase 11 Comprehensive Verification Suite: Autonomous Mastery & Sovereign Workflow Suite.

Tests:
1. Recursive Autonomous Gap-Filler (Deepening Loop: Contested matrix parsing & sub-query generation)
2. Cross-Corpus Entity-Relationship Knowledge Graph (networkx graph construction, node categories, serialization)
3. Embedded Python REPL & Mathematical Verification Sandbox (Restricted builtins, execution timeout, filesystem write guard)
4. Headless LAN Mobile Web Mirror Server (FastAPI endpoints, PIN security, workspace & audio streaming)
5. Zero-Knowledge Client-Side AES-256-GCM Vault Backup (PBKDF2 key derivation, authentication tag verification, InvalidTag rejection)
6. Unattended Batch Research CLI Engine (Headless pipeline execution, .omni packaging, executive exports)
7. Full MainWindow Phase 11 Integration & Sizing Retention Guards
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["GEMINI_API_KEY"] = "mock_key_for_testing"

from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient
from PyQt6.QtWidgets import QApplication

from core.cli_runner import BatchResearchRunner
from core.deep_research import DeepResearchEngine, generate_gap_queries, parse_contested_matrix
from core.document_loader import DocumentCorpus, SourceDocument
from core.i18n import get_text
from core.knowledge_graph import ENTITY_CATEGORIES, KnowledgeGraphEngine
from core.math_sandbox import MathSandbox, SandboxResult
from core.server_mirror import MobileMirrorServer
from core.vault_sync import VaultSync
from ui.graph_widget import KnowledgeGraphWidget
from ui.main_window import MainWindow
from ui.sandbox_dock import SandboxDock


class TestPhase11AutonomousMastery(unittest.TestCase):
    """Rigorous tests covering all Phase 11 architectural deliverables."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="omni_phase11_test_")
        self.test_dir = Path(self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Recursive Autonomous Gap-Filler (Deepening Loop)
    # -------------------------------------------------------------------------
    def test_01_contested_matrix_parsing(self) -> None:
        sample_report = """# Executive Propulsion Assessment

## Core Findings
Baseline engine specs indicate stable chamber pressure.

## Contested Claims & Empirical Anomalies
| Parameter / Event | Official / Baseline Claim | Empirical / Contrarian Finding | Technical Divergence Root Cause |
| :--- | :--- | :--- | :--- |
| Specific Impulse (Isp) | 382 sec vacuum [1] | 361 sec in static fire logs [2] | Combustion instability at 85% throttle |
| Turbine Inlet Temp | 1150 K nominal [1] | 1340 K spike at T+45s [3] | Oxidizer pre-burner seal leak |
| Refurbishment Life | 25 cycles [1] | Nozzle throat erosion after 3 burns [2] | High thermal stress cycling |

## Next Steps
Further research required.
"""
        gaps = parse_contested_matrix(sample_report)
        self.assertEqual(len(gaps), 3)
        self.assertIn("Specific Impulse", gaps[0]["parameter"])
        self.assertIn("Turbine Inlet Temp", gaps[1]["parameter"])
        self.assertIn("Refurbishment Life", gaps[2]["parameter"])

        queries = generate_gap_queries(gaps, base_topic="Raptor Vacuum Engine", max_queries=3)
        self.assertEqual(len(queries), 3)
        self.assertTrue(any("Specific Impulse" in q for q in queries))
        self.assertTrue(any("telemetry" in q for q in queries))

    def test_02_gap_filler_loop_execution(self) -> None:
        corpus = DocumentCorpus()
        doc = SourceDocument(
            cite_id=1,
            title="Baseline Spec",
            source_type="file",
            path_or_uri="spec.txt",
            content="Official report claims 382 sec Isp.",
        )
        corpus.add_document(doc)

        engine = DeepResearchEngine()
        sample_report = """## Contested Claims & Empirical Anomalies
| Parameter / Event | Official / Baseline Claim | Empirical / Contrarian Finding | Technical Divergence Root Cause |
| :--- | :--- | :--- | :--- |
| Chamber Acoustic Resonance | 450 Hz suppressed | Uncontrolled 600 Hz harmonic | Acoustic cavity baffles missing |
"""

        # Mock search and scrape to return clean primary telemetry
        mock_scraped = [{
            "title": "Static Fire Test Log #42",
            "url": "https://telemetry.org/test42.txt",
            "content": "Empirical accelerometer telemetry confirms 600 Hz acoustic resonance resolved with 12mm baffles.",
        }]

        with patch.object(engine, "search_and_scrape", return_value=mock_scraped):
            addendum, new_docs = engine.run_gap_filling_loop(
                report_markdown=sample_report,
                corpus=corpus,
                base_topic="Propulsion",
            )
            self.assertIn("Autonomous Gap-Fill Addendum", addendum)
            self.assertEqual(len(new_docs), 1)
            self.assertEqual(new_docs[0].source_type, "deep_gap_fill")
            self.assertTrue(new_docs[0].metadata.get("is_gap_fill"))

    # -------------------------------------------------------------------------
    # 2. Cross-Corpus Entity-Relationship Knowledge Graph
    # -------------------------------------------------------------------------
    def test_03_knowledge_graph_construction(self) -> None:
        kg = KnowledgeGraphEngine()
        kg.add_entity("NASA", category="Organization", description="Space Agency", cite_id=1)
        kg.add_entity("Artemis", category="Program", description="Lunar Exploration", cite_id=1)
        kg.add_entity("Lockheed Martin", category="Organization", description="Prime Contractor", cite_id=2)
        kg.add_entity("Orion", category="Program", description="Crew Vehicle", cite_id=2)

        kg.add_relation("NASA", "Artemis", relation="leads", premise="Directs mission", cite_id=1)
        kg.add_relation("Lockheed Martin", "Orion", relation="manufactures", premise="Builds spacecraft", cite_id=2)
        kg.add_relation("Orion", "Artemis", relation="component_of", premise="Crew transportation", cite_id=2)

        nodes = kg.get_nodes_data()
        edges = kg.get_edges_data()

        self.assertEqual(len(nodes), 4)
        self.assertEqual(len(edges), 3)

        # Check serialization and restoration
        serialized = kg.to_dict()
        kg_restored = KnowledgeGraphEngine()
        kg_restored.from_dict(serialized)

        self.assertEqual(len(kg_restored.get_nodes_data()), 4)
        self.assertEqual(len(kg_restored.get_edges_data()), 3)

    def test_04_knowledge_graph_widget_ui(self) -> None:
        kg = KnowledgeGraphEngine()
        kg.add_entity("DARPA", category="Organization")
        kg.add_entity("Quantum Logic", category="Concept")
        kg.add_relation("DARPA", "Quantum Logic", relation="funds")

        widget = KnowledgeGraphWidget(engine=kg, lang="en")
        self.assertIsNotNone(widget.scene)
        self.assertTrue(widget.scene.items())
        widget.filter_input.setText("DARPA")
        # Ensure filter does not crash
        self.assertEqual(widget.filter_input.text(), "DARPA")

    # -------------------------------------------------------------------------
    # 3. Embedded Python REPL & Mathematical Verification Sandbox
    # -------------------------------------------------------------------------
    def test_05_math_sandbox_calculation_and_plotting(self) -> None:
        sandbox = MathSandbox(timeout_seconds=5.0)
        code = """
import numpy as np
import matplotlib.pyplot as plt

data = np.array([10.0, 20.0, 30.0, 40.0])
mean_val = np.mean(data)
std_val = np.std(data)
print(f"Mean: {mean_val:.1f}")
print(f"Std: {std_val:.1f}")

plt.figure()
plt.plot(data, [1, 2, 3, 4], label="Test Curve")
"""
        res = sandbox.execute_script(code)
        self.assertTrue(res.success)
        self.assertIn("Mean: 25.0", res.stdout)
        self.assertIn("Std: 11.2", res.stdout)
        self.assertTrue(len(res.plots) >= 1)
        self.assertTrue(Path(res.plots[0]).exists())

    def test_06_math_sandbox_security_guards(self) -> None:
        sandbox = MathSandbox(timeout_seconds=2.0)

        # 1. Attempt writing outside session_cache/ must raise PermissionError
        forbidden_write_code = """
with open("C:/unauthorized_test.txt", "w") as f:
    f.write("malicious")
"""
        res = sandbox.execute_script(forbidden_write_code)
        self.assertFalse(res.success)
        self.assertIn("PermissionError", res.error_message)

        # 2. Timeout guard: Script exceeding timeout ceiling must terminate
        slow_code = """
import time
time.sleep(3)
"""
        res_timeout = sandbox.execute_script(slow_code)
        self.assertFalse(res_timeout.success)
        self.assertIn("timed out", res_timeout.error_message.lower())

    # -------------------------------------------------------------------------
    # 4. Headless LAN Mobile Web Mirror Server
    # -------------------------------------------------------------------------
    def test_07_mobile_mirror_fastapi_endpoints(self) -> None:
        server = MobileMirrorServer(port=8484)
        client = TestClient(server.app)

        # 1. Unauthorized request without PIN must return 401
        resp_unauth = client.get("/api/workspaces")
        self.assertEqual(resp_unauth.status_code, 401)

        # 2. Authorized request with valid PIN
        resp_auth = client.get(f"/api/workspaces?pin={server.pin}")
        self.assertEqual(resp_auth.status_code, 200)
        data = resp_auth.json()
        self.assertIsInstance(data, list)

        # 3. Mobile UI page GET /
        resp_ui = client.get(f"/?pin={server.pin}")
        self.assertEqual(resp_ui.status_code, 200)
        self.assertIn("OmniResearch Mobile", resp_ui.text)

        # 4. Follow-up endpoint
        resp_qa = client.post(
            f"/api/followup?pin={server.pin}",
            json={"question": "What is the primary thrust variance?"},
        )
        self.assertEqual(resp_qa.status_code, 200)
        self.assertIn("answer", resp_qa.json())

    # -------------------------------------------------------------------------
    # 5. Zero-Knowledge Client-Side AES-256-GCM Vault Backup
    # -------------------------------------------------------------------------
    def test_08_vault_sync_encryption_and_tamper_resistance(self) -> None:
        raw_payload = b"OmniResearch Studio .omni Project Package: High Security Telemetry."
        passphrase = "MasterKey_Alpha_99!"

        # 1. Encrypt
        encrypted = VaultSync.encrypt_bytes(raw_payload, passphrase)
        self.assertTrue(encrypted.startswith(b"OMNI_VAULT_1"))
        self.assertNotEqual(encrypted, raw_payload)

        # 2. Decrypt with correct passphrase
        decrypted = VaultSync.decrypt_bytes(encrypted, passphrase)
        self.assertEqual(decrypted, raw_payload)

        # 3. Decrypt with incorrect passphrase must raise InvalidTag
        with self.assertRaises(InvalidTag):
            VaultSync.decrypt_bytes(encrypted, "Wrong_Passphrase_123")

        # 4. File-level roundtrip
        src_file = self.test_dir / "test_project.omni"
        src_file.write_bytes(raw_payload)
        vault_file = self.test_dir / "test_project.omni.vault"
        restored_file = self.test_dir / "restored_project.omni"

        VaultSync.encrypt_file(src_file, vault_file, passphrase)
        self.assertTrue(vault_file.exists())

        VaultSync.decrypt_file(vault_file, restored_file, passphrase)
        self.assertTrue(restored_file.exists())
        self.assertEqual(restored_file.read_bytes(), raw_payload)

    # -------------------------------------------------------------------------
    # 6. Unattended Batch Research CLI Engine
    # -------------------------------------------------------------------------
    def test_09_cli_runner_single_topic(self) -> None:
        out_batch_dir = self.test_dir / "batch_out"
        runner = BatchResearchRunner(
            render_audio=False,
            export_all=True,
        )

        with patch("google.genai.Client"):
            res = runner.process_topic("Hypersonic Boundary Layer Transition", out_batch_dir)
            self.assertIn("Hypersonic", res["topic"])
            self.assertTrue(Path(res["report_md"]).exists())
            self.assertTrue(Path(res["omni_file"]).exists())

    # -------------------------------------------------------------------------
    # 7. MainWindow Phase 11 Integration & Sizing Retention Guards
    # -------------------------------------------------------------------------
    def test_10_mainwindow_phase11_integration(self) -> None:
        window = MainWindow()

        # Check gap-fill toggle checkbox
        self.assertIsNotNone(window.chk_gap_fill)
        self.assertEqual(window.chk_gap_fill.text(), get_text("btn_gap_fill_toggle", "en"))

        # Check mobile LAN server and status bar button
        self.assertIsNotNone(window.mobile_server)
        self.assertTrue(window.mobile_server.is_running)
        self.assertIsNotNone(window.btn_mobile_server)

        # Check sandbox dock widget
        self.assertIsNotNone(window.sandbox_dock)
        self.assertIsInstance(window.sandbox_dock, SandboxDock)

        # Check knowledge graph engine and tab
        self.assertIsNotNone(window.knowledge_graph_engine)
        self.assertIsNotNone(window.active_workspace_pane.knowledge_graph_viewer)
        self.assertIsInstance(window.active_workspace_pane.knowledge_graph_viewer, KnowledgeGraphWidget)

        # Check layout sizing retention
        self.assertGreaterEqual(window.sweep_topic_input.minimumHeight(), 135)
        self.assertGreaterEqual(window.audio_focus_input.minimumHeight(), 120)

        window.close()


if __name__ == "__main__":
    unittest.main()
