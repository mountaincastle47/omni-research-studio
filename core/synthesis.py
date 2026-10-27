"""Accelerated Synthesis Engine with fast JSON parsing, persistent connection reuse, and cooperative cancellation."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import orjson

    def fast_json_loads(data: Union[str, bytes]) -> Any:
        """High-speed zero-copy JSON parsing using orjson."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        return orjson.loads(data)

    def fast_json_dumps(obj: Any, **kwargs) -> str:
        """High-speed JSON serialization using orjson."""
        return orjson.dumps(obj).decode("utf-8")

except ImportError:
    try:
        import ujson

        def fast_json_loads(data: Union[str, bytes]) -> Any:
            return ujson.loads(data)

        def fast_json_dumps(obj: Any, **kwargs) -> str:
            return ujson.dumps(obj, **kwargs)

    except ImportError:
        import json

        def fast_json_loads(data: Union[str, bytes]) -> Any:
            return json.loads(data)

        def fast_json_dumps(obj: Any, **kwargs) -> str:
            return json.dumps(obj, **kwargs)

# Re-export core synthesis symbols from notebook_synthesis
from core.notebook_synthesis import (
    CitationMatch,
    DEFAULT_SYNTHESIS_MODEL,
    NotebookSynthesizer,
    SynthesisResult,
)

CitationRef = CitationMatch

logger = logging.getLogger("OmniSynthesis")

MAX_GAP_ITERATIONS: int = 2


class CancellableSynthesisEngine:
    """Thread-safe cancellable synthesis orchestrator with active client socket teardown."""

    def __init__(self, synthesizer: Optional[NotebookSynthesizer] = None) -> None:
        self.synthesizer = synthesizer
        self.stop_requested = threading.Event()
        self.active_client: Any = getattr(synthesizer, "client", None) if synthesizer else None

    def request_stop(self) -> None:
        """Immediately signal stop and tear down active network sockets."""
        self.stop_requested.set()
        if hasattr(self, "active_client") and self.active_client:
            try:
                self.active_client.close()
            except Exception:
                pass

    def is_stopped(self) -> bool:
        return self.stop_requested.is_set()


__all__ = [
    "MAX_GAP_ITERATIONS",
    "CitationRef",
    "DEFAULT_SYNTHESIS_MODEL",
    "NotebookSynthesizer",
    "SynthesisResult",
    "CancellableSynthesisEngine",
    "fast_json_loads",
    "fast_json_dumps",
]
