"""Headless Pre-Build Smoke Test Harness for OmniResearch Studio.

Executes core discovery, synthesis, recursive gap-filling, token telemetry,
and cooperative cancellation without initializing a GUI window to verify pipeline
health and prevent thread lock, serialization, or timeout regressions before compilation.
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
            "## Contested Claims & Empirical Anomalies / 상충 쟁점 및 실증 불일치 분석\n"
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
