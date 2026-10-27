"""Progressive real-time cost and context telemetry manager for OmniResearch Studio."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from core.token_ledger import TokenLedger, TokenTotals


@dataclass
class LiveTaskUsage:
    """In-flight tracking metadata for an active streaming or generation task."""

    task_id: str
    model: str
    session_id: str = "default"
    prompt_tokens: int = 0
    candidate_tokens: int = 0
    cached_tokens: int = 0
    candidate_chars: int = 0
    cost_usd: float = 0.0
    start_time: float = 0.0


@dataclass
class LiveTotals:
    """Cumulative ledger totals combined with active in-flight estimates."""

    prompt_tokens: int = 0
    candidate_tokens: int = 0
    cached_tokens: int = 0
    total_cost_usd: float = 0.0
    is_live: bool = False
    active_tasks: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.candidate_tokens

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "candidate_tokens": self.candidate_tokens,
            "cached_tokens": self.cached_tokens,
            "total_cost_usd": self.total_cost_usd,
            "total_tokens": self.total_tokens,
            "is_live": self.is_live,
            "active_tasks": self.active_tasks,
        }


class LiveCostTracker:
    """
    Progressive real-time cost calculator tracking in-flight prompt tokens,
    streaming chunk accumulation, and final audit reconciliation against TokenLedger.
    """

    _instance: Optional[LiveCostTracker] = None

    def __init__(self, ledger: Optional[TokenLedger] = None) -> None:
        self._lock = threading.Lock()
        self.ledger = ledger or TokenLedger.get_instance()
        self._active_tasks: Dict[str, LiveTaskUsage] = {}

    @classmethod
    def get_instance(cls) -> LiveCostTracker:
        if cls._instance is None:
            cls._instance = LiveCostTracker()
        return cls._instance

    def estimate_tokens_from_text(self, text_content: str) -> int:
        """Estimate token count from raw text (fast 4 chars/token heuristic)."""
        if not text_content:
            return 0
        return max(1, len(text_content) // 4)

    def start_task(
        self,
        task_id: str,
        model: str,
        prompt_text_or_tokens: Union[str, int],
        cached_tokens: int = 0,
        session_id: str = "default",
        client: Optional[Any] = None,
    ) -> LiveTotals:
        """
        Register a new task before dispatching API call.
        Calculates prompt token count and pre-flight spend immediately.
        """
        with self._lock:
            prompt_tokens = 0
            if isinstance(prompt_text_or_tokens, int):
                prompt_tokens = max(0, prompt_text_or_tokens)
            elif isinstance(prompt_text_or_tokens, str):
                if client is not None and hasattr(client, "models") and hasattr(client.models, "count_tokens"):
                    try:
                        res = client.models.count_tokens(model=model, contents=prompt_text_or_tokens)
                        prompt_tokens = int(getattr(res, "total_tokens", 0) or 0)
                    except Exception:
                        prompt_tokens = self.estimate_tokens_from_text(prompt_text_or_tokens)
                else:
                    prompt_tokens = self.estimate_tokens_from_text(prompt_text_or_tokens)

            preflight_cost = self.ledger.calculate_cost(
                model=model,
                prompt_tokens=prompt_tokens,
                candidate_tokens=0,
                cached_tokens=cached_tokens,
            )

            task = LiveTaskUsage(
                task_id=task_id,
                model=model,
                session_id=session_id,
                prompt_tokens=prompt_tokens,
                candidate_tokens=0,
                cached_tokens=cached_tokens,
                candidate_chars=0,
                cost_usd=preflight_cost,
                start_time=time.monotonic(),
            )
            self._active_tasks[task_id] = task

        return self.get_live_totals()

    def accumulate_chunk(
        self,
        task_id: str,
        chunk_text_or_tokens: Union[str, int],
    ) -> LiveTotals:
        """
        Increment output candidate tokens and recalculate spend incrementally on chunk yields.
        """
        with self._lock:
            task = self._active_tasks.get(task_id)
            if task is None:
                return self.get_live_totals()

            if isinstance(chunk_text_or_tokens, int):
                task.candidate_tokens += max(0, chunk_text_or_tokens)
            elif isinstance(chunk_text_or_tokens, str):
                task.candidate_chars += len(chunk_text_or_tokens)
                task.candidate_tokens = max(1, task.candidate_chars // 4)

            task.cost_usd = self.ledger.calculate_cost(
                model=task.model,
                prompt_tokens=task.prompt_tokens,
                candidate_tokens=task.candidate_tokens,
                cached_tokens=task.cached_tokens,
            )

        return self.get_live_totals()

    def reconcile_task(
        self,
        task_id: str,
        usage_metadata: Optional[Any] = None,
        final_model: str = "",
        prompt_tokens: Optional[int] = None,
        candidate_tokens: Optional[int] = None,
        cached_tokens: Optional[int] = None,
        record_to_ledger: bool = True,
    ) -> LiveTotals:
        """
        Reconcile running estimate with exact billed API metrics and remove from active tasks.
        """
        with self._lock:
            task = self._active_tasks.pop(task_id, None)
            if task is not None and record_to_ledger:
                model_used = final_model or task.model
                if usage_metadata is not None:
                    self.ledger.record_usage(
                        model=model_used,
                        usage_metadata=usage_metadata,
                        session_id=task.session_id,
                    )
                else:
                    p_tok = prompt_tokens if prompt_tokens is not None else task.prompt_tokens
                    c_tok = candidate_tokens if candidate_tokens is not None else task.candidate_tokens
                    ca_tok = cached_tokens if cached_tokens is not None else task.cached_tokens
                    self.ledger.record_manual(
                        model=model_used,
                        prompt_tokens=p_tok,
                        candidate_tokens=c_tok,
                        cached_tokens=ca_tok,
                        session_id=task.session_id,
                    )

        return self.get_live_totals()

    def cancel_task(self, task_id: str, commit_partial: bool = False) -> LiveTotals:
        """Cancel task and clean up in-flight state."""
        with self._lock:
            task = self._active_tasks.pop(task_id, None)
            if task is not None and commit_partial:
                if task.prompt_tokens > 0 or task.candidate_tokens > 0:
                    self.ledger.record_manual(
                        model=task.model,
                        prompt_tokens=task.prompt_tokens,
                        candidate_tokens=task.candidate_tokens,
                        cached_tokens=task.cached_tokens,
                        session_id=task.session_id,
                    )
        return self.get_live_totals()

    def get_live_totals(self, session_id: Optional[str] = None) -> LiveTotals:
        """
        Aggregate committed SQLite totals from TokenLedger plus all active in-flight estimates.
        """
        base: TokenTotals = self.ledger.get_session_totals(session_id)
        with self._lock:
            active_p = sum(t.prompt_tokens for t in self._active_tasks.values())
            active_c = sum(t.candidate_tokens for t in self._active_tasks.values())
            active_ca = sum(t.cached_tokens for t in self._active_tasks.values())
            active_cost = sum(t.cost_usd for t in self._active_tasks.values())
            is_live = len(self._active_tasks) > 0
            count = len(self._active_tasks)

        return LiveTotals(
            prompt_tokens=base.prompt_tokens + active_p,
            candidate_tokens=base.candidate_tokens + active_c,
            cached_tokens=base.cached_tokens + active_ca,
            total_cost_usd=round(base.total_cost_usd + active_cost, 6),
            is_live=is_live,
            active_tasks=count,
        )

    def reset(self) -> None:
        """Clear active in-flight tracking."""
        with self._lock:
            self._active_tasks.clear()


GLOBAL_COST_TRACKER = LiveCostTracker.get_instance()
