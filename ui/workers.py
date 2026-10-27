"""Background QThread workers with live streaming, 250ms interpolated ETA progress, global caching, and cancellation."""

from __future__ import annotations

import threading
import time
import traceback
from typing import Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.audio_studio import (
    SESSION_CACHE_DIR,
    AudioStudioGenerator,
    NeuralVoiceSynthesizer,
    PodcastScript,
)
from core.cache_manager import GLOBAL_CACHE, CacheManager
from core.config import ConfigManager, DEFAULT_SYNTHESIS_MODEL
from core.cost_tracker import GLOBAL_COST_TRACKER
from core.database import get_db_connection
from core.document_loader import SourceDocument
from core.followup_engine import FOLLOWUP_MODEL, FollowUpEngine
from core.local_llm_client import is_local_model
from core.i18n import get_text
from core.notebook_synthesis import NotebookSynthesizer, SynthesisResult
from core.resilience import (
    RATE_LIMIT_USER_MESSAGE,
    TaskCancelledError,
    is_rate_limit_error,
)
from core.storm_discovery import OmniSweepDiscoveryAgent, OmniSweepDiscoveryResult
from core.translator import TRANSLATION_MODEL, MarkdownTranslator


import socket
import threading

# Enforce strict 30-second socket timeout across all worker network interactions
DEFAULT_WORKER_SOCKET_TIMEOUT: float = 30.0
socket.setdefaulttimeout(DEFAULT_WORKER_SOCKET_TIMEOUT)


class BaseCancellableWorker(QThread):
    """Base QThread supporting cooperative cancellation, live streaming chunks, and interpolated ETA updates."""

    progress_Changed = pyqtSignal(str)
    progress_Detailed = pyqtSignal(int, int, str)  # (percentage: 0-100, eta_seconds: int, status_text: str)
    chunk_received = pyqtSignal(str, str)  # (chunk_text, target_pane)
    telemetry_live = pyqtSignal(dict)  # (live token and cost metrics)
    cache_Hit = pyqtSignal()
    cancelled = pyqtSignal()
    task_canceled = pyqtSignal()
    task_timed_out = pyqtSignal(str, float)  # (stage: str, idle_seconds: float)

    def __init__(self, cache_manager: Optional[CacheManager] = None) -> None:
        super().__init__()
        self.stop_requested = threading.Event()
        self._is_cancelled: bool = False
        self._last_heartbeat: float = time.monotonic()
        self._task_start: float = time.monotonic()
        self._stage_start: float = time.monotonic()
        self._current_stage: str = "OmniSweep Discovery"
        self._watchdog_active: bool = False
        self._watchdog_timeout: float = 180.0  # 60s inactivity watchdog limit (between heartbeats)
        self._stage_stall_limit: float = 240.0  # 90s maximum stall in a single stage without progress
        self._total_stall_limit: float = 900.0  # 10 min absolute ceiling for multi-perspective workflow
        self.cache_manager: CacheManager = cache_manager or GLOBAL_CACHE
        from core.memory_guard import MemoryGuard
        self.finished.connect(lambda: MemoryGuard.clean())
        self.cancelled.connect(self.task_canceled.emit)

    def record_heartbeat(self, stage: Optional[str] = None) -> None:
        """Refresh heartbeat timestamp whenever a network chunk, search hit, or progress tick is recorded."""
        self._last_heartbeat = time.monotonic()
        if stage and stage != self._current_stage:
            self._current_stage = stage
            self._stage_start = time.monotonic()

    def start_watchdog(self, initial_stage: str = "OmniSweep Discovery") -> None:
        """Spawn a background daemon thread checking for stalls."""
        self._watchdog_active = True
        self._last_heartbeat = time.monotonic()
        self._task_start = time.monotonic()
        self._stage_start = time.monotonic()
        self._current_stage = initial_stage

        def _watchdog_loop() -> None:
            while self._watchdog_active and not self.is_cancelled():
                time.sleep(min(0.2, max(0.02, self._watchdog_timeout / 4.0)))
                now = time.monotonic()
                idle_sec = now - self._last_heartbeat
                stage_sec = now - self._stage_start
                total_sec = now - self._task_start
                if idle_sec >= self._watchdog_timeout or stage_sec >= self._stage_stall_limit or total_sec >= self._total_stall_limit:
                    reported_elapsed = round(max(idle_sec, stage_sec if stage_sec >= self._stage_stall_limit else idle_sec), 1)
                    self.stop_requested.set()
                    self._is_cancelled = True
                    try:
                        self.task_timed_out.emit(self._current_stage, reported_elapsed)
                        self.cancelled.emit()
                    except Exception:
                        pass
                    break

        wd = threading.Thread(target=_watchdog_loop, daemon=True)
        wd.start()

    def stop_watchdog(self) -> None:
        self._watchdog_active = False

    def requestInterruption(self) -> None:
        """Set cooperative cancellation flag in addition to QThread interruption state."""
        self.stop_requested.set()
        self._is_cancelled = True
        super().requestInterruption()
        try:
            self.task_canceled.emit()
            self.cancelled.emit()
        except Exception:
            pass

    def cancel(self) -> None:
        """Alias for cooperative cancellation."""
        self.requestInterruption()

    def is_cancelled(self) -> bool:
        """Check whether interruption or cancellation has been requested."""
        return self.stop_requested.is_set() or self._is_cancelled or self.isInterruptionRequested()


