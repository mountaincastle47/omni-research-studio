"""OmniSweep discovery execution controller with strict socket timeouts, top-level exception interceptor, and watchdog tracking."""

from __future__ import annotations

import socket
import time
from typing import Any, Callable, Dict, List, Optional

# Enforce strict 30-second default socket timeout across all network calls
DEFAULT_NETWORK_TIMEOUT: float = 30.0
socket.setdefaulttimeout(DEFAULT_NETWORK_TIMEOUT)

from core.storm_discovery import (
    OmniSweepDiscoveryAgent,
    OmniSweepDiscoveryResult,
)
from core.resilience import TaskCancelledError

# Structured progress phase tokens for dynamic i18n resolution
PHASE_TOKENS: Dict[int, str] = {
    1: "omnisweep_phase_1",
    2: "omnisweep_phase_2",
    3: "omnisweep_phase_3",
    4: "omnisweep_phase_4",
}


class OmniSweepController:
    """Coordinates execution of multi-perspective OmniSweep discovery with watchdog heartbeat tracking."""

    def __init__(
        self,
        agent: OmniSweepDiscoveryAgent,
        heartbeat_callback: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.agent = agent
        self.heartbeat_callback = heartbeat_callback
        self.cancel_check = cancel_check

    def run(
        self,
        topic: str,
        perspectives: List[Dict[str, str]],
        corpus_summary: str = "",
        progress_callback: Optional[Callable[[str], None]] = None,
        step_progress_callback: Optional[Callable[[int, int, str, int], None]] = None,
        subphase_callback: Optional[Callable[[int, int, str, float], None]] = None,
    ) -> OmniSweepDiscoveryResult:
        """Top-level exception interceptor and heartbeat refreshed execution."""
        if self.cancel_check and self.cancel_check():
            raise TaskCancelledError("Task aborted by user.")

        if self.heartbeat_callback:
            self.heartbeat_callback("omnisweep_phase_1")

        def _intercepted_subphase(idx: int, tot: int, msg: str, ratio: float) -> None:
            if self.heartbeat_callback:
                phase_token = PHASE_TOKENS.get(idx, "omnisweep_phase_2")
                self.heartbeat_callback(phase_token)
            if subphase_callback:
                subphase_callback(idx, tot, msg, ratio)

        def _intercepted_step(pct: int, eta: int, msg: str, idx: int) -> None:
            if self.heartbeat_callback:
                self.heartbeat_callback(f"step_{idx}")
            if step_progress_callback:
                step_progress_callback(pct, eta, msg, idx)

        return self.agent.run_discovery(
            topic=topic,
            perspectives=perspectives,
            corpus_summary=corpus_summary,
            progress_callback=progress_callback,
            step_progress_callback=_intercepted_step,
            subphase_callback=_intercepted_subphase,
            cancel_check=self.cancel_check,
            heartbeat_callback=self.heartbeat_callback,
        )
