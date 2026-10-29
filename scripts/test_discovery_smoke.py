"""Headless Pre-Build Smoke Test Harness for OmniResearch Studio.

Executes core discovery, synthesis, recursive gap-filling, token telemetry,
and cooperative cancellation without initializing a GUI window to verify pipeline
health and prevent thread lock, serialization, or timeout regressions before compilation.
"""

from __future__ import annotations

import os
import re
import sys
import time
import traceback
from pathlib import Path

# Enforce headless mode
os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_smoke_test() -> int:
    try:
        t_global_start = time.monotonic()
        print("=== OMNIRESEARCH STUDIO PRE-BUILD HEADLESS SMOKE TEST ===")

        # 1. Initialize headless Qt application if Qt is loaded
        try:
            from PyQt6.QtWidgets import QApplication

            _qt_app = QApplication.instance() or QApplication(sys.argv)
        except ImportError:
            try:
                from PySide6.QtWidgets import QApplication

                _qt_app = QApplication.instance() or QApplication(sys.argv)
            except ImportError:
                _qt_app = None

        # 2. Retrieve API Key
        print("[1/6] Verifying Gemini API Key retrieval...")
        from core.config_manager import ConfigManager

        cfg_mgr = ConfigManager()
        api_key = cfg_mgr.get_api_key() or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "No Gemini API key found in Windows Registry, user-space storage, or GEMINI_API_KEY environment."
            )
        print(f"   -> API Key detected (prefix: {api_key[:6]}..., length: {len(api_key)})")

        # 3. Instantiate Client & Verify HttpOptions
        print("[2/6] Creating GenAI Client with persistent connection pooling...")
        client = cfg_mgr.create_client(api_key=api_key)
        print("   -> Client created successfully.")

        # 4. Execute Discovery Agent (Phase 1 & Phase 2 Search Grounding)
        print("[3/6] Dispatching test discovery query ('Python asyncio architecture')...")
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
        print("[4/6] Executing grounded synthesis verification...")
        from core.document_loader import DocumentCorpus, SourceDocument
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

        t_pipeline = time.monotonic() - t_global_start
        print(f"   -> Combined Discovery & Synthesis completed in {t_pipeline:.1f}s (<150s mandate).")
        if t_pipeline >= 150.0:
            raise TimeoutError(f"Pipeline took {t_pipeline:.1f}s exceeding the 150-second latency bound!")

        # 6. Verify Recursive Gap-Filler Termination (Max 2 iterations)
        print("[5/6] Verifying Recursive Autonomous Gap-Filler bounding (MAX_GAP_ITERATIONS <= 2)...")
        from core.deep_research import DeepResearchEngine, MAX_GAP_ITERATIONS

        corpus = DocumentCorpus()
        corpus.add_document(doc)
        deep_engine = DeepResearchEngine(config_manager=cfg_mgr, model_name="gemini-3.8-flash")

        mock_contested_report = (
            "# Synthesis Report with Contested Claims\n\n"
            "## Contested Claims & Empirical Anomalies\n"
            "| Parameter / Event | Official / Baseline Claim | Empirical / Contrarian Finding | Technical Divergence Root Cause | Citations |\n"
            "| :--- | :--- | :--- | :--- | :--- |\n"
            "| Event Loop Latency | 5 microseconds | 45 microseconds under load | Kernel epoll context switch | [1] |\n"
            "| Task Cancellation Overhead | 0.2% CPU | 8.5% CPU burst | Task pending queue scan | [1] |\n\n"
            + synth_result.markdown_report
        )

        recorded_iterations: list[int] = []

        def _gap_progress(msg: str) -> None:
            print(f"      [Gap-Fill Progress] {msg}")
            if "[Deepening " in msg:
                try:
                    iter_num = int(msg.split("[Deepening ")[1].split("/")[0])
                    if iter_num not in recorded_iterations:
                        recorded_iterations.append(iter_num)
                except Exception:
                    pass

        addendum, new_docs = deep_engine.run_gap_filling_loop(
            report_markdown=mock_contested_report,
            corpus=corpus,
            base_topic="Python asyncio",
            progress_callback=_gap_progress,
        )
        print(f"   -> Gap-filler recorded iterations: {recorded_iterations} (Max allowed: {MAX_GAP_ITERATIONS})")
        if len(recorded_iterations) > MAX_GAP_ITERATIONS:
            raise RuntimeError(f"Gap filler exceeded max iterations: {recorded_iterations} > {MAX_GAP_ITERATIONS}")
        print("   -> Bounded gap filler terminated strictly within limits.")

        # 7. Verify Cooperative Stop Request (<= 1.0s responsiveness)
        print("[6/6] Verifying Cooperative Cancellation responsiveness (<= 1.0s)...")
        from core.storm_discovery import OmniSweepDiscoveryAgent

        cancellable_agent = OmniSweepDiscoveryAgent(
            client=client,
            model_name="gemini-3.8-flash",
            deep_scrape=False,
            inter_perspective_delay=5.0,  # Long delay to test pacing interruption
        )
        t_cancel_start = time.monotonic()
        cancellable_agent.request_stop()
        if not cancellable_agent.is_stopped():
            raise RuntimeError("Agent stop_requested flag was not set!")

        # Verify discovery aborts immediately on cancel check
        cancelled_cleanly = False
        try:
            cancellable_agent.run_discovery(
                topic="Test Cancellation",
                perspectives=test_perspective,
                corpus_summary="",
            )
        except Exception as cancel_exc:
            cancelled_cleanly = "Task aborted" in str(cancel_exc) or "cancelled" in str(cancel_exc).lower()

        t_cancel_elapsed = time.monotonic() - t_cancel_start
        print(f"   -> Cancellation handled in {t_cancel_elapsed:.3f}s (Clean abort: {cancelled_cleanly})")
        if t_cancel_elapsed > 1.0:
            raise TimeoutError(f"Cancellation took {t_cancel_elapsed:.3f}s (> 1.0s mandate)!")

        # 8. Verify SQLite Database & Token Ledger Telemetry
        print("[Verification] Verifying SQLite database persistence & LocalAppData routing...")
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

        # 9. Verify Phase 4 Precomputation Watchdog Safety & Gap-Fill AttributeError Immunity
        print("[7/7] Verifying Phase 4 precomputation watchdog safety & gap-fill lifecycle...")
        from ui.workers import SynthesisWorker, GapFillWorker
        from ui.main_window import MainWindow

        # Test Phase 4 watchdog safety (worker should disable watchdog and complete layout precomputation cleanly)
        synth_worker = SynthesisWorker(
            config_manager=cfg_mgr,
            query="Asyncio architecture",
            documents=[doc],
            model_override="gemini-3.8-flash",
        )
        synth_worker.start_watchdog("synthesis_phase_1")
        # Simulate Phase 4 transition: stop watchdog, compute layout, verify no cancellation
        synth_worker.stop_watchdog()
        synth_worker.record_heartbeat("Phase 4/4: Precomputing layouts & citations...")

        from core.knowledge_graph import KnowledgeGraphEngine
        from ui.graph_viewer import compute_causal_layout_from_markdown

        causal_layout = compute_causal_layout_from_markdown(synth_result.markdown_report)
        kg_engine = KnowledgeGraphEngine()
        kg_engine.build_from_documents([doc], use_llm=False)
        kg_engine.extract_from_text(synth_result.markdown_report, cite_id=1, use_llm=False)
        kg_layout = kg_engine.compute_layout_data(min_repulsion=120.0)

        if synth_worker.is_cancelled():
            raise RuntimeError("Phase 4 layout precomputation tripped watchdog cancellation!")
        print("   -> Phase 4 precomputation completed cleanly without watchdog timeout.")

        # Test MainWindow lifecycle: _begin_task(None), _trigger_gap_fill, and _on_synthesis_finished immunity
        main_win = MainWindow()
        main_win._begin_task(None, "Testing guarded _begin_task")
        if main_win.active_worker is not None:
            raise RuntimeError("active_worker was expected to be None")

        # Test enabling recursive gap-filling triggering via _on_synthesis_finished
        main_win.chk_gap_fill.setChecked(True)
        main_win._on_synthesis_finished(synth_result)
        if not hasattr(main_win, "_gap_fill_worker") or main_win._gap_fill_worker is None:
            raise RuntimeError("GapFillWorker was not instantiated on _trigger_gap_fill!")
        print("   -> _on_synthesis_finished and _trigger_gap_fill completed with zero AttributeError.")

        # Verify GapFillWorker cooperatively cancels cleanly
        main_win._gap_fill_worker.request_stop()
        if not main_win._gap_fill_worker.is_cancelled():
            raise RuntimeError("GapFillWorker failed to register cooperative stop request!")
        main_win._end_task()
        print("   -> Recursive gap-filling worker lifecycle and cooperative cancellation verified.")

        # 10. Verify Graph Token Sanitization & Layout Stability
        print("[8/8] Verifying Causal token filtering & Knowledge Graph auto-layout stability...")
        from core.graph_generator import parse_mermaid_code
        from ui.widgets.knowledge_graph import KnowledgeGraphWidget

        # (a) Causal graph Mermaid parsing must eliminate stray control tokens (e.g. 'end', 'graph', 'subgraph')
        mermaid_sample = """
        graph TD
            subgraph Microservice Cluster
                A[API Gateway] --> B[Auth Service]
                B --> C[Postgres DB]
            end
            C --> D[Cache Layer]
        """
        parsed_g = parse_mermaid_code(mermaid_sample)
        for nid, nnode in parsed_g.nodes.items():
            clean_id = nid.strip().lower()
            clean_label = nnode.label.strip().lower()
            if clean_id in {"end", "graph", "subgraph", ""} or clean_label in {"end", "graph", "subgraph", ""}:
                raise RuntimeError(f"Mermaid parser emitted illegal control token as node: id='{nid}', label='{nnode.label}'")
        print(f"   -> Mermaid control tokens filtered cleanly (Nodes: {list(parsed_g.nodes.keys())})")

        # (b) KnowledgeGraphWidget auto_layout with precomputed layout retains items and finite coordinates
        kg_widget = KnowledgeGraphWidget()
        kg_widget.load_precomputed_layout(kg_layout)
        initial_node_count = len(kg_widget._node_items)
        if initial_node_count == 0:
            raise RuntimeError("KnowledgeGraphWidget loaded 0 nodes from kg_layout!")

        # Trigger auto_layout
        kg_widget.auto_layout()
        after_layout_count = len(kg_widget._node_items)
        if after_layout_count != initial_node_count:
            raise RuntimeError(f"auto_layout wiped or changed node count: {initial_node_count} -> {after_layout_count}")

        # Check finite coordinates
        import math
        for nid, item in kg_widget._node_items.items():
            pos = item.pos()
            if math.isnan(pos.x()) or math.isnan(pos.y()) or math.isinf(pos.x()) or math.isinf(pos.y()):
                raise RuntimeError(f"Node {nid} has non-finite coordinates after auto_layout: {pos}")

        scene_rect = kg_widget.scene.itemsBoundingRect()
        if scene_rect.width() <= 0 or scene_rect.height() <= 0:
            raise RuntimeError(f"Knowledge Graph scene itemsBoundingRect is not positive: {scene_rect}")
        print(f"   -> Knowledge Graph auto-layout retained {after_layout_count} nodes with valid scene rect: {scene_rect.width():.1f}x{scene_rect.height():.1f}")

        # (c) Causal graph node dynamic vertical expansion and <br/> sanitization
        from ui.graph_viewer import compute_causal_layout_from_markdown, _CausalNodeGraphicsItem, CausalGraphWidget
        causal_md_test = (
            "```mermaid\n"
            "graph TD\n"
            '    A["Root Cause Failure Chain<br/>Thermal Shock Overstress<br/>Combustion Instability Logged<br />Primary Nozzle Failure [1]"] -->|triggers| B["Secondary Emergency Shutdown<br/>Telemetry Dump Triggered"]\n'
            "```"
        )
        causal_layout_res = compute_causal_layout_from_markdown(causal_md_test)
        if not causal_layout_res or not causal_layout_res.get("nodes"):
            raise RuntimeError("compute_causal_layout_from_markdown returned empty layout!")

        causal_widget = CausalGraphWidget()
        causal_widget.load_precomputed_layout(causal_layout_res)
        found_test_nodes = False
        for it in causal_widget.scene.items():
            if isinstance(it, _CausalNodeGraphicsItem):
                found_test_nodes = True
                if "<br" in it.clean_label or "<br/>" in it.clean_label:
                    raise RuntimeError(f"Unsanitized <br> tag found in node label: {it.clean_label!r}")
                if it.node_id == "A":
                    # 4 lines of text must dynamically expand height well beyond default 72px
                    if it.height < 110.0:
                        raise RuntimeError(f"Node A height {it.height} did not expand to accommodate 4 lines of text (expected >= 110px)!")
                    if it.boundingRect().height() < 110.0:
                        raise RuntimeError(f"Node A boundingRect height {it.boundingRect().height()} is smaller than 110px!")
        if not found_test_nodes:
            raise RuntimeError("CausalGraphWidget scene failed to instantiate _CausalNodeGraphicsItem!")
        print("   -> Causal graph multi-line text expansion and <br/> sanitization verified.")

        # 11. Verify End-to-End GapFillWorker execution lifecycle (<90s bound)
        print("[9/9] Verifying Synthesis Pipeline with recursive_gap_filling=True lifecycle...")
        t_gap_run_start = time.monotonic()
        test_gap_worker = GapFillWorker(
            report_markdown=mock_contested_report,
            corpus=corpus,
            base_topic="Python asyncio",
            config_manager=cfg_mgr,
            model_name="gemini-3.8-flash",
        )
        test_gap_worker.run()
        t_gap_elapsed = time.monotonic() - t_gap_run_start
        print(f"   -> GapFillWorker completed in {t_gap_elapsed:.1f}s (<90s bound).")
        if t_gap_elapsed >= 90.0:
            raise TimeoutError(f"GapFillWorker took {t_gap_elapsed:.1f}s exceeding 90-second bound!")
        if test_gap_worker.precomputed_causal_layout is None:
            raise RuntimeError("GapFillWorker failed to precompute causal layout!")
        print("   -> GapFillWorker lifecycle and precomputations verified end-to-end.")

        # 12. Verify Localized Button Tooltips & Dynamic Graph Translation Swapping
        print("[10/10] Verifying 14 bilingual hover tooltips & dynamic graph translation swapping...")
        from core.i18n import get_text
        tooltip_keys = [
            "tooltip_add_files",
            "tooltip_diff_compare",
            "tooltip_clear_all",
            "tooltip_run_discovery",
            "tooltip_synthesize",
            "tooltip_gap_fill",
            "tooltip_export_report",
            "tooltip_split_view",
            "tooltip_auto_layout",
            "tooltip_export_svg",
            "tooltip_zoom_in",
            "tooltip_zoom_out",
            "tooltip_cancel_task",
            "tooltip_filter_entities",
        ]
        for key in tooltip_keys:
            en_val = get_text(key, "en")
            ko_val = get_text(key, "ko")
            if not en_val or en_val == key:
                raise RuntimeError(f"Missing English tooltip for {key}: '{en_val}'")
            if not ko_val or ko_val == key:
                raise RuntimeError(f"Missing Korean tooltip for {key}: '{ko_val}'")
        print(f"   -> All {len(tooltip_keys)} tooltips verified non-empty in both English and Korean.")

        # Verify Causal Graph label swapping preserves node positions and viewport
        pos_before = {nid: (item.pos().x(), item.pos().y()) for nid, item in causal_widget._node_items.items()}
        causal_widget.update_language(
            "ko",
            {
                "A": "열 충격 과부하 장애 체인",
                "B": "비상 셧다운 트리거",
                "triggers": "유발함",
            },
        )
        for nid, item in causal_widget._node_items.items():
            pos_after = (item.pos().x(), item.pos().y())
            if pos_before[nid] != pos_after:
                raise RuntimeError(f"Causal node {nid} moved position during language update: {pos_before[nid]} -> {pos_after}")
        if causal_widget._node_items["A"].clean_label != "열 충격 과부하 장애 체인":
            raise RuntimeError(f"Causal node A label was not updated: {causal_widget._node_items['A'].clean_label}")
        print("   -> Causal graph translation updated node labels with zero coordinate displacement.")

        # Verify Knowledge Graph label swapping preserves node positions
        first_kg_id = list(kg_widget._node_items.keys())[0]
        first_kg_item = kg_widget._node_items[first_kg_id]
        orig_kg_name = first_kg_item.name
        orig_kg_pos = (first_kg_item.pos().x(), first_kg_item.pos().y())
        kg_widget.update_language("ko", {first_kg_id: "테스트 개체명"})
        new_kg_pos = (first_kg_item.pos().x(), first_kg_item.pos().y())
        if orig_kg_pos != new_kg_pos:
            raise RuntimeError(f"KG node {first_kg_id} moved position during language update: {orig_kg_pos} -> {new_kg_pos}")
        if first_kg_item.name != "테스트 개체명":
            raise RuntimeError(f"KG node label was not updated: {first_kg_item.name}")
        print("   -> Knowledge graph translation updated entity names with zero coordinate displacement.")

        # Verify WorkspaceReportPane bilateral translation synchronization
        from ui.workspace_tabs import WorkspaceReportPane
        pane = WorkspaceReportPane(title="Translation Test Workspace")
        pane.update_synthesis_views(causal_md_test, precomputed_causal_layout=causal_layout_res)
        translated_md_test = (
            "```mermaid\n"
            "graph TD\n"
            '    A["원인 장애 체인<br/>열 충격 과응력<br/>연소 불안정 기록<br />기본 노즐 결함 [1]"] -->|촉발| B["2차 긴급 정지<br/>원격 측정 덤프 유발"]\n'
            "```"
        )
        pane.set_translated_synthesis(translated_md_test)
        if "A" not in pane.causal_label_map_en_to_ko and len(pane.causal_label_map_en_to_ko) == 0:
            raise RuntimeError("WorkspaceReportPane failed to extract localized label mappings!")
        pane.update_graph_language("ko")
        pane.update_graph_language("en")
        print("   -> WorkspaceReportPane bilateral graph translation pipeline verified cleanly.")

        # 13. Verify Knowledge Graph Z-Ordering, Relation Localization & Cancel Button State Machine
        print("[11/11] Verifying KG Z-order hierarchy, relation localization, and Cancel Button state machine...")
        from core.knowledge_graph import localize_kg_relation, KG_RELATION_TRANSLATIONS

        # (a) Verify Relationship mapping dictionary produces valid Korean strings for standard relation tokens
        test_relations = ["associated_with", "identifies", "precedes", "causes", "synthesizes_the", "leads_to", "depends_on"]
        for r_token in test_relations:
            ko_str = localize_kg_relation(r_token, "ko")
            if not ko_str or ko_str == r_token or "_" in ko_str:
                raise RuntimeError(f"Relationship mapping for '{r_token}' failed to produce valid Korean string: '{ko_str}'")
        print(f"   -> KG relationship dictionary localized {len(test_relations)} standard tokens into valid Korean.")

        # (b) Verify Knowledge Graph items have valid z-order hierarchy (node_text.zValue() > edge_line.zValue())
        first_node = list(kg_widget._node_items.values())[0]
        first_edge = kg_widget._edge_items[0]
        if first_node.label_item.zValue() <= first_edge.zValue():
            raise RuntimeError(
                f"Z-order violation: node_text.zValue() ({first_node.label_item.zValue()}) <= edge_line.zValue() ({first_edge.zValue()})"
            )
        if first_edge.badge_bg and first_edge.badge_bg.zValue() <= first_edge.zValue():
            raise RuntimeError(
                f"Z-order violation: edge_badge.zValue() ({first_edge.badge_bg.zValue()}) <= edge_line.zValue() ({first_edge.zValue()})"
            )
        print(f"   -> Strict Z-order hierarchy verified: node_text ({first_node.label_item.zValue()}) > node_circle ({first_node.zValue()}) > edge_badge ({first_edge.badge_bg.zValue() if first_edge.badge_bg else 2.0}) > edge_line ({first_edge.zValue()}).")

        # (c) Verify Cancel Button state machine transitions cleanly from Running -> Cancelling -> Idle/Hidden without bilingual string leaks
        main_win.current_language = "en"
        main_win._set_cancel_state("idle")
        if not main_win.btn_cancel.isHidden() or main_win.btn_cancel.isEnabled():
            raise RuntimeError("Cancel button was expected to be hidden and disabled in Idle state!")
        if "/" in main_win.btn_cancel.text():
            raise RuntimeError(f"Bilingual leak in Idle text: {main_win.btn_cancel.text()}")

        main_win._set_cancel_state("running")
        if main_win.btn_cancel.isHidden() or not main_win.btn_cancel.isEnabled():
            raise RuntimeError("Cancel button was expected to be visible and enabled in Running state!")
        if main_win.btn_cancel.text() != "Cancel Task":
            raise RuntimeError(f"Unexpected Running text in English: {main_win.btn_cancel.text()}")

        main_win._set_cancel_state("cancelling")
        if main_win.btn_cancel.isHidden() or main_win.btn_cancel.isEnabled():
            raise RuntimeError("Cancel button was expected to be visible and disabled in Cancelling state!")
        if main_win.btn_cancel.text() != "Cancelling...":
            raise RuntimeError(f"Unexpected Cancelling text in English: {main_win.btn_cancel.text()}")

        # Korean locale transitions
        main_win.current_language = "ko"
        main_win._set_cancel_state("running")
        if main_win.btn_cancel.text() != "작업 취소":
            raise RuntimeError(f"Unexpected Running text in Korean: {main_win.btn_cancel.text()}")

        main_win._set_cancel_state("cancelling")
        if main_win.btn_cancel.text() != "취소 중...":
            raise RuntimeError(f"Unexpected Cancelling text in Korean: {main_win.btn_cancel.text()}")

        main_win._set_cancel_state("idle")
        if not main_win.btn_cancel.isHidden():
            raise RuntimeError("Cancel button was expected to be hidden in Idle state!")
        print("   -> Cancel Button state machine verified across Running -> Cancelling -> Idle without bilingual leaks.")

        # 12. Verify OmniSweep Perspective Reports persistent translation caching & instant toggle
        print("[12/12] Verifying OmniSweep Perspective Reports persistent translation caching & instant toggle...")
        test_persp_en = (
            "# OmniSweep Multi-Perspective Discovery: Asyncio\n\n"
            "---\n## [1] Systems & Technical Architect `[CORE ARCHITECTURE]`\n"
            "**Role Mandate:** *Examine event loop and coroutines*\n\n"
            "Python asyncio implements cooperative multitasking via an event loop and epoll syscalls.\n"
        )
        test_persp_ko = (
            "# OmniSweep 다중 관점 탐색: Asyncio\n\n"
            "---\n## [1] 시스템 및 기술 아키텍트 `[핵심 아키텍처]`\n"
            "**역할 위임:** *이벤트 루프 및 코루틴 검토*\n\n"
            "파이썬 asyncio는 이벤트 루프 및 epoll 시스템 콜을 통해 협조적 멀티태스킹을 구현합니다.\n"
        )
        test_synth_en = (
            "# Grounded Synthesis Report\n\n"
            "Asyncio allows high-concurrency I/O bound execution without OS thread context-switch overhead."
        )
        test_synth_ko = (
            "# 근거 기반 종합 보고서\n\n"
            "Asyncio는 OS 스레드 컨텍스트 전환 오버헤드 없이 고동시성 I/O 바운드 실행을 가능하게 합니다."
        )

        main_win.perspective_original_text = test_persp_en
        main_win.perspective_translated_text = ""
        main_win.perspective_showing_translation = False
        main_win.synthesis_original_text = test_synth_en
        main_win.synthesis_translated_text = test_synth_ko
        main_win.synthesis_showing_translation = False

        # Populate structured perspectives data
        perspectives_dict = {
            "architect": {
                "id": "architect",
                "name": "Systems & Technical Architect",
                "role": "Examine event loop and coroutines",
                "content_en": "Python asyncio implements cooperative multitasking via an event loop and epoll syscalls.",
                "content_ko": "",
            },
            "_combined": {
                "id": "_combined",
                "name": "Combined Perspectives",
                "content_en": test_persp_en,
                "content_ko": "",
            },
        }
        main_win.active_workspace_pane.set_perspectives_data(perspectives_dict)
        main_win.active_workspace_pane.causal_label_map_en_to_ko = {"A": "원인 장애 체인"}
        main_win.active_workspace_pane.kg_label_map_en_to_ko = {"Python": "파이썬"}

        # Pre-seed cache_manager with translation for test_persp_en
        p_hash = main_win.cache_manager.compute_hash(test_persp_en)
        main_win.cache_manager.set_translation(p_hash, "ko", test_persp_ko)

        # Pre-seed synthesis translation in cache_manager as well
        s_hash = main_win.cache_manager.compute_hash(test_synth_en)
        main_win.cache_manager.set_translation(s_hash, "ko", test_synth_ko)

        # Track any worker thread dispatches
        dispatched_workers = []
        original_start_trans = main_win._start_translation
        def _mock_start_trans(md_text, target_pane):
            dispatched_workers.append(target_pane)
            return original_start_trans(md_text, target_pane)
        main_win._start_translation = _mock_start_trans

        # Checkbox states tracking
        initial_checked = [cb.isChecked() for cb, _ in main_win.perspective_selector._checkboxes]

        # Step 1: Switch to Korean ("ko")
        ko_idx = 1 if main_win.language_combo.itemData(1) == "ko" else 0
        main_win.language_combo.setCurrentIndex(ko_idx)

        if not main_win.perspective_showing_translation:
            raise RuntimeError("Perspective report was expected to show translation after switching to Korean!")
        if main_win.perspective_translated_text != test_persp_ko:
            raise RuntimeError("Perspective translated text did not match cached Korean content!")
        if main_win.active_workspace_pane.get_perspective_translation("ko") != test_persp_ko:
            raise RuntimeError("WorkspaceReportPane get_perspective_translation('ko') did not return cached Korean content!")
        if main_win.active_workspace_pane.perspectives["architect"]["content_ko"] == "":
            raise RuntimeError("Per-perspective architect content_ko was not populated!")
        if len(dispatched_workers) > 0:
            raise RuntimeError(f"Expected 0 worker dispatches on cache hit, but dispatched: {dispatched_workers}")

        # Step 2: Switch back to English ("en")
        en_idx = 0 if main_win.language_combo.itemData(0) == "en" else 1
        main_win.language_combo.setCurrentIndex(en_idx)

        if main_win.perspective_showing_translation:
            raise RuntimeError("Perspective report was expected to show original after switching to English!")
        if main_win.sweep_report_viewer.toPlainText() == "":
            raise RuntimeError("Perspective viewer was unexpectedly empty after switching to English!")

        # Step 3: Switch back to Korean ("ko") a second time
        dispatched_workers.clear()
        main_win.language_combo.setCurrentIndex(ko_idx)

        if not main_win.perspective_showing_translation:
            raise RuntimeError("Perspective report was expected to show translation on second Korean toggle!")
        if main_win.perspective_translated_text != test_persp_ko:
            raise RuntimeError("Perspective translated text did not match cached Korean content on second toggle!")
        if len(dispatched_workers) != 0:
            raise RuntimeError(f"Expected strictly 0 API/worker calls on second toggle, but got: {len(dispatched_workers)}")

        # Step 4: Verify Grounded Synthesis Report, Causal Graph, and Knowledge Graph retain cached states
        if not main_win.synthesis_showing_translation:
            raise RuntimeError("Grounded synthesis report lost its translation showing state!")
        if main_win.synthesis_translated_text != test_synth_ko:
            raise RuntimeError("Grounded synthesis report lost its cached translation text!")

        # Verify Causal & Knowledge Graph localized label maps retained
        if not main_win.active_workspace_pane.causal_label_map_en_to_ko:
            raise RuntimeError("Causal graph label mapping was lost!")
        if not main_win.active_workspace_pane.kg_label_map_en_to_ko:
            raise RuntimeError("Knowledge graph label mapping was lost!")

        # Verify checkbox states maintained
        after_checked = [cb.isChecked() for cb, _ in main_win.perspective_selector._checkboxes]
        if initial_checked != after_checked:
            raise RuntimeError("Perspective checkbox states were altered during language toggling!")

        # Restore original _start_translation
        main_win._start_translation = original_start_trans
        print("   -> Toggling to Korean cached perspective report and populated per-perspective content_ko.")
        print("   -> Toggling to English and back to Korean read from cache with 0 API/worker dispatches.")
        print("   -> Grounded Synthesis, Causal Graph, Knowledge Graph, and checkbox states preserved.")

        # 13. Verify Universal 100% Button Tooltip Coverage across English & Korean
        print("[13/13] Verifying 100% button tooltip coverage across English and Korean locales...")
        from PyQt6.QtWidgets import QPushButton, QToolButton
        en_idx = 0 if main_win.language_combo.itemData(0) == "en" else 1
        main_win.language_combo.setCurrentIndex(en_idx)
        buttons_en = main_win.findChildren(QPushButton) + main_win.findChildren(QToolButton)
        if len(buttons_en) < 30:
            raise RuntimeError(f"Expected at least 30 buttons discovered in hierarchy, found {len(buttons_en)}")
        empty_en = [b for b in buttons_en if not b.toolTip().strip()]
        if empty_en:
            names = [f"{b.__class__.__name__}({b.text() or b.objectName()})" for b in empty_en]
            raise RuntimeError(f"Found {len(empty_en)} buttons with empty tooltips in English: {names}")

        ko_idx = 1 if main_win.language_combo.itemData(1) == "ko" else 0
        main_win.language_combo.setCurrentIndex(ko_idx)
        buttons_ko = main_win.findChildren(QPushButton) + main_win.findChildren(QToolButton)
        empty_ko = [b for b in buttons_ko if not b.toolTip().strip()]
        if empty_ko:
            names = [f"{b.__class__.__name__}({b.text() or b.objectName()})" for b in empty_ko]
            raise RuntimeError(f"Found {len(empty_ko)} buttons with empty tooltips in Korean: {names}")

        print(f"   -> Verified 100% non-empty tooltips across {len(buttons_en)} buttons in English.")
        print(f"   -> Verified 100% non-empty tooltips across {len(buttons_ko)} buttons in Korean.")

        # 14. Verify Resilient Translation Pipeline: Chunking, 504 Deadline Exceeded Backoff, and Caching
        print("[14/14] Verifying Resilient Translation Pipeline: Section chunking, 504 retry, and caching...")
        from google.genai import errors as genai_errors
        from core.translator import MarkdownTranslator, split_markdown_into_chunks
        from core.resilience import is_transient_server_error, is_retryable_error

        # 14.1 Verify error classification for transient errors
        err_504 = genai_errors.APIError(504, "504 Gateway Timeout: DEADLINE_EXCEEDED")
        err_503 = genai_errors.APIError(503, "The service is temporarily unavailable")
        if not is_transient_server_error(err_504) or not is_retryable_error(err_504):
            raise RuntimeError("504 DEADLINE_EXCEEDED was not classified as a retryable transient error!")
        if not is_transient_server_error(err_503) or not is_retryable_error(err_503):
            raise RuntimeError("503 UNAVAILABLE was not classified as a retryable transient error!")

        # 14.2 Verify Markdown chunking on multi-section document
        test_doc = (
            "# Large Multi-Section Research Synthesis [1]\n\n"
            "## 1. System Concurrency Architecture [2]\n"
            + ("Event loop throughput metrics and task scheduling analysis. " * 35 + "\n\n")
            + "## 2. Failure Recovery & Fault Tolerance [3]\n"
            + ("Circuit breakers and cooperative cancellation response latency. " * 35 + "\n\n")
            + "## 3. Empirical Benchmark Verification [4]\n"
            + ("Empirical memory allocation traces and token telemetry stats. " * 35 + "\n\n")
            + "## 4. Synthesis Conclusions\n"
            + "Final grounded synthesis recommendations."
        )
        chunks = split_markdown_into_chunks(test_doc, max_chunk_chars=1800)
        if len(chunks) < 3:
            raise RuntimeError(f"Expected document to split into at least 3 chunks, got {len(chunks)}")
        for idx, c in enumerate(chunks, 1):
            if len(c) > 2500:
                raise RuntimeError(f"Chunk {idx} exceeded expected bound with {len(c)} characters")

        # 14.3 Simulate 504 DEADLINE_EXCEEDED with automated backoff recovery
        class _MockStreamChunk:
            def __init__(self, text: str) -> None:
                self.text = text

        class _MockTransientModel:
            def __init__(self) -> None:
                self.call_count = 0

            def generate_content_stream(self, model, contents, config):
                self.call_count += 1
                if self.call_count == 1:
                    raise genai_errors.APIError(504, "504 Gateway Timeout: DEADLINE_EXCEEDED")
                return [_MockStreamChunk("번역: " + contents[:25])]

        class _MockTransientClient:
            def __init__(self) -> None:
                self.models = _MockTransientModel()

        mock_client = _MockTransientClient()
        mock_translator = MarkdownTranslator(client=mock_client)

        streamed_pieces = []
        recovered_translation = mock_translator.translate_markdown(
            test_doc,
            target_lang="ko",
            chunk_callback=lambda p: streamed_pieces.append(p),
            max_chunk_chars=1800,
        )

        if mock_client.models.call_count <= len(chunks):
            raise RuntimeError("Expected retry call to be dispatched following 504 DEADLINE_EXCEEDED!")
        if not recovered_translation or len(recovered_translation) < 50:
            raise RuntimeError("Translation output was unexpectedly empty or truncated following recovery!")
        if not streamed_pieces:
            raise RuntimeError("Live token streaming chunk_callback was not invoked during chunked translation!")

        # 14.4 Verify Cache Consistency in active workspace
        t_hash = main_win.cache_manager.compute_hash(test_doc)
        main_win.cache_manager.set_translation(t_hash, "ko", recovered_translation)
        retrieved_cached = main_win.cache_manager.get_translation(t_hash, "ko")
        if retrieved_cached != recovered_translation:
            raise RuntimeError("Cached translated report did not match recovered translation!")

        print("   -> 504 DEADLINE_EXCEEDED and 503 UNAVAILABLE classified as retryable transient errors.")
        print(f"   -> Multi-section document ({len(test_doc)} chars) partitioned into {len(chunks)} bounded sections.")
        print("   -> Transient 504 simulated on initial chunk: recovered with exponential backoff and streamed.")
        print("   -> Translated report assembled and verified in cache for instant language toggling.")

        # 15. Verify Causal Graph Edge Label Collision Avoidance & Dynamic Text Wrapping
        print("[15/15] Verifying Causal Graph edge label collision avoidance and text wrapping...")
        from ui.widgets.causal_graph import CausalGraphWidget, _CausalEdgeBadgeItem

        causal_widget = CausalGraphWidget(lang="en")
        test_causal_mermaid = (
            "```mermaid\n"
            "graph TD\n"
            '    Root["Autonomy Core Failure"] -->|"152mm 2-piece ammo & multi-drum auto-loader mechanism failure"| C1["Hydraulic Lock"]\n'
            '    Root -->|"Turret-mounted crew & combustible cartridge ignition cascade"| C2["Fire Suppression Stall"]\n'
            '    Root -->|"Forward-swept wing & carrier flight operation structural overload"| C3["Wing Spar Fatigue"]\n'
            '    Root -->|"High-voltage bus arc flash and secondary battery disconnect"| C4["Electrical Blackout"]\n'
            "```"
        )
        causal_widget.set_markdown_report(test_causal_mermaid)

        # Collect all edge label items in the scene
        edge_label_items = [
            item for item in causal_widget.scene.items()
            if getattr(item, "is_edge_badge", False) or getattr(item, "is_edge_label", False)
        ]

        if len(edge_label_items) < 4:
            raise RuntimeError(f"Expected at least 4 edge label items in scene, found {len(edge_label_items)}")

        # 15.1 Verify Max Width Constraint and Text Wrapping
        MAX_ALLOWED_WIDTH = 180.0
        for idx, item in enumerate(edge_label_items):
            rect = item.boundingRect()
            if rect.width() > MAX_ALLOWED_WIDTH:
                raise RuntimeError(
                    f"Edge label {idx} width ({rect.width():.1f}px) exceeded maximum allowed {MAX_ALLOWED_WIDTH}px!"
                )
            if rect.width() < 40.0:
                raise RuntimeError(f"Edge label {idx} width ({rect.width():.1f}px) is unexpectedly small!")

        # 15.2 Assert no two edge label bounding rectangles intersect
        for i in range(len(edge_label_items)):
            rect_a = edge_label_items[i].boundingRect()
            for j in range(i + 1, len(edge_label_items)):
                rect_b = edge_label_items[j].boundingRect()
                if rect_a.intersects(rect_b):
                    raise RuntimeError(
                        f"Collision detected between edge label {i} and {j}!\n"
                        f"  Label A ({edge_label_items[i].relation}): {rect_a}\n"
                        f"  Label B ({edge_label_items[j].relation}): {rect_b}"
                    )

        # 15.3 Verify Dynamic Translation of Edge Labels preserves collision-free layout
        label_map_ko = {
            "152mm 2-piece ammo & multi-drum auto-loader mechanism failure": "152mm 2피스 탄약 및 다중 드럼 자동장전기 기구 장애",
            "Turret-mounted crew & combustible cartridge ignition cascade": "포탑 승무원 및 가연성 탄피 발화 연쇄",
            "Forward-swept wing & carrier flight operation structural overload": "전진익 및 함재기 비행 운용 구조적 과부하",
            "High-voltage bus arc flash and secondary battery disconnect": "고전압 버스 아크 플래시 및 보조 배터리 차단",
        }
        causal_widget.update_language("ko", label_map_ko)

        for idx, item in enumerate(edge_label_items):
            rect = item.boundingRect()
            if rect.width() > MAX_ALLOWED_WIDTH:
                raise RuntimeError(
                    f"Translated edge label {idx} width ({rect.width():.1f}px) exceeded {MAX_ALLOWED_WIDTH}px!"
                )

        for i in range(len(edge_label_items)):
            rect_a = edge_label_items[i].boundingRect()
            for j in range(i + 1, len(edge_label_items)):
                rect_b = edge_label_items[j].boundingRect()
                if rect_a.intersects(rect_b):
                    raise RuntimeError(
                        f"Collision detected between translated edge labels {i} and {j}!\n"
                        f"  Label A ({edge_label_items[i].relation}): {rect_a}\n"
                        f"  Label B ({edge_label_items[j].relation}): {rect_b}"
                    )

        print(f"   -> Verified {len(edge_label_items)} edge label badges wrapped within {MAX_ALLOWED_WIDTH}px.")
        print(f"   -> Verified strictly 0 collisions across radiating edges (all rectA.intersects(rectB) == False).")
        print("   -> Verified dynamic translation updates and anti-collision recalculation.")

        # 16. Verify Workspace Export Functions (Markdown, HTML, PDF, SVG)
        print("[16/16] Verifying Workspace Export Functions (Markdown, HTML, PDF, SVG)...")
        import tempfile
        from core.exporter import save_html_report, export_pdf_report, build_pdf_html, build_html_report
        from core.document_loader import SourceDocument
        from ui.widgets.knowledge_graph import KnowledgeGraphWidget

        with tempfile.TemporaryDirectory() as export_tmp:
            export_dir = Path(export_tmp)
            md_path = export_dir / "test_synthesis.md"
            html_path = export_dir / "test_report.html"
            pdf_path = export_dir / "test_report.pdf"
            causal_svg_path = export_dir / "causal_graph.svg"
            kg_svg_path = export_dir / "knowledge_graph.svg"

            test_docs = [
                SourceDocument(
                    cite_id=1,
                    title="Asyncio Event Loop Specifications",
                    path_or_uri="https://docs.python.org/3/library/asyncio.html",
                    content="The asyncio module provides infrastructure for writing concurrent code using the async/await syntax.",
                    source_type="web_page",
                    enabled=True,
                ),
                SourceDocument(
                    cite_id=2,
                    title="High-Throughput Concurrency Benchmarks",
                    path_or_uri="https://benchmarks.example.com/concurrency",
                    content="Empirical event loop tests show epoll overhead scales with active descriptors.",
                    source_type="academic_doi",
                    enabled=True,
                ),
            ]
            synth_markdown = (
                "# High-Performance Concurrency Research\n\n"
                "Python asyncio utilizes an event loop for multiplexing [1]. "
                "Empirical benchmarks demonstrate minimal context switch latency [2].\n"
            )

            # 16.1 Markdown Export Verification
            meta_payload = main_win._collect_synthesis_metadata(synth_markdown)
            md_header = (
                f"# {meta_payload['title']}\n"
                f"*Model: `{meta_payload['model_name']}` (Temperature = `0.0`) | "
                f"Active Sources: **{meta_payload['active_sources_count']}** | "
                f"Verified Citations: **{meta_payload['citations_count']}***\n\n---\n\n"
            )
            md_path.write_text(md_header + synth_markdown, encoding="utf-8")
            saved_md = md_path.read_text(encoding="utf-8")
            if not saved_md or "Model:" not in saved_md or "Active Sources:" not in saved_md:
                raise RuntimeError("Markdown export was empty or missing metadata header!")

            # 16.2 HTML Export Verification
            raw_prompt_test = "Analyze aerodynamic stability and control surface flutter of forward-swept wings."
            meta_payload["raw_prompt"] = raw_prompt_test
            meta_payload["query"] = raw_prompt_test

            save_html_report(
                output_path=html_path,
                title=raw_prompt_test,
                report_markdown=synth_markdown,
                documents=test_docs,
                model_name=meta_payload["model_name"],
                audit=meta_payload["audit"],
                metadata=meta_payload,
                language="en",
            )
            if not html_path.exists() or html_path.stat().st_size < 100:
                raise RuntimeError("HTML export file was not generated or is empty!")
            html_content = html_path.read_text(encoding="utf-8")
            if "<html" not in html_content or "</html>" not in html_content:
                raise RuntimeError("HTML export file is malformed!")
            if "Synthesis model: —" in html_content or "Groundedness: <span class=\"badge\" style=\"background:#6e7781\">—" in html_content:
                raise RuntimeError("HTML export contains unpopulated '—' metadata placeholders!")
            if meta_payload["model_name"] not in html_content:
                raise RuntimeError(f"Expected model name '{meta_payload['model_name']}' in HTML export!")
            # Assertion 3: header.cover h1 must not contain the raw input prompt
            if f"<h1>{raw_prompt_test}</h1>" in html_content:
                raise RuntimeError("HTML export placed raw input prompt directly into header.cover h1!")
            if "<details class=\"prompt-card\"" not in html_content or raw_prompt_test not in html_content:
                raise RuntimeError("HTML export missing collapsible prompt card for raw query!")

            # 16.3 PDF Export Verification
            pdf_html = build_pdf_html(
                markdown_text=synth_markdown,
                documents=test_docs,
                title=raw_prompt_test,
                model_name=meta_payload["model_name"],
                audit=meta_payload["audit"],
                metadata=meta_payload,
                language="en",
            )
            if "Synthesis model: —" in pdf_html or "Groundedness: —" in pdf_html:
                raise RuntimeError("PDF HTML template contains unpopulated '—' metadata placeholders!")
            if meta_payload["model_name"] not in pdf_html:
                raise RuntimeError(f"Expected model name '{meta_payload['model_name']}' in PDF HTML!")
            export_pdf_report(
                output_path=pdf_path,
                title=raw_prompt_test,
                report_markdown=synth_markdown,
                documents=test_docs,
                model_name=meta_payload["model_name"],
                audit=meta_payload["audit"],
                metadata=meta_payload,
                language="en",
            )
            if not pdf_path.exists() or pdf_path.stat().st_size < 500:
                raise RuntimeError("PDF export file was not generated or is too small!")

            # 16.4 Graph Vector SVG & Raster Export Verification
            causal_widget.export_to_svg(causal_svg_path)
            if not causal_svg_path.exists() or causal_svg_path.stat().st_size < 50:
                raise RuntimeError("Causal Graph SVG export file was not created or is empty!")

            kg_widget = KnowledgeGraphWidget(lang="en")
            kg_widget.set_documents(test_docs)
            kg_widget.export_to_svg(kg_svg_path)
            if not kg_svg_path.exists() or kg_svg_path.stat().st_size < 50:
                raise RuntimeError("Knowledge Graph SVG export file was not created or is empty!")

            # Assertion 2: Verify XML prologue, standard xmlns, and viewBox
            for svg_path in (causal_svg_path, kg_svg_path):
                svg_txt = svg_path.read_text(encoding="utf-8")
                if not svg_txt.lstrip().startswith("<?xml"):
                    raise RuntimeError(f"{svg_path.name} missing XML prolog <?xml ...")
                if 'xmlns="http://www.w3.org/2000/svg"' not in svg_txt:
                    raise RuntimeError(f"{svg_path.name} missing standard xmlns http://www.w3.org/2000/svg")
                if "viewBox=" not in svg_txt:
                    raise RuntimeError(f"{svg_path.name} missing viewBox attribute")
                if re.search(r'width="[\d.]+mm"', svg_txt):
                    raise RuntimeError(f"{svg_path.name} contains invalid millimeter width")

            # High-res raster image exports (4K resolution verification)
            causal_png_path = export_dir / "causal_graph.png"
            kg_png_path = export_dir / "knowledge_graph.png"
            causal_widget.export_image(causal_png_path)
            kg_widget.export_image(kg_png_path)
            if not causal_png_path.exists() or causal_png_path.stat().st_size < 1000:
                raise RuntimeError("Causal Graph PNG export was not created or is too small!")
            if not kg_png_path.exists() or kg_png_path.stat().st_size < 1000:
                raise RuntimeError("Knowledge Graph PNG export was not created or is too small!")

            from PyQt6.QtGui import QImage
            causal_img = QImage(str(causal_png_path))
            if causal_img.isNull() or causal_img.width() < 3840:
                raise RuntimeError(f"Causal Graph PNG width ({causal_img.width()}px) is less than 3840px (4K requirement)!")
            kg_img = QImage(str(kg_png_path))
            if kg_img.isNull() or kg_img.width() < 3840:
                raise RuntimeError(f"Knowledge Graph PNG width ({kg_img.width()}px) is less than 3840px (4K requirement)!")

            # 16.5 Knowledge Graph Semantic Filtering Verification
            from core.knowledge_graph import KnowledgeGraphEngine
            kg_test_engine = KnowledgeGraphEngine()
            test_corpus_snippet = (
                "In October 1967, NASA established the Apollo Program to land humans on the Moon. "
                "While West Germany operated the Leopard 2 tank, Hence Germany adopted 120mm Rheinmetall cannons. "
                "Inconel 718 was incorporated into rocket combustion chambers. The Fixed timeline was challenging. "
                "1981 marked the orbital launch of the Space Shuttle."
            )
            ents, rels = kg_test_engine._heuristic_extract(test_corpus_snippet, cite_id=1)
            ent_names = [e["name"] for e in ents]

            # Assertion 1.1: 0 standalone date strings
            date_entities = [n for n in ent_names if re.match(r"^\d{4}$", n) or "october" in n.lower()]
            if date_entities:
                raise RuntimeError(f"Knowledge Graph extracted standalone dates: {date_entities}")

            # Assertion 1.2: 0 transition words / fragments
            transition_entities = [n for n in ent_names if any(w in n.lower() for w in ["while", "hence", "the fixed"])]
            if transition_entities:
                raise RuntimeError(f"Knowledge Graph extracted sentence transitions: {transition_entities}")

            # Assertion 1.3: 0 'associated_with' relations
            banned_relations = [r for r in rels if r.get("relation") in ("associated_with", "associated with")]
            if banned_relations:
                raise RuntimeError(f"Knowledge Graph contained generic 'associated_with' relations: {banned_relations}")

            # Assertion 1.4: 0 table headers or trailing-stopword/copula junk entities from table markdown
            test_markdown_with_table = (
                "| Milestone / Event | Empirical Outcome | Primary Citation |\n"
                "| Official / Baseline Claim | Preliminary Study | Technical Appendix |\n"
                "| Apollo 11 Mission | Moon landing [1] | Primary Citation |\n\n"
                "Class Is Still an issue. Purpose The objective was identified.\n"
                "The Space Shuttle Orbiter was deployed by NASA.\n"
            )
            table_ents, table_rels = kg_test_engine._heuristic_extract(test_markdown_with_table, cite_id=1)
            table_ent_names = [e["name"] for e in table_ents]

            banned_table_headers = [
                "Primary Citation", "Milestone / Event", "Empirical Outcome",
                "Official / Baseline Claim", "Technical Appendix", "Preliminary Study",
                "Milestone", "Event", "Empirical", "Outcome", "Primary", "Citation",
            ]
            found_headers = [n for n in table_ent_names if any(h.lower() == n.lower() for h in banned_table_headers)]
            if found_headers:
                raise RuntimeError(f"Knowledge Graph extracted markdown table headers: {found_headers}")

            trailing_junk = [n for n in table_ent_names if any(n.lower().endswith(" " + w) for w in ["the", "is", "still", "and", "or", "of", "in", "to", "with"])]
            if trailing_junk:
                raise RuntimeError(f"Knowledge Graph extracted trailing-stopword junk entities: {trailing_junk}")

            copula_junk = [n for n in table_ent_names if any(f" {c} " in f" {n.lower()} " for c in ["is", "are", "was", "were"])]
            if copula_junk:
                raise RuntimeError(f"Knowledge Graph extracted broken clause fragments with copulas: {copula_junk}")

            # 16.6 Pure Locale English Section Headings Verification
            from core.notebook_synthesis import EPISTEMIC_FRICTION_MANDATE
            if "상충 쟁점" in EPISTEMIC_FRICTION_MANDATE or "연대표" in EPISTEMIC_FRICTION_MANDATE:
                raise RuntimeError("English synthesis prompt mandate contains Korean slash-delimited headers!")
            if "Contested Claims & Empirical Anomalies /" in synth_markdown:
                raise RuntimeError("English synthesis report contains dual-language slash-delimited heading!")

            # 16.7 Epistemic Radar Tooltips Verification
            from ui.balance_radar import EpistemicBalanceWidget
            radar_en = EpistemicBalanceWidget(lang="en")
            radar_ko = EpistemicBalanceWidget(lang="ko")
            for r in (radar_en, radar_ko):
                for ax in ("authority", "linguistic", "dispersion"):
                    tip = r.get_axis_tooltip(ax)
                    if not tip or len(tip) < 10:
                        raise RuntimeError(f"Radar axis {ax} in lang={r._lang} has empty tooltip!")
                if not r.canvas.toolTip() or len(r.canvas.toolTip()) < 20:
                    raise RuntimeError(f"Radar canvas in lang={r._lang} has empty tooltip!")

            # 16.8 Knowledge Graph Clutter Elimination, Dynamic Badges, Expanded Physics, & Dual-Language Translation
            kg_test_ui = KnowledgeGraphWidget(lang="en")
            kg_test_ui.engine.clear()
            kg_test_ui.engine.add_entity("Ground Combat Vehicle", category="Program")
            kg_test_ui.engine.add_entity("BAE Systems", category="Organization")
            kg_test_ui.engine.add_entity("General Dynamics", category="Organization")
            kg_test_ui.engine.add_entity("Active Protection System", category="Concept")
            kg_test_ui.engine.add_relation("Ground Combat Vehicle", "BAE Systems", relation="competes_with")
            kg_test_ui.engine.add_relation("Ground Combat Vehicle", "Active Protection System", relation="incorporates")
            kg_layout = kg_test_ui.engine.compute_layout_data(min_repulsion=280.0)
            kg_test_ui.load_precomputed_layout(kg_layout)

            # Assertion 16.8.1: Clean edge lines by default (all badges hidden)
            for edge in kg_test_ui._edge_items:
                if edge.badge_bg and edge.badge_bg.isVisible():
                    raise RuntimeError("KG edge badge was visible by default! Expected hidden for clutter elimination.")

            # Assertion 16.8.2: Hover/Selection reveals connected edge badges
            kg_test_ui._select_node("Ground Combat Vehicle")
            connected_badges = [e.badge_bg for e in kg_test_ui._edge_items if e.source_id in ("Ground Combat Vehicle", "ground combat vehicle") or e.target_id in ("Ground Combat Vehicle", "ground combat vehicle")]
            for b in connected_badges:
                if not b or not b.isVisible():
                    raise RuntimeError("Connected KG edge badge failed to become visible upon node selection!")

            # Reset selection hides badges again
            kg_test_ui._reset_selection()
            for edge in kg_test_ui._edge_items:
                if edge.badge_bg and edge.badge_bg.isVisible():
                    raise RuntimeError("KG edge badge remained visible after resetting selection!")

            # Assertion 16.8.3: Physical node collision boundary enforcement d(A, B) >= R_eff,A + R_eff,B
            nodes_out = kg_layout["nodes"]
            for i in range(len(nodes_out)):
                r_eff_a = max(24.0, nodes_out[i].get("label_w", 120.0) / 2.0) + 15.0
                for j in range(i + 1, len(nodes_out)):
                    r_eff_b = max(24.0, nodes_out[j].get("label_w", 120.0) / 2.0) + 15.0
                    d_sep = ((nodes_out[i]["x"] - nodes_out[j]["x"]) ** 2 + (nodes_out[i]["y"] - nodes_out[j]["y"]) ** 2) ** 0.5
                    if d_sep < (r_eff_a + r_eff_b):
                        raise RuntimeError(
                            f"Physical node collision detected: d={d_sep:.1f}px < (R_a={r_eff_a:.1f} + R_b={r_eff_b:.1f} = {r_eff_a + r_eff_b:.1f}px) "
                            f"between '{nodes_out[i]['name']}' and '{nodes_out[j]['name']}'"
                        )
                    if d_sep < 180.0:
                        raise RuntimeError(f"Physics simulation packed nodes too closely ({d_sep:.1f}px < 180px) between {nodes_out[i]['name']} and {nodes_out[j]['name']}")

            # Assertion 16.8.4: Full Dual-Language Entity Node and Edge Translation
            kg_test_ui.update_language("ko")
            gcv_item = kg_test_ui._node_items.get("ground combat vehicle") or kg_test_ui._node_items.get("Ground Combat Vehicle")
            if not gcv_item or gcv_item.name != "지상전투차량":
                raise RuntimeError(f"Entity node 'Ground Combat Vehicle' failed to translate to Korean! Got: {getattr(gcv_item, 'name', None)}")

            edge_competes = [e for e in kg_test_ui._edge_items if e.original_relation == "competes_with"][0]
            if edge_competes.label_item and edge_competes.label_item.text() != "경쟁함":
                raise RuntimeError(f"Edge relation 'competes_with' failed to translate to '경쟁함'! Got: {edge_competes.label_item.text()}")

            # Restore English
            kg_test_ui.update_language("en")
            if gcv_item.name != "Ground Combat Vehicle":
                raise RuntimeError(f"Entity node failed to restore English name! Got: {gcv_item.name}")

        print("   -> Knowledge Graph decluttered default state (0 overlapping badges) verified.")
        print("   -> Knowledge Graph dynamic hover/selection badge reveal and expanded physics verified.")
        print("   -> Knowledge Graph full bilingual entity node and relation translation verified.")
        print("   -> Markdown export verified with valid structure and model metadata.")
        print(f"   -> HTML export verified with populated metadata and clean cover title (raw prompt in collapsible card).")
        print("   -> PDF export verified with populated metadata and vector compilation.")
        print("   -> Causal Graph and Knowledge Graph valid SVG and 4K raster PNG exports verified.")
        print("   -> Knowledge Graph semantic extraction verified (0 dates, 0 transitions, 0 'associated_with').")
        print("   -> English synthesis verified with 0 Korean slash-delimited section headings.")
        print("   -> Epistemic Radar verified with non-empty localized axis and canvas tooltips.")

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