class OmniSweepWorker(BaseCancellableWorker):
    """
    Executes multi-perspective OmniSweep web discovery with 3 measured sub-phases per perspective:
      (1) Query formulation (15%)
      (2) Search grounding (60%)
      (3) Perspective synthesis (25%)
    Includes a 250ms tick interpolator for smooth progress & real-time ETA countdown.
    """

    finished_Success = pyqtSignal(object)  # OmniSweepDiscoveryResult
    failed_Error = pyqtSignal(str)

    def __init__(
        self,
        config_manager: ConfigManager,
        topic: str,
        perspectives: List[Dict[str, str]],
        corpus_summary: str = "",
        model_override: str = "",
        cache_manager: Optional[CacheManager] = None,
        inter_perspective_delay: float = 2.5,
        deep_scrape: bool = True,
        scrape_status_text: str = "Deep-scraping full text from authoritative sources...",
    ) -> None:
        super().__init__(cache_manager=cache_manager)
        self.config_manager = config_manager
        self.topic = topic
        self.perspectives = perspectives
        self.corpus_summary = corpus_summary
        self.model_override = model_override
        self.inter_perspective_delay = inter_perspective_delay
        self.deep_scrape = deep_scrape
        self.scrape_status_text = scrape_status_text

    def run(self) -> None:
        get_db_connection()
        self.start_watchdog("omnisweep_phase_1")
        try:
            if self.is_cancelled():
                self.cancelled.emit()
                return

            model_name = self.model_override or self.config_manager.config.discovery_model
            persona_ids = [
                str(p.get("id") or p.get("name") or "") for p in self.perspectives
            ]

            # 1. Global Cache Check
            cached_dict = self.cache_manager.get_discovery(self.topic, persona_ids, model_name)
            if cached_dict is not None:
                if self.is_cancelled():
                    self.cancelled.emit()
                    return
                restored = OmniSweepDiscoveryResult.from_dict(cached_dict)
                self.progress_Detailed.emit(100, 0, "CACHE_HIT")
                self.cache_Hit.emit()
                self.finished_Success.emit(restored)
                return

            total = max(1, len(self.perspectives))
            state_lock = threading.Lock()
            state = {
                "active_index": 1,
                "subphase_start_pct": 0.0,
                "subphase_target_pct": (0.15 / total) * 100.0,
                "current_pct": 1.0,
                "avg_duration": 9.0,
                "completed_count": 0,
                "step_start_time": time.monotonic(),
                "status_text": "omnisweep_phase_1",
                "stop_ticker": False,
            }

            def _ticker_loop() -> None:
                while True:
                    time.sleep(0.25)
                    if self.is_cancelled():
                        break
                    with state_lock:
                        if state["stop_ticker"]:
                            break
                        cur = float(state["current_pct"])
                        target = float(state["subphase_target_pct"])
                        if cur < target - 0.4:
                            cur = min(target - 0.4, cur + max(0.35, (target - cur) * 0.12))
                            state["current_pct"] = cur

                        idx = int(state["active_index"])
                        avg_dur = float(state["avg_duration"])
                        step_elapsed = max(0.0, time.monotonic() - float(state["step_start_time"]))
                        rem_in_current = max(1.0, avg_dur - step_elapsed)
                        rem_perspectives = max(0, total - idx)
                        pacing_rem = rem_perspectives * self.inter_perspective_delay
                        eta_sec = max(1, int(round(rem_in_current + rem_perspectives * avg_dur + pacing_rem)))
                        pct_int = max(1, min(99, int(round(cur))))
                        st_msg = str(state["status_text"])

                    self.progress_Detailed.emit(pct_int, eta_sec, st_msg)

            ticker_thread = threading.Thread(target=_ticker_loop, daemon=True)
            ticker_thread.start()

            task_id = f"omnisweep_{id(self)}"
            try:
                if self.is_cancelled():
                    self.cancelled.emit()
                    return

                client = self.config_manager.create_client()
                est_prompt = max(400, len(self.topic) * 4 + len(self.corpus_summary) // 4 + 600) * total
                GLOBAL_COST_TRACKER.start_task(
                    task_id=task_id,
                    model=model_name,
                    prompt_text_or_tokens=est_prompt,
                    session_id="discovery",
                )
                self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

                agent = OmniSweepDiscoveryAgent(
                    client=client,
                    model_name=model_name,
                    inter_perspective_delay=self.inter_perspective_delay,
                    deep_scrape=self.deep_scrape,
                    scrape_status_text=self.scrape_status_text,
                )

                completed_durations: List[float] = []

                def on_subphase(idx: int, tot: int, status_msg: str, cumulative_slice_ratio: float) -> None:
                    slice_width = 100.0 / max(1, tot)
                    slice_base = (idx - 1) * slice_width
                    if cumulative_slice_ratio <= 0.16:
                        phase_token = "omnisweep_phase_1"
                    elif cumulative_slice_ratio <= 0.76:
                        phase_token = "omnisweep_phase_2"
                    else:
                        phase_token = "omnisweep_phase_3"
                    self.record_heartbeat(phase_token)

                    with state_lock:
                        if idx != state["active_index"]:
                            state["active_index"] = idx
                            state["step_start_time"] = time.monotonic()
                        if cumulative_slice_ratio <= 0.16:
                            # Subphase 1 (0 -> 15% of slice)
                            state["subphase_start_pct"] = slice_base
                            state["subphase_target_pct"] = slice_base + slice_width * 0.15
                            state["current_pct"] = max(float(state["current_pct"]), slice_base + slice_width * 0.05)
                        elif cumulative_slice_ratio <= 0.76:
                            # Subphase 2 (15% -> 75% of slice: Search grounding 60%)
                            state["subphase_start_pct"] = slice_base + slice_width * 0.15
                            state["subphase_target_pct"] = slice_base + slice_width * 0.75
                            state["current_pct"] = max(float(state["current_pct"]), slice_base + slice_width * 0.18)
                        else:
                            # Subphase 3 (75% -> 100% of slice: Perspective synthesis 25%)
                            state["subphase_start_pct"] = slice_base + slice_width * 0.75
                            state["subphase_target_pct"] = slice_base + slice_width * 0.98
                            state["current_pct"] = max(float(state["current_pct"]), slice_base + slice_width * 0.78)
                        state["status_text"] = phase_token

                def on_step_progress(pct: int, _eta: int, status_msg: str, idx: int) -> None:
                    self.record_heartbeat("omnisweep_phase_3")
                    with state_lock:
                        elapsed_step = max(0.5, time.monotonic() - float(state["step_start_time"]))
                        if pct >= int((idx / total) * 100):
                            completed_durations.append(elapsed_step)
                            state["avg_duration"] = sum(completed_durations) / len(completed_durations)
                            state["current_pct"] = float(pct)
                        state["status_text"] = "omnisweep_phase_3"
                    GLOBAL_COST_TRACKER.accumulate_chunk(task_id, 350)
                    self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

                self.record_heartbeat("omnisweep_phase_1")
                self._last_heartbeat = time.monotonic()
                self._stage_start = time.monotonic()
                result: OmniSweepDiscoveryResult = agent.run_discovery(
                    topic=self.topic,
                    perspectives=self.perspectives,
                    corpus_summary=self.corpus_summary,
                    progress_callback=self.progress_Changed.emit,
                    step_progress_callback=on_step_progress,
                    subphase_callback=on_subphase,
                    cancel_check=self.is_cancelled,
                    heartbeat_callback=self.record_heartbeat,
                )

                with state_lock:
                    state["stop_ticker"] = True

                GLOBAL_COST_TRACKER.reconcile_task(task_id, record_to_ledger=True, prompt_tokens=est_prompt, candidate_tokens=350 * total)
                self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

                if self.is_cancelled():
                    self.cancelled.emit()
                    return

                self.record_heartbeat("omnisweep_phase_4")
                self.cache_manager.set_discovery(
                    self.topic, persona_ids, model_name, result.to_dict()
                )
                self.progress_Detailed.emit(100, 0, "omnisweep_phase_4")
                self.finished_Success.emit(result)
            except TaskCancelledError:
                self.stop_watchdog()
                with state_lock:
                    state["stop_ticker"] = True
                GLOBAL_COST_TRACKER.cancel_task(task_id, commit_partial=True)
                self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())
                self.cancelled.emit()
            except Exception as exc:
                self.stop_watchdog()
                with state_lock:
                    state["stop_ticker"] = True
                GLOBAL_COST_TRACKER.cancel_task(task_id, commit_partial=True)
                self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())
                if self.is_cancelled():
                    self.cancelled.emit()
                    return
                if is_rate_limit_error(exc):
                    self.failed_Error.emit(RATE_LIMIT_USER_MESSAGE)
                else:
                    detail = f"{exc}\n\n{traceback.format_exc()}"
                    self.failed_Error.emit(detail)
        except Exception as top_exc:
            if not self.is_cancelled():
                self.failed_Error.emit(str(top_exc))
        finally:
            self.stop_watchdog()

