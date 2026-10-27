"""Headless Pre-Build Smoke Test Harness for OmniResearch Studio.

Executes core discovery, synthesis, token telemetry, and database persistence
without initializing a GUI window to verify pipeline health and detect any
thread lock or serialization regressions before compilation and release.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

# Enforce headless mode
os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def run_smoke_test() -> int:
    try:
        print("=== OMNIRESEARCH STUDIO PRE-BUILD HEADLESS SMOKE TEST ===")

        # 1. Initialize headless Qt core application if Qt is loaded
        try:
            from PyQt6.QtCore import QCoreApplication

            _qt_app = QCoreApplication.instance() or QCoreApplication(sys.argv)
        except ImportError:
            try:
                from PySide6.QtCore import QCoreApplication

                _qt_app = QCoreApplication.instance() or QCoreApplication(sys.argv)
            except ImportError:
                _qt_app = None

        # 2. Retrieve API Key
        print("[1/5] Verifying Gemini API Key retrieval...")
        from core.config_manager import ConfigManager

        cfg_mgr = ConfigManager()
        api_key = cfg_mgr.get_api_key() or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "No Gemini API key found in Windows Registry, user-space storage, or GEMINI_API_KEY environment."
            )
        print(f"   -> API Key detected (prefix: {api_key[:6]}..., length: {len(api_key)})")

        # 3. Instantiate Client & Verify HttpOptions
        print("[2/5] Creating GenAI Client with primitive 180s HttpOptions...")
        client = cfg_mgr.create_client(api_key=api_key)
        print("   -> Client created successfully.")

        # 4. Execute Discovery Agent (Phase 1 & Phase 2 Search Grounding)
        print("[3/5] Dispatching test discovery query ('Python asyncio architecture')...")
        from core.config import DEFAULT_PERSPECTIVES
        from core.storm_discovery import OmniSweepDiscoveryAgent, OmniSweepDiscoveryResult

        test_perspective = [DEFAULT_PERSPECTIVES[0]]  # Systems & Technical Architect
        agent = OmniSweepDiscoveryAgent(
            client=client,
            model_name="gemini-3.8-flash",
            deep_scrape=False,  # Headless fast-path
        )

        t_start = time.monotonic()
        discovery_result: OmniSweepDiscoveryResult = agent.run_discovery(
            topic="Python asyncio architecture",
            perspectives=test_perspective,
            corpus_summary="",
            progress_callback=lambda msg: print(f"      [Discovery Progress] {msg}"),
        )
        t_elapsed = time.monotonic() - t_start
        print(f"   -> Discovery finished in {t_elapsed:.1f}s.")
        print(f"   -> Perspectives explored: {len(discovery_result.perspective_reports)}")
        if not discovery_result.perspective_reports or not discovery_result.perspective_reports[0].analysis_markdown:
            raise RuntimeError("Discovery produced an empty perspective report!")
        print(f"   -> Perspective analysis chars: {len(discovery_result.perspective_reports[0].analysis_markdown)}")
        print(f"   -> Grounding citations retrieved: {len(discovery_result.perspective_reports[0].grounding_references)}")

        # 5. Execute Lightweight Grounded Synthesis
        print("[4/5] Executing grounded synthesis verification...")
        from core.document_loader import SourceDocument
        from core.notebook_synthesis import NotebookSynthesizer, SynthesisResult

        doc = SourceDocument(
            cite_id=1,
            title="Asyncio Architecture Perspective",
            source_type="web",
            path_or_uri="web://discovery_smoke_test",
            content=discovery_result.perspective_reports[0].analysis_markdown,
            enabled=True,
        )

        synthesizer = NotebookSynthesizer(
            client=client,
            model_name="gemini-3.8-flash",
        )
        synth_result: SynthesisResult = synthesizer.synthesize(
            query="Summarize Python asyncio architecture in 2 bullet points",
            documents=[doc],
            progress_callback=lambda msg: print(f"      [Synthesis Progress] {msg}"),
        )
        if not synth_result.markdown_report or len(synth_result.markdown_report.strip()) < 20:
            raise RuntimeError("Synthesis returned an empty or invalid report!")
        print(f"   -> Synthesis report produced ({len(synth_result.markdown_report)} chars).")

        # 6. Verify SQLite Database & Token Ledger Telemetry
        print("[5/5] Verifying SQLite database persistence & LocalAppData routing...")
        from core.database import DB_PATH, get_app_data_dir
        from core.token_ledger import TokenLedger

        app_data_dir = get_app_data_dir()
        db_file = Path(DB_PATH)
        print(f"   -> AppData Directory: {app_data_dir}")
        print(f"   -> Database Path: {db_file}")

        if not db_file.exists():
            raise FileNotFoundError(f"Database file was not created at expected path: {db_file}")

        ledger = TokenLedger.get_instance()
        rec = ledger.record_manual(
            model="gemini-3.8-flash",
            prompt_tokens=250,
            candidate_tokens=120,
            cached_tokens=50,
            session_id="smoke_test",
        )
        totals = ledger.get_session_totals(session_id="smoke_test")
        if totals.prompt_tokens < 250 or totals.candidate_tokens < 120:
            raise RuntimeError(f"Token ledger verification failed. Unexpected totals: {totals}")
        print(
            f"   -> Ledger record written and retrieved: {rec.model} | {totals.total_tokens} tokens | ${totals.total_cost_usd}"
        )

        # Verify no .sqlite files were generated in current working directory
        cwd_sqlite = list(Path(".").glob("*.sqlite*"))
        if cwd_sqlite:
            raise RuntimeError(f"SQLite artifacts leaked into project root / cwd: {cwd_sqlite}")
        print("   -> Workspace cleanliness verified: zero SQLite artifacts in working directory.")

        print("\n=======================================================")
        print("  ALL PRE-BUILD SMOKE TESTS PASSED CLEANLY (EXIT 0)    ")
        print("=======================================================")
        return 0

    except Exception:
        print("\n" + "=" * 60, file=sys.stderr)
        print(" [SMOKE TEST FAILURE DETECTED]", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_test())
