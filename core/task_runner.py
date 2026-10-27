"""Thread-safe cooperative task execution and cancellation engine."""

from __future__ import annotations

import threading
from typing import Callable, Any, Optional
from core.resilience import TaskCancelledError


class TaskCancellationContext:
    """Thread-safe cancellation context using threading.Event."""

    def __init__(self) -> None:
        self.stop_requested = threading.Event()
        self._is_cancelled = False

    def request_cancel(self) -> None:
        """Signal cooperative cancellation to worker thread."""
        self._is_cancelled = True
        self.stop_requested.set()

    def is_cancelled(self) -> bool:
        """Return True if cancellation has been requested."""
        return self._is_cancelled or self.stop_requested.is_set()

    def check_cancelled(self) -> None:
        """Raise TaskCancelledError immediately if cancellation was requested."""
        if self.is_cancelled():
            raise TaskCancelledError("Task was cooperatively cancelled by user.")


class TaskRunner:
    """Coordinates execution of background tasks with cooperative cancellation."""

    def __init__(self) -> None:
        self.current_context: Optional[TaskCancellationContext] = None

    def create_context(self) -> TaskCancellationContext:
        self.current_context = TaskCancellationContext()
        return self.current_context

    def cancel_active(self) -> None:
        if self.current_context:
            self.current_context.request_cancel()