# Backwards-compatible alias
ResearchWorker = OmniSweepWorker


class SynthesisWorker(BaseCancellableWorker):
    """
    Executes zero-temperature grounded synthesis with live streaming and 4-phase progress interpolation:
      Phase 1 (0% -> 15%): Context packing & token indexing.
      Phase 2 (15% -> 45%): Model reasoning & time-to-first-token (~5s creep).
      Phase 3 (45% -> 95%): Live token streaming proportional to chunks received.
      Phase 4 (95% -> 100%): Final HTML rendering.
    Seeds ETA at ~18s and updates once per second based on streaming throughput.
    """

    finished_Success = pyqtSignal(object)  # SynthesisResult
    failed_Error = pyqtSignal(str)

    def __init__(
        self,
        config_manager: ConfigManager,
        query: str,
        documents: List[SourceDocument],
        model_override: str = "",
        cache_manager: Optional[CacheManager] = None,
        compression_mode: str = "Auto",
    ) -> None:
        super().__init__(cache_manager=cache_manager)
        self.config_manager = config_manager
        self.query = query
        self.documents = list(documents)
        self.model_override = model_override
        self.compression_mode = compression_mode

    def _compute_corpus_hash(self) -> str:
        active_docs = [doc for doc in self.documents if doc.enabled]
        serialized = [
            {
                "cite_id": d.cite_id,
                "title": d.title,
                "path_or_uri": d.path_or_uri,
                "content": d.content,
            }
            for d in active_docs
        ]
        return self.cache_manager.compute_hash(serialized)

    def run(self) -> None:
        get_db_connection()
        self.start_watchdog("synthesis_phase_1")
        state_lock = threading.Lock()
        state = {
            "phase": 2,  # 2 = TTFT reasoning (15->45%), 3 = Streaming (45->95%)
            "current_pct": 15.0,
            "chars_streamed": 0,
            "expected_chars": 3800,
            "start_time": time.monotonic(),
            "stream_start_time": 0.0,
            "last_eta": 18,
            "last_eta_update": time.monotonic(),
            "status_text": "Phase 2/4: Reasoning across sources...",
            "stop_ticker": False,
        }
        task_id = f"synthesis_{id(self)}"
        try:
            if self.is_cancelled():
                self.cancelled.emit()
                return

            model_name = self.model_override or self.config_manager.config.synthesis_model
            active_docs = [d for d in self.documents if d.enabled]
            corpus_hash = self._compute_corpus_hash()

            # 1. Global Cache Check
            cached_report = self.cache_manager.get_synthesis(self.query, corpus_hash, model_name)
            if cached_report is not None:
                if self.is_cancelled():
                    self.cancelled.emit()
                    return
                citations = NotebookSynthesizer.extract_citations_for_documents(
                    cached_report, active_docs
                )
                cached_result = SynthesisResult(
                    query=self.query.strip(),
                    model_used=model_name,
                    markdown_report=cached_report,
                    citations_used=citations,
                    total_sources_provided=len(active_docs),
                    from_cache=True,
                )
                self.progress_Detailed.emit(100, 0, "CACHE_HIT")
                self.cache_Hit.emit()
                self.finished_Success.emit(cached_result)
                return

            # Phase 1 (0% -> 15%): Context packing & token indexing
            status_p1 = f"Phase 1/4: Packing {len(active_docs)} sources & indexing context..."
            self.progress_Detailed.emit(15, 18, status_p1)

            state["status_text"] = f"Phase 2/4: Reasoning across {len(active_docs)} sources ({model_name})..."

            def _synth_ticker() -> None:
                while True:
                    time.sleep(0.25)
                    if self.is_cancelled():
                        break
                    now = time.monotonic()
                    with state_lock:
                        if state["stop_ticker"]:
                            break
                        phase = int(state["phase"])
                        cur = float(state["current_pct"])
                        if phase == 2:
                            # Creep from 15% to 45% over ~5s (1.5% per 250ms tick)
                            cur = min(44.5, cur + 1.5)
                            state["current_pct"] = cur
                            if now - float(state["last_eta_update"]) >= 1.0:
                                elapsed = now - float(state["start_time"])
                                state["last_eta"] = max(4, int(round(18.0 - elapsed)))
                                state["last_eta_update"] = now
                        elif phase == 3:
                            chars = int(state["chars_streamed"])
                            exp = max(500, int(state["expected_chars"]))
                            ratio = min(1.0, chars / exp)
                            target_pct = 45.0 + ratio * 50.0  # 45% -> 95%
                            cur = max(cur, min(95.0, target_pct))
                            state["current_pct"] = cur
                            if now - float(state["last_eta_update"]) >= 1.0:
                                stream_elapsed = max(0.25, now - float(state["stream_start_time"]))
                                rate = max(80.0, chars / stream_elapsed)
                                rem_chars = max(0, exp - chars)
                                state["last_eta"] = max(1, int(round(rem_chars / rate)))
                                state["last_eta_update"] = now

                        pct_int = max(1, min(95, int(round(cur))))
                        eta_int = int(state["last_eta"])
                        st_msg = str(state["status_text"])

                    self.record_heartbeat(st_msg)
                    self.progress_Detailed.emit(pct_int, eta_int, st_msg)

            ticker_thread = threading.Thread(target=_synth_ticker, daemon=True)
            ticker_thread.start()

            if self.is_cancelled():
                self.cancelled.emit()
                return

            if is_local_model(model_name):
                client = None
            else:
                client = self.config_manager.create_client()
            synthesizer = NotebookSynthesizer(
                client=client, model_name=model_name, compression_mode=self.compression_mode
            )

            est_prompt_tokens = sum(d.estimated_tokens for d in active_docs) + max(200, len(self.query) // 4 + 800)
            GLOBAL_COST_TRACKER.start_task(
                task_id=task_id,
                model=model_name,
                prompt_text_or_tokens=est_prompt_tokens,
                cached_tokens=32768 if est_prompt_tokens >= 32768 else 0,
                session_id="synthesis",
                client=client,
            )
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

            def _on_chunk(chunk_text: str) -> None:
                with state_lock:
                    if state["phase"] == 2:
                        state["phase"] = 3
                        state["stream_start_time"] = time.monotonic()
                        state["current_pct"] = max(45.0, float(state["current_pct"]))
                        state["status_text"] = f"Phase 3/4: Streaming grounded synthesis ({model_name})..."
                    state["chars_streamed"] = int(state["chars_streamed"]) + len(chunk_text)
                self.record_heartbeat("Phase 3/4: Streaming grounded synthesis...")
                self.chunk_received.emit(chunk_text, "synthesis")
                GLOBAL_COST_TRACKER.accumulate_chunk(task_id, chunk_text)
                self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

            result: SynthesisResult = synthesizer.synthesize(
                query=self.query,
                documents=self.documents,
                progress_callback=self.progress_Changed.emit,
                chunk_callback=_on_chunk,
                cancel_check=self.is_cancelled,
            )

            with state_lock:
                state["stop_ticker"] = True

            GLOBAL_COST_TRACKER.reconcile_task(task_id, record_to_ledger=False)
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

            if self.is_cancelled():
                self.cancelled.emit()
                return

            # Phase 4 (95% -> 100%): Final HTML rendering
            self.record_heartbeat("Phase 4/4: Finalizing HTML report & citations...")
            self.progress_Detailed.emit(97, 1, "Phase 4/4: Finalizing HTML report & citations...")
            self.cache_manager.set_synthesis(
                self.query, corpus_hash, model_name, result.markdown_report
            )
            self.progress_Detailed.emit(100, 0, "Grounded synthesis complete.")
            self.finished_Success.emit(result)
        except TaskCancelledError:
            self.stop_watchdog()
            with state_lock:
                state["stop_ticker"] = True
            GLOBAL_COST_TRACKER.cancel_task(task_id, commit_partial=True)
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())
            self.cancelled.emit()
        except Exception as exc:
            self.stop_watchdog()
            try:
                with state_lock:
                    state["stop_ticker"] = True
                GLOBAL_COST_TRACKER.cancel_task(task_id, commit_partial=True)
                self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())
            except Exception:
                pass
            if self.is_cancelled():
                self.cancelled.emit()
                return
            if is_rate_limit_error(exc):
                self.failed_Error.emit(RATE_LIMIT_USER_MESSAGE)
            else:
                detail = f"{exc}\n\n{traceback.format_exc()}"
                self.failed_Error.emit(detail)
        finally:
            self.stop_watchdog()


