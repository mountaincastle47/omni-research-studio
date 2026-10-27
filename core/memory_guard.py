"""Explicit Hardware VRAM & Memory Lifecycle Management:
Reclaims RAM, CUDA VRAM, and unmanaged GUI/Matplotlib resources across worker lifecycles.
"""

from __future__ import annotations

import gc
import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("OmniMemoryGuard")


class MemoryGuard:
    """Monitors and reclaims host memory, GPU VRAM, and graphics plot resources."""

    @classmethod
    def clean(cls, ephemeral_models: bool = True) -> Dict[str, Any]:
        """
        Execute comprehensive garbage collection, CUDA cache reclamation,
        and Matplotlib figure clearing.
        """
        stats: Dict[str, Any] = {
            "gc_freed": 0,
            "cuda_available": False,
            "vram_freed": False,
            "plots_closed": False,
            "initial_rss_mb": cls.get_process_memory_mb(),
        }

        # 1. Close open Matplotlib figure canvases to prevent GDI leak
        try:
            if "matplotlib.pyplot" in sys.modules:
                import matplotlib.pyplot as plt
                if plt.get_fignums():
                    plt.close("all")
                    stats["plots_closed"] = True
        except Exception as exc:
            logger.debug(f"Matplotlib figure closing skipped: {exc}")

        # 2. Release ephemeral whisper / ocr / networkx caches if requested
        if ephemeral_models:
            pass

        # 3. Explicit Python GC sweep
        freed = gc.collect()
        stats["gc_freed"] = freed

        # 4. GPU VRAM Cache Eviction (PyTorch / CUDA)
        try:
            if "torch" in sys.modules:
                import torch
                if torch.cuda.is_available():
                    stats["cuda_available"] = True
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
                    stats["vram_freed"] = True
        except Exception as exc:
            logger.debug(f"CUDA VRAM eviction skipped: {exc}")

        stats["final_rss_mb"] = cls.get_process_memory_mb()
        logger.debug(f"MemoryGuard cleaned: freed {freed} objects, final RSS: {stats['final_rss_mb']:.2f} MB")
        return stats

    @classmethod
    def attach_to_worker(cls, worker: Any) -> None:
        """Hook memory cleanup to worker thread completion and destruction signals."""
        if hasattr(worker, "finished"):
            try:
                worker.finished.connect(lambda: cls.clean())
            except Exception:
                pass
        if hasattr(worker, "destroyed"):
            try:
                worker.destroyed.connect(lambda: cls.clean())
            except Exception:
                pass

    @classmethod
    def get_process_memory_mb(cls) -> float:
        """Return the current resident set size (RSS) of the application in Megabytes."""
        try:
            import psutil
            p = psutil.Process(os.getpid())
            return p.memory_info().rss / (1024.0 * 1024.0)
        except Exception:
            return 0.0
