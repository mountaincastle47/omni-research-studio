"""Worker architecture with 60-second inactivity watchdog, heartbeat tracking, and instant cancellation."""

from __future__ import annotations

import time
import threading
from typing import Any, Callable, Optional
from PyQt6.QtCore import QObject, pyqtSignal


class WorkerSignals(QObject):
    """Unified signals for background workers."""

    started = pyqtSignal()
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)  # pct, eta, status_token
    chunk = pyqtSignal(str, str)
    telemetry = pyqtSignal(dict)
    canceled = pyqtSignal()
    task_timed_out = pyqtSignal(str, float)  # current_stage, elapsed_seconds


class BaseWorker:
    """Thread-safe worker base supporting cooperative cancellation and active socket teardown."""

    def __init__(self) -> None:
        self.stop_requested = threading.Event()
        self.active_client: Any = None
        self.signals = WorkerSignals()

    def request_stop(self) -> None:
        """Signal cooperative cancellation and close any active HTTP/network clients."""
        self.stop_requested.set()
        if hasattr(self, "active_client") and self.active_client:
            try:
                self.active_client.close()
            except Exception:
                pass

    def is_stopped(self) -> bool:
        """Check whether cancellation has been requested."""
        return self.stop_requested.is_set()


class InactivityWatchdog:
    """
    Watches background worker execution for stalls.
    Triggers cancellation and timeout signal if no heartbeat is recorded for >60s,
    or if a single stage remains stalled for >90s.
    """

    def __init__(
        self,
        timeout_seconds: float = 180.0,
        stage_stall_limit: float = 240.0,
        total_stall_limit: float = 900.0,
        on_timeout: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.stage_stall_limit = stage_stall_limit
        self.total_stall_limit = total_stall_limit
        self.on_timeout = on_timeout
        self.stop_requested = threading.Event()
        self._last_heartbeat: float = time.time()
        self._task_start: float = time.time()
        self._stage_start: float = time.time()
        self._current_stage: str = "init"
        self._is_active: bool = False
        self._thread: Optional[threading.Thread] = None

    def start(self, initial_stage: str = "init") -> None:
        self.stop_requested.clear()
        self._last_heartbeat = time.time()
        self._task_start = time.time()
        self._stage_start = time.time()
        self._current_stage = initial_stage
        self._is_active = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def heartbeat(self, stage: Optional[str] = None) -> None:
        """Call this on every network packet, search hit, or progress increment."""
        self._last_heartbeat = time.time()
        if stage and stage != self._current_stage:
            self._current_stage = stage
            self._stage_start = time.time()

    def stop(self) -> None:
        self._is_active = False

    def _loop(self) -> None:
        while self._is_active and not self.stop_requested.is_set():
            time.sleep(min(0.2, max(0.02, self.timeout_seconds / 4.0)))
            now = time.time()
            idle_sec = now - self._last_heartbeat
            stage_sec = now - self._stage_start
            total_sec = now - self._task_start
            if idle_sec >= self.timeout_seconds or stage_sec >= self.stage_stall_limit or total_sec >= self.total_stall_limit:
                reported_elapsed = round(max(idle_sec, stage_sec if stage_sec >= self.stage_stall_limit else idle_sec), 1)
                self.stop_requested.set()
                if self.on_timeout:
                    self.on_timeout(self._current_stage, reported_elapsed)
                break