class AudioWorker(BaseCancellableWorker):
    """
    Generates the two-host Audio Overview script (streaming + cached), then renders it to speech with edge-tts
    neural voices into session_cache/audio_briefing.mp3.

    Progress: script generation maps to 0-50% (0-100% when `render_audio=False`), TTS maps to 50-98%.
    A TTS failure never discards the script: `audio_failed` fires and `finished_Success` still delivers the script.
    """

    script_ready = pyqtSignal(object)  # PodcastScript, emitted as soon as the dialogue exists
    audio_ready = pyqtSignal(str)  # absolute path of the rendered MP3
    audio_failed = pyqtSignal(str)  # TTS error message (script is preserved)
    finished_Success = pyqtSignal(object)  # PodcastScript
    failed_Error = pyqtSignal(str)

    def __init__(
        self,
        config_manager: ConfigManager,
        topic_or_query: str,
        synthesis_markdown: str,
        documents: List[SourceDocument],
        focus_instructions: str = "",
        model_override: str = "",
        cache_manager: Optional[CacheManager] = None,
        language: str = "en",
        render_audio: bool = True,
        existing_script: Optional[PodcastScript] = None,
        output_dir: Optional[str] = None,
    ) -> None:
        super().__init__(cache_manager=cache_manager)
        self.config_manager = config_manager
        self.topic_or_query = topic_or_query
        self.synthesis_markdown = synthesis_markdown
        self.documents = list(documents)
        self.focus_instructions = focus_instructions
        self.model_override = model_override
        self.language = "ko" if str(language).lower().startswith("ko") else "en"
        self.render_audio = render_audio
        self.existing_script = existing_script
        self.output_dir = output_dir or str(SESSION_CACHE_DIR)

    def _compute_synthesis_context_hash(self) -> str:
        active_docs = [
            {"cite_id": d.cite_id, "title": d.title, "snippet": d.summary_snippet}
            for d in self.documents
            if d.enabled
        ]
        return self.cache_manager.compute_hash(
            {
                "topic": self.topic_or_query,
                "synthesis": self.synthesis_markdown,
                "docs": active_docs,
            }
        )

    def _obtain_script(self, model_name: str, span: int) -> Optional[PodcastScript]:
        """Return the script (existing, cached, or freshly generated); None when cancelled."""
        if self.existing_script is not None:
            return self.existing_script

        synth_hash = self._compute_synthesis_context_hash()
        cache_directive = f"{self.focus_instructions}||lang={self.language}"
        cached_raw = self.cache_manager.get_audio(synth_hash, cache_directive, model_name)
        if cached_raw is not None:
            self.progress_Detailed.emit(span, 0, "CACHE_HIT")
            self.cache_Hit.emit()
            return AudioStudioGenerator.build_script_from_raw(
                raw_text=cached_raw,
                default_title=self.topic_or_query or "OmniResearch Audio Overview",
                model_used=model_name,
                from_cache=True,
            )

        status_msg = get_text("btn_generate_audio", self.language)
        self.progress_Changed.emit(status_msg)
        self.progress_Detailed.emit(max(2, int(span * 0.1)), 12, status_msg)

        chars_streamed = {"count": 0}
        start_t = time.monotonic()

        def _on_audio_chunk(chunk_text: str) -> None:
            chars_streamed["count"] += len(chunk_text)
            ratio = min(1.0, chars_streamed["count"] / 3000.0)
            pct = int(span * (0.1 + ratio * 0.85))
            elapsed = max(0.25, time.monotonic() - start_t)
            rate = max(80.0, chars_streamed["count"] / elapsed)
            rem = max(1, int(round(max(0, 3000 - chars_streamed["count"]) / rate)))
            self.progress_Detailed.emit(min(span - 1, pct), rem, status_msg)
            self.chunk_received.emit(chunk_text, "audio")

        client = self.config_manager.create_client()
        studio = AudioStudioGenerator(client=client, model_name=model_name)
        script = studio.generate_podcast_script(
            topic_or_query=self.topic_or_query,
            synthesis_markdown=self.synthesis_markdown,
            documents=self.documents,
            focus_instructions=self.focus_instructions,
            progress_callback=self.progress_Changed.emit,
            chunk_callback=_on_audio_chunk,
            cancel_check=self.is_cancelled,
            output_language=self.language,
        )
        if self.is_cancelled():
            return None
        self.cache_manager.set_audio(synth_hash, cache_directive, model_name, script.raw_script)
        return script

    def _render_speech(self, script: PodcastScript, base_pct: int) -> None:
        """Run edge-tts synthesis (asyncio.run inside this worker thread) and publish the MP3 path."""
        synthesizer = NeuralVoiceSynthesizer(language=self.language, output_dir=self.output_dir)
        total_turns = max(1, len(synthesizer.plan_segments(script)))
        start_t = time.monotonic()
        span = 98 - base_pct

        def _on_tts_progress(done: int, total: int) -> None:
            elapsed = max(0.25, time.monotonic() - start_t)
            per_turn = elapsed / max(1, done)
            eta = max(0, int(round((total - done) * per_turn)))
            pct = base_pct + int(span * (done / max(1, total)))
            status = get_text("status_audio_rendering", self.language).format(done=done, total=total)
            self.progress_Changed.emit(status)
            self.progress_Detailed.emit(min(98, pct), eta, status)

        self.progress_Detailed.emit(
            base_pct,
            total_turns * 2,
            get_text("status_audio_rendering", self.language).format(done=0, total=total_turns),
        )
        mp3_path = synthesizer.synthesize_script(
            script,
            progress_callback=_on_tts_progress,
            cancel_check=self.is_cancelled,
        )
        if self.is_cancelled():
            return
        self.audio_ready.emit(str(mp3_path))

    def run(self) -> None:
        if self.is_cancelled():
            self.cancelled.emit()
            return

        model_name = self.model_override or self.config_manager.config.audio_model

        try:
            script_span = 50 if self.render_audio else 100
            if self.existing_script is not None:
                script_span = 0
            script = self._obtain_script(model_name, max(script_span, 1))
            if script is None or self.is_cancelled():
                self.cancelled.emit()
                return

            self.script_ready.emit(script)

            if self.render_audio:
                base_pct = 50 if self.existing_script is None else 2
                try:
                    self._render_speech(script, base_pct)
                except TaskCancelledError:
                    self.cancelled.emit()
                    return
                except Exception as exc:  # TTS/network failure must not discard the generated script
                    if self.is_cancelled():
                        self.cancelled.emit()
                        return
                    self.audio_failed.emit(str(exc))

            if self.is_cancelled():
                self.cancelled.emit()
                return
            self.progress_Detailed.emit(100, 0, "Audio Overview complete.")
            self.finished_Success.emit(script)
        except TaskCancelledError:
            self.cancelled.emit()
        except Exception as exc:
            if self.is_cancelled():
                self.cancelled.emit()
                return
            if is_rate_limit_error(exc):
                self.failed_Error.emit(RATE_LIMIT_USER_MESSAGE)
            else:
                detail = f"{exc}\n\n{traceback.format_exc()}"
                self.failed_Error.emit(detail)


