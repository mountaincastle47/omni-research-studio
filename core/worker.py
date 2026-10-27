"""Worker architecture with 60-second inactivity watchdog, heartbeat tracking, and instant cancellation."""

from __future__ import annotations

import time
import threading
from typing import Callable, Optional
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


class InactivityWatchdog:
    """
    Watches background worker execution for stalls.
    Triggers cancellation and timeout signal if no heartbeat is recorded for >60s.
    """

    def __init__(
        self,
        timeout_seconds: float = 60.0,
        total_stall_limit: float = 90.0,
        on_timeout: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.total_stall_limit = total_stall_limit
        self.on_timeout = on_timeout
        self.stop_requested = threading.Event()
        self._last_heartbeat: float = time.monotonic()
        self._task_start: float = time.monotonic()
        self._current_stage: str = "init"
        self._is_active: bool = False
        self._thread: Optional[threading.Thread] = None

    def start(self, initial_stage: str = "init") -> None:
        self.stop_requested.clear()
        self._last_heartbeat = time.monotonic()
        self._task_start = time.monotonic()
        self._current_stage = initial_stage
        self._is_active = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def heartbeat(self, stage: Optional[str] = None) -> None:
        """Call this on every network packet, search hit, or progress increment."""
        self._last_heartbeat = time.monotonic()
        if stage:
            self._current_stage = stage

    def stop(self) -> None:
        self._is_active = False

    def _loop(self) -> None:
        while self._is_active and not self.stop_requested.is_set():
            time.sleep(1.0)
            now = time.monotonic()
            idle = now - self._last_heartbeat
            total_elapsed = now - self._task_start

            if idle >= self.timeout_seconds or total_elapsed >= self.total_stall_limit:
                self.stop_requested.set()
                if self.on_timeout:
                    self.on_timeout(self._current_stage, idle)
                break
