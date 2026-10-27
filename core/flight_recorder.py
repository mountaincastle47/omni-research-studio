"""Blackbox Flight Recorder & Crash Recovery: sys.excepthook diagnostics and state snapshots."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import traceback
from typing import Any, Dict, Optional

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.i18n import get_text
from core.paths import get_cache_dir, get_logs_dir, LOGS_DIR, SESSION_CACHE_DIR

CRASH_DUMP_FILE = get_cache_dir() / "crash_dump.json"
SESSION_LOG_FILE = get_logs_dir() / "omni_session.log"


class FlightRecorder:
    """Manages rotating session logs, state snapshots, and global unhandled exception trapping."""

    _installed: bool = False
    _original_excepthook = None
    _in_flight_state: Dict[str, Any] = {}
    _logger: Optional[logging.Logger] = None

    @classmethod
    def get_logger(cls) -> logging.Logger:
        if cls._logger is None:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            logger = logging.getLogger("OmniFlightRecorder")
            logger.setLevel(logging.INFO)

            handler = RotatingFileHandler(
                SESSION_LOG_FILE,
                maxBytes=10 * 1024 * 1024,  # 10 MB ceiling
                backupCount=3,
                encoding="utf-8",
            )
            formatter = logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s:%(threadName)s] %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            cls._logger = logger
        return cls._logger

    @classmethod
    def install(cls) -> None:
        """Register the blackbox flight recorder exception hook."""
        if cls._installed:
            return

        cls.get_logger().info("Blackbox Flight Recorder engaged.")
        cls._original_excepthook = sys.excepthook
        sys.excepthook = cls._on_unhandled_exception
        cls._installed = True

    @classmethod
    def uninstall(cls) -> None:
        """Restore original sys.excepthook."""
        if cls._installed and cls._original_excepthook:
            sys.excepthook = cls._original_excepthook
            cls._installed = False

    @classmethod
    def update_flight_state(cls, key: str, val: Any) -> None:
        """Record live application state for recovery snapshotting."""
        cls._in_flight_state[key] = val

    @classmethod
    def record_event(cls, category: str, detail: str) -> None:
        """Log an operational event."""
        cls.get_logger().info(f"[{category}] {detail}")

    @classmethod
    def _on_unhandled_exception(cls, exc_type, exc_value, exc_traceback) -> None:
        """Global exception trap writing traceback to rotating log and saving crash dump."""
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        cls.get_logger().critical(f"FATAL UNHANDLED EXCEPTION:\n{tb_str}")

        # Write crash dump JSON
        SESSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        dump_data = {
            "timestamp": str(exc_type.__name__),
            "error_type": str(exc_type.__name__),
            "error_message": str(exc_value),
            "traceback": tb_str,
            "flight_state": dict(cls._in_flight_state),
        }

        try:
            CRASH_DUMP_FILE.write_text(json.dumps(dump_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as write_err:
            cls.get_logger().error(f"Failed to write crash dump: {write_err}")

        # Delegate to original excepthook
        if cls._original_excepthook:
            cls._original_excepthook(exc_type, exc_value, exc_traceback)

    @classmethod
    def has_crash_dump(cls) -> bool:
        """Return True if a previous abnormal termination dump exists."""
        return CRASH_DUMP_FILE.exists() and CRASH_DUMP_FILE.stat().st_size > 0

    @classmethod
    def read_crash_dump(cls) -> Optional[Dict[str, Any]]:
        """Read and parse existing crash dump."""
        if not cls.has_crash_dump():
            return None
        try:
            return json.loads(CRASH_DUMP_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None

    @classmethod
    def clear_crash_dump(cls) -> None:
        """Remove existing crash dump after recovery or dismissal."""
        try:
            CRASH_DUMP_FILE.unlink(missing_ok=True)
        except Exception:
            pass


class CrashRecoveryDialog(QDialog):
    """Presents previous crash dump diagnostics and offers session state recovery."""

    def __init__(self, dump_data: Dict[str, Any], lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.dump_data = dump_data
        self._lang = lang
        self.should_restore: bool = False

        self.setWindowTitle(get_text("crash_recovery_title", self._lang))
        self.resize(780, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header Prompt
        hdr = QLabel(get_text("crash_recovery_prompt", self._lang))
        hdr.setWordWrap(True)
        hdr.setStyleSheet("color: #F87171; font-weight: 700; font-size: 13px;")
        layout.addWidget(hdr)

        # Trace Details Box
        self.trace_box = QTextEdit(self)
        self.trace_box.setReadOnly(True)
        self.trace_box.setStyleSheet(
            "QTextEdit { background-color: #0B0E14; color: #FCA5A5; font-family: Consolas, monospace; "
            "font-size: 11px; border: 1px solid #1E293B; border-radius: 6px; padding: 8px; }"
        )

        trace_content = (
            f"Error: {self.dump_data.get('error_type')}: {self.dump_data.get('error_message')}\n\n"
            f"Stack Trace:\n{self.dump_data.get('traceback', 'No traceback available.')}\n\n"
            f"In-Flight State Snapshot:\n{json.dumps(self.dump_data.get('flight_state', {}), indent=2)}"
        )
        self.trace_box.setPlainText(trace_content)
        layout.addWidget(self.trace_box, stretch=1)

        # Bottom Button Row
        btn_row = QHBoxLayout()

        btn_copy = QPushButton(get_text("crash_copy_trace_btn", self._lang), self)
        btn_copy.setStyleSheet("QPushButton { background-color: #1E293B; color: #38BDF8; border: 1px solid #334155; border-radius: 4px; padding: 6px 14px; font-size: 11px; }")
        btn_copy.clicked.connect(self._copy_trace)
        btn_row.addWidget(btn_copy)

        btn_row.addStretch(1)

        btn_dismiss = QPushButton(get_text("crash_dismiss_btn", self._lang), self)
        btn_dismiss.setStyleSheet("QPushButton { background-color: #334155; color: #F1F5F9; border-radius: 4px; padding: 6px 14px; font-size: 11px; }")
        btn_dismiss.clicked.connect(self._on_dismiss)
        btn_row.addWidget(btn_dismiss)

        btn_restore = QPushButton(get_text("crash_restore_btn", self._lang), self)
        btn_restore.setStyleSheet("QPushButton { background-color: #0284C7; color: #FFFFFF; font-weight: 700; border-radius: 4px; padding: 6px 18px; font-size: 11px; }")
        btn_restore.clicked.connect(self._on_restore)
        btn_row.addWidget(btn_restore)

        layout.addLayout(btn_row)

    def _copy_trace(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.trace_box.toPlainText())

    def _on_restore(self) -> None:
        self.should_restore = True
        FlightRecorder.clear_crash_dump()
        self.accept()

    def _on_dismiss(self) -> None:
        self.should_restore = False
        FlightRecorder.clear_crash_dump()
        self.reject()
