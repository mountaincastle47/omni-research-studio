"""Embedded Python REPL & Mathematical Verification Sandbox:
Provides safe, restricted empirical computation, telemetry verification, and Matplotlib plotting.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import io
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

from core.paths import get_cache_dir

logger = logging.getLogger("OmniMathSandbox")

PLOTS_DIR = get_cache_dir() / "plots"


class SandboxResult:
    """Execution telemetry and output payload from the Math Sandbox."""

    def __init__(
        self,
        success: bool,
        stdout: str = "",
        stderr: str = "",
        plots: Optional[List[str]] = None,
        execution_time_ms: float = 0.0,
        error_message: str = "",
    ) -> None:
        self.success = success
        self.stdout = stdout
        self.stderr = stderr
        self.plots = plots or []
        self.execution_time_ms = execution_time_ms
        self.error_message = error_message

    def to_markdown(self) -> str:
        """Format the output and plot references into Markdown."""
        lines = ["\n### Mathematical Verification Output\n"]
        if self.stdout:
            lines.append(f"```text\n{self.stdout.strip()}\n```\n")
        if self.error_message:
            lines.append(f"**Error:** `{self.error_message}`\n")
        for p in self.plots:
            lines.append(f"![Verification Plot]({p})\n")
        return "\n".join(lines)


SAFE_MODULES = {
    "math", "numpy", "np", "matplotlib", "matplotlib.pyplot", "plt",
    "json", "re", "time", "datetime", "scipy", "random",
}


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if root not in SAFE_MODULES:
        raise ImportError(f"Module '{name}' is restricted in Math Sandbox. Permitted: math, numpy, matplotlib, json, re, time, datetime.")
    return __import__(name, globals, locals, fromlist, level)


class MathSandbox:
    """Restricted execution runner for mathematical calculations and telemetry modeling."""

    ALLOWED_BUILTINS = {
        "abs": abs,
        "all": all,
        "any": any,
        "bin": bin,
        "bool": bool,
        "bytearray": bytearray,
        "bytes": bytes,
        "chr": chr,
        "complex": complex,
        "dict": dict,
        "divmod": divmod,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "format": format,
        "frozenset": frozenset,
        "hash": hash,
        "hex": hex,
        "int": int,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "iter": iter,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "next": next,
        "oct": oct,
        "ord": ord,
        "pow": pow,
        "print": print,
        "range": range,
        "repr": repr,
        "reversed": reversed,
        "round": round,
        "set": set,
        "slice": slice,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "type": type,
        "zip": zip,
        "Exception": Exception,
        "ValueError": ValueError,
        "TypeError": TypeError,
        "IndexError": IndexError,
        "KeyError": KeyError,
        "ZeroDivisionError": ZeroDivisionError,
        "math": None,
    }

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds
        PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    def execute_script(self, code: str) -> SandboxResult:
        """Execute user script within an isolated sandbox environment with a strict timeout."""
        import threading
        res_container: List[Optional[SandboxResult]] = [None]
        exc_container: List[Optional[Exception]] = [None]

        def _worker():
            try:
                res_container[0] = self._run_isolated(code)
            except Exception as e:
                exc_container[0] = e

        t = threading.Thread(target=_worker, daemon=True, name="MathSandboxThread")
        t.start()
        t.join(timeout=self.timeout_seconds)

        if t.is_alive():
            return SandboxResult(
                success=False,
                error_message=f"Execution timed out ({self.timeout_seconds}s limit exceeded).",
            )
        if exc_container[0] is not None:
            return SandboxResult(
                success=False,
                error_message=str(exc_container[0]),
            )
        return res_container[0] or SandboxResult(success=False, error_message="No execution result produced.")

    def _run_isolated(self, code: str) -> SandboxResult:
        start_time = time.perf_counter()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        # Track existing plots before run
        existing_plots = set(PLOTS_DIR.glob("*.png"))

        # Pre-import safe math & plotting modules
        import math
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")  # Headless backend
        import matplotlib.pyplot as plt
        import json
        import re

        # Restricted file open: allows reading/writing ONLY inside cache directory (or local session_cache)
        def restricted_open(file, mode="r", *args, **kwargs):
            p = Path(file).resolve()
            cache_root = get_cache_dir().resolve()
            local_cache = Path("session_cache").resolve()
            in_cache = False
            try:
                p.relative_to(cache_root)
                in_cache = True
            except ValueError:
                pass
            if not in_cache:
                try:
                    p.relative_to(local_cache)
                    in_cache = True
                except ValueError:
                    pass
            if not in_cache:
                raise PermissionError(f"Access denied: Path '{p}' is outside cache directory")
            return open(p, mode, *args, **kwargs)

        safe_builtins = dict(self.ALLOWED_BUILTINS)
        safe_builtins["open"] = restricted_open
        safe_builtins["math"] = math
        safe_builtins["__import__"] = safe_import

        # Custom namespace
        namespace: Dict[str, Any] = {
            "__builtins__": safe_builtins,
            "math": math,
            "np": np,
            "numpy": np,
            "plt": plt,
            "matplotlib": matplotlib,
            "json": json,
            "re": re,
            "PLOTS_DIR": str(PLOTS_DIR),
        }

        # Clear any dangling matplotlib figures
        plt.close("all")

        success = True
        err_msg = ""

        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                # Pre-compile to catch syntax errors cleanly
                compiled = compile(code, "<sandbox>", "exec")
                exec(compiled, namespace)

                # If the script generated a matplotlib figure but didn't save, auto-save it
                if plt.get_fignums():
                    timestamp = int(time.time() * 1000)
                    auto_plot = PLOTS_DIR / f"plot_{timestamp}.png"
                    plt.savefig(auto_plot, dpi=150, bbox_inches="tight")
                    plt.close("all")

            except Exception as exc:
                success = False
                err_msg = f"{type(exc).__name__}: {str(exc)}"
                print(f"Error: {err_msg}", file=stderr_buf)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Detect any new plots
        current_plots = set(PLOTS_DIR.glob("*.png"))
        new_plots = sorted([str(p.as_posix()) for p in (current_plots - existing_plots)])

        return SandboxResult(
            success=success,
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            plots=new_plots,
            execution_time_ms=elapsed_ms,
            error_message=err_msg,
        )