class FollowUpWorker(BaseCancellableWorker):
    """Streams a grounded follow-up answer (gemini-3.8-flash) with cooperative cancellation."""

    finished_Success = pyqtSignal(str)  # complete answer text
    failed_Error = pyqtSignal(str)

    def __init__(
        self,
        config_manager: ConfigManager,
        question: str,
        synthesis_report: str,
        documents: List[SourceDocument],
        history: List[Dict[str, str]],
        answer_language: str = "en",
        model_name: str = FOLLOWUP_MODEL,
        cache_manager: Optional[CacheManager] = None,
        engine: Optional[FollowUpEngine] = None,
    ) -> None:
        super().__init__(cache_manager=cache_manager)
        self.config_manager = config_manager
        self.question = question
        self.synthesis_report = synthesis_report
        self.documents = list(documents)
        self.history = [dict(entry) for entry in history]
        self.answer_language = answer_language
        self.model_name = model_name
        self._engine = engine

    def run(self) -> None:
        if self.is_cancelled():
            self.cancelled.emit()
            return

        task_id = f"followup_{id(self)}"
        try:
            status = get_text("status_chat_answering", self.answer_language)
            self.progress_Changed.emit(status)
            self.progress_Detailed.emit(10, 6, status)

            est_prompt = max(200, (len(self.question) + len(self.synthesis_report)) // 4)
            GLOBAL_COST_TRACKER.start_task(
                task_id=task_id,
                model=self.model_name,
                prompt_text_or_tokens=est_prompt,
                session_id="followup",
            )
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

            chars_streamed = {"count": 0}
            start_t = time.monotonic()

            def _on_chunk(chunk_text: str) -> None:
                chars_streamed["count"] += len(chunk_text)
                ratio = min(1.0, chars_streamed["count"] / 1400.0)
                elapsed = max(0.25, time.monotonic() - start_t)
                rate = max(60.0, chars_streamed["count"] / elapsed)
                rem = max(1, int(round(max(0, 1400 - chars_streamed["count"]) / rate)))
                self.progress_Detailed.emit(min(95, int(10 + ratio * 85)), rem, status)
                self.chunk_received.emit(chunk_text, "chat")
                GLOBAL_COST_TRACKER.accumulate_chunk(task_id, chunk_text)
                self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

            engine = self._engine or FollowUpEngine(
                client=self.config_manager.create_client(), model_name=self.model_name
            )
            answer = engine.stream_answer(
                question=self.question,
                synthesis_report=self.synthesis_report,
                documents=self.documents,
                history=self.history,
                answer_language=self.answer_language,
                chunk_callback=_on_chunk,
                progress_callback=self.progress_Changed.emit,
                cancel_check=self.is_cancelled,
            )

            GLOBAL_COST_TRACKER.reconcile_task(task_id, record_to_ledger=False)
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

            if self.is_cancelled():
                self.cancelled.emit()
                return

            self.progress_Detailed.emit(100, 0, "Follow-up answer complete.")
            self.finished_Success.emit(answer)
        except TaskCancelledError:
            GLOBAL_COST_TRACKER.cancel_task(task_id, commit_partial=True)
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())
            self.cancelled.emit()
        except Exception as exc:
            GLOBAL_COST_TRACKER.cancel_task(task_id, commit_partial=True)
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())
            if self.is_cancelled():
                self.cancelled.emit()
                return
            if is_rate_limit_error(exc):
                self.failed_Error.emit(RATE_LIMIT_USER_MESSAGE)
            else:
                detail = f"{exc}\n\n{traceback.format_exc()}"
                self.failed_Error.emit(detail)


