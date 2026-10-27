"""Process Sandboxing for Ingestion: OS Segfault Immunity and Process Isolation."""

from __future__ import annotations

import concurrent.futures
from concurrent.futures.process import BrokenProcessPool
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.document_loader import SourceDocument, load_docx, load_pdf

DEFAULT_INGESTION_TIMEOUT_SECONDS = 45.0


def _extract_document_isolated(file_path: str) -> Dict[str, Any]:
    """
    Top-level standalone extraction worker running inside an isolated child subprocess.
    If a C-level library (MuPDF, RapidOCR, libxml2) segfaults or dumps core, only
    this child worker terminates, leaving the parent GUI process completely intact.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = path.suffix.lower()
    if ext == ".pdf":
        res = load_pdf(path)
        return {
            "success": True,
            "crashed": False,
            "content": res.get("content", ""),
            "page_count": res.get("page_count", 1),
            "has_ocr": res.get("has_ocr", False),
            "figures": res.get("figures", []),
            "source_type": "local_pdf",
        }
    elif ext == ".docx":
        res = load_docx(path)
        return {
            "success": True,
            "crashed": False,
            "content": res.get("content", ""),
            "page_count": res.get("page_count", 1),
            "has_ocr": False,
            "figures": [],
            "source_type": "local_docx",
        }
    else:
        # Plain text / Markdown with chardet encoding detection
        from core.document_loader import DocumentCorpus
        content = DocumentCorpus._extract_text(path)
        return {
            "success": True,
            "crashed": False,
            "content": content,
            "page_count": 1,
            "has_ocr": False,
            "figures": [],
            "source_type": "local_md" if ext in {".md", ".markdown"} else "local_txt",
        }


class ExtractionSubprocessCrashError(RuntimeError):
    """Raised when an extraction subprocess terminates abnormally or segfaults."""


class SandboxedDocumentLoader:
    """
    Manages an isolated subprocess pool for document parsing with strict timeout
    guards and automatic recovery from native worker crashes.
    """

    _instance: Optional[SandboxedDocumentLoader] = None

    def __init__(self, max_workers: int = 2, timeout_seconds: float = DEFAULT_INGESTION_TIMEOUT_SECONDS) -> None:
        self.max_workers = max_workers
        self.timeout_seconds = timeout_seconds
        self._executor: Optional[concurrent.futures.ProcessPoolExecutor] = None
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> SandboxedDocumentLoader:
        if cls._instance is None:
            cls._instance = SandboxedDocumentLoader()
        return cls._instance

    def _get_executor(self) -> concurrent.futures.ProcessPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers)
            return self._executor

    def _reset_executor(self) -> None:
        with self._lock:
            if self._executor is not None:
                try:
                    self._executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                self._executor = None

    def extract_document(
        self,
        file_path: str | Path,
        timeout: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Extract text and metadata from file_path inside an isolated subprocess.
        Guarantees that child segfaults or infinite loops do not crash the host process.
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        to_sec = timeout_seconds if timeout_seconds is not None else (timeout if timeout is not None else self.timeout_seconds)
        executor = self._get_executor()

        try:
            future = executor.submit(_extract_document_isolated, str(path))
            result = future.result(timeout=to_sec)
            return result
        except concurrent.futures.TimeoutError:
            self._reset_executor()
            return {
                "success": False,
                "crashed": False,
                "timeout": True,
                "error": f"Document extraction timed out after {to_sec}s.",
                "content": f"[EXTRACTION_TIMEOUT: Processing exceeded {to_sec}s] {path.name}",
                "title": f"[EXTRACTION_TIMEOUT] {path.name}",
                "page_count": 1,
                "source_type": "local_error",
                "figures": [],
                "has_ocr": False,
            }
        except (BrokenProcessPool, ProcessLookupError) as exc:
            self._reset_executor()
            return {
                "success": False,
                "crashed": True,
                "timeout": False,
                "error": f"Subprocess terminated abnormally (possible segfault): {exc}",
                "content": f"[EXTRACTION_FAILED: Corrupted Native Binary/Bitmap] {path.name}\n\nWarning: Parsing process terminated abnormally.",
                "title": f"[EXTRACTION_FAILED: Corrupted Native Binary/Bitmap] {path.name}",
                "page_count": 1,
                "source_type": "local_error",
                "figures": [],
                "has_ocr": False,
            }
        except Exception as exc:
            return {
                "success": False,
                "crashed": False,
                "timeout": False,
                "error": str(exc),
                "content": f"[EXTRACTION_ERROR: {exc}] {path.name}",
                "title": f"[EXTRACTION_ERROR] {path.name}",
                "page_count": 1,
                "source_type": "local_error",
                "figures": [],
                "has_ocr": False,
            }

    def close(self) -> None:
        """Shutdown the process pool."""
        self._reset_executor()