class TranslationWorker(BaseCancellableWorker):
    """Asynchronously translates Markdown reports using gemini-3.8-flash with live streaming, caching, and cancellation."""

    finished_Success = pyqtSignal(str, str)  # (translated_text, target_pane)
    failed_Error = pyqtSignal(str)  # error_message

    def __init__(
        self,
        config_manager: ConfigManager,
        markdown_text: str,
        target_pane: str,
        target_lang: str = "ko",
        model_name: str = TRANSLATION_MODEL,
        cache_manager: Optional[CacheManager] = None,
    ) -> None:
        super().__init__(cache_manager=cache_manager)
        self.config_manager = config_manager
        self.markdown_text = markdown_text
        self.target_pane = target_pane
        self.target_lang = target_lang
        self.model_name = model_name

    def run(self) -> None:
        if self.is_cancelled():
            self.cancelled.emit()
            return

        text_hash = self.cache_manager.compute_hash(self.markdown_text)

        # 1. Global Cache Check
        cached_translation = self.cache_manager.get_translation(text_hash, self.target_lang)
        if cached_translation is not None:
            if self.is_cancelled():
                self.cancelled.emit()
                return
            self.progress_Detailed.emit(100, 0, "CACHE_HIT")
            self.cache_Hit.emit()
            self.finished_Success.emit(cached_translation, self.target_pane)
            return

        task_id = f"translation_{id(self)}"
        try:
            if self.is_cancelled():
                self.cancelled.emit()
                return

            status_msg = "Translating report..."
            self.progress_Changed.emit(status_msg)
            self.progress_Detailed.emit(20, 10, status_msg)

            est_prompt = max(100, len(self.markdown_text) // 4)
            GLOBAL_COST_TRACKER.start_task(
                task_id=task_id,
                model=self.model_name,
                prompt_text_or_tokens=est_prompt,
                session_id="translation",
            )
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

            expected_len = max(400, len(self.markdown_text))
            chars_streamed = {"count": 0}
            start_t = time.monotonic()

            def _on_trans_chunk(chunk_text: str) -> None:
                chars_streamed["count"] += len(chunk_text)
                ratio = min(1.0, chars_streamed["count"] / expected_len)
                pct = int(20 + ratio * 75)
                elapsed = max(0.25, time.monotonic() - start_t)
                rate = max(80.0, chars_streamed["count"] / elapsed)
                rem = max(1, int(round(max(0, expected_len - chars_streamed["count"]) / rate)))
                self.progress_Detailed.emit(min(95, pct), rem, status_msg)
                self.chunk_received.emit(chunk_text, self.target_pane)
                GLOBAL_COST_TRACKER.accumulate_chunk(task_id, chunk_text)
                self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

            client = self.config_manager.create_client()
            translator = MarkdownTranslator(client=client, model_name=self.model_name)
            translated_text = translator.translate_markdown(
                markdown_text=self.markdown_text,
                target_lang=self.target_lang,
                progress_callback=self.progress_Changed.emit,
                chunk_callback=_on_trans_chunk,
                cancel_check=self.is_cancelled,
            )

            GLOBAL_COST_TRACKER.reconcile_task(task_id, record_to_ledger=True, prompt_tokens=est_prompt, candidate_tokens=max(1, chars_streamed["count"] // 4))
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())

            if self.is_cancelled():
                self.cancelled.emit()
                return

            self.cache_manager.set_translation(text_hash, self.target_lang, translated_text)
            self.progress_Detailed.emit(100, 0, "Translation complete.")
            self.finished_Success.emit(translated_text, self.target_pane)
        except TaskCancelledError:
            GLOBAL_COST_TRACKER.cancel_task(task_id, commit_partial=True)
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())
            self.cancelled.emit()
        except Exception as exc:
            GLOBAL_COST_TRACKER.cancel_task(task_id, commit_partial=True)
            self.telemetry_live.emit(GLOBAL_COST_TRACKER.get_live_totals().to_dict())
            if self.is_cancelled():
                self.cancelled.emit()
                return
            if is_rate_limit_error(exc):
                self.failed_Error.emit(RATE_LIMIT_USER_MESSAGE)
            else:
                self.failed_Error.emit(str(exc))


class VisionAnalysisWorker(BaseCancellableWorker):
    """Executes multi-modal schematic analysis with Gemini Vision asynchronously."""

    finished_Success = pyqtSignal(str, str, str)  # figure_path, figure_title, analysis_markdown
    chunk_received = pyqtSignal(str)
    failed_Error = pyqtSignal(str)

    def __init__(
        self,
        figure_path: str,
        figure_title: str,
        query: str = "",
        model_name: str = "gemini-3.8-flash",
        config_manager: Optional[ConfigManager] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent=parent)
        self.figure_path = figure_path
        self.figure_title = figure_title
        self.query = query
        self.model_name = model_name
        self.config_manager = config_manager or ConfigManager()

    def run(self) -> None:
        if self.is_cancelled():
            self.cancelled.emit()
            return

        from core.vision_analyzer import VisionAnalyzer
        try:
            analyzer = VisionAnalyzer(config_manager=self.config_manager)

            def _stream_cb(chunk: str) -> None:
                if not self.is_cancelled():
                    self.chunk_received.emit(chunk)

            res = analyzer.analyze_figure(
                image_path=self.figure_path,
                query=self.query,
                model_name=self.model_name,
                stream_callback=_stream_cb,
            )
            if not self.is_cancelled():
                self.finished_Success.emit(self.figure_path, self.figure_title, res)
        except TaskCancelledError:
            self.cancelled.emit()
        except Exception as exc:
            if not self.is_cancelled():
                if is_rate_limit_error(exc):
                    self.failed_Error.emit(RATE_LIMIT_USER_MESSAGE)
                else:
                    self.failed_Error.emit(str(exc))


class GapFillWorker(BaseCancellableWorker):
    """Executes recursive autonomous gap-filling loop in the background."""

    status_changed = pyqtSignal(str)
    gap_fill_finished = pyqtSignal(str, list)
    failed_Error = pyqtSignal(str)

    def __init__(
        self,
        report_markdown: str,
        corpus: DocumentCorpus,
        base_topic: str = "",
        lang: str = "en",
        config_manager: Optional[ConfigManager] = None,
        model_name: str = DEFAULT_SYNTHESIS_MODEL,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.report_markdown = report_markdown
        self.corpus = corpus
        self.base_topic = base_topic
        self.lang = lang
        self.config_manager = config_manager
        self.model_name = model_name

    def run(self) -> None:
        if self.is_cancelled():
            self.cancelled.emit()
            return

        from core.deep_research import DeepResearchEngine
        try:
            engine = DeepResearchEngine(
                config_manager=self.config_manager,
                model_name=self.model_name,
            )

            def _progress(msg: str) -> None:
                if not self.is_cancelled():
                    self.status_changed.emit(msg)

            addendum, new_docs = engine.run_gap_filling_loop(
                report_markdown=self.report_markdown,
                corpus=self.corpus,
                base_topic=self.base_topic,
                lang=self.lang,
                progress_callback=_progress,
            )
            if not self.is_cancelled():
                self.gap_fill_finished.emit(addendum, new_docs)
        except TaskCancelledError:
            self.cancelled.emit()
        except Exception as exc:
            if not self.is_cancelled():
                self.failed_Error.emit(str(exc))
