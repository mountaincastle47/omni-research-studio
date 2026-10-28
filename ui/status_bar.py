"""Status bar component with font-metric dynamic ETA prefix, jitter-free value labels, and busy spinner."""

from __future__ import annotations

import time
from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
)

from core.i18n import get_text

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class StatusEtaWidget(QWidget):
    """
    Timer widget splitting ETA into two distinct labels:
    - eta_prefix_label: Displays 'ETA:' or '남은 시간:' with dynamic width based on font metrics.
    - eta_value_label: Displays only dynamic digits ('~43s', '~8s') with fixed 55px width and right alignment.
    """

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusEtaWidget")
        self._lang = lang
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Dynamic width prefix label
        self.eta_prefix_label = QLabel("")
        self.eta_prefix_label.setObjectName("StatusEtaPrefixLabel")
        self.eta_prefix_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.eta_prefix_label.setStyleSheet(
            "color: #8B949E; font-size: 12px; font-weight: 500; border: none; background: transparent;"
        )

        # Fixed width 55px value label
        self.eta_value_label = QLabel("")
        self.eta_value_label.setObjectName("StatusEtaValueLabel")
        self.eta_value_label.setFixedWidth(55)
        self.eta_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.eta_value_label.setStyleSheet(
            "color: #58A6FF; font-size: 12px; font-weight: 600; border: none; background: transparent;"
        )

        layout.addWidget(self.eta_prefix_label)
        layout.addWidget(self.eta_value_label)

    def set_eta(self, eta_seconds: int, is_ready: bool = False, elapsed_seconds: int = 0) -> None:
        """Update ETA with font-metric sizing for the prefix and jitter-free value formatting."""
        if is_ready:
            self.eta_prefix_label.setText("")
            self.eta_prefix_label.setFixedWidth(0)
            self.eta_value_label.setText(get_text("eta_ready", self._lang))
            return

        if eta_seconds > 1:
            prefix_text = "남은 시간:" if self._lang == "ko" else "ETA:"
            self.eta_prefix_label.setText(prefix_text)
            fm = self.eta_prefix_label.fontMetrics()
            prefix_width = fm.horizontalAdvance(prefix_text) + 4
            self.eta_prefix_label.setFixedWidth(prefix_width)
            self.eta_value_label.setFixedWidth(55)
            self.eta_value_label.setText(f"~{eta_seconds}s")
        elif elapsed_seconds > 0:
            self.set_elapsed(elapsed_seconds)
        else:
            self.eta_prefix_label.setText("")
            self.eta_prefix_label.setFixedWidth(0)
            self.eta_value_label.setText("")

    def set_elapsed(self, elapsed_seconds: int) -> None:
        """Display dynamic elapsed time counter when ETA drops or becomes indeterminate."""
        m, s = divmod(max(0, elapsed_seconds), 60)
        time_str = f"{m}m {s:02d}s" if m > 0 else f"{s}s"
        prefix_text = "경과:" if self._lang == "ko" else "Elapsed:"
        self.eta_prefix_label.setText(prefix_text)
        fm = self.eta_prefix_label.fontMetrics()
        prefix_width = fm.horizontalAdvance(prefix_text) + 4
        self.eta_prefix_label.setFixedWidth(prefix_width)
        val_width = max(55, fm.horizontalAdvance(time_str) + 12)
        self.eta_value_label.setFixedWidth(val_width)
        self.eta_value_label.setText(time_str)

    def clear(self) -> None:
        """Clear both prefix and value labels."""
        self.eta_prefix_label.setText("")
        self.eta_prefix_label.setFixedWidth(0)
        self.eta_value_label.setText("")

    def set_language(self, lang: str) -> None:
        """Update active language."""
        self._lang = lang


class OmniStatusBar(QWidget):
    """Bottom status bar strip containing status text, animated spinner, ETA widget, progress bar, and cancel button."""

    cancel_requested = pyqtSignal()

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._spinner_idx = 0
        self._task_start_time: Optional[float] = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFixedHeight(30)
        self.setStyleSheet("background-color: #161B22; border-top: 1px solid #30363D;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # Rotating spinner indicator
        self.spinner_label = QLabel("")
        self.spinner_label.setObjectName("StatusSpinnerLabel")
        self.spinner_label.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: bold; border: none; background: transparent;")
        self.spinner_label.setFixedWidth(16)
        self.spinner_label.setVisible(False)
        layout.addWidget(self.spinner_label)

        self.spinner_timer = QTimer(self)
        self.spinner_timer.setInterval(100)
        self.spinner_timer.timeout.connect(self._on_spinner_tick)

        # Status text
        self.status_label = QLabel(get_text("status_ready", self._lang) or "Ready")
        self.status_label.setStyleSheet("color: #C9D1D9; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(self.status_label, stretch=1)

        # Right-aligned controls
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        controls_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.eta_widget = StatusEtaWidget(lang=self._lang, parent=self)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("StatusProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedWidth(210)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.btn_cancel = QPushButton(get_text("btn_cancel", self._lang))
        self.btn_cancel.setObjectName("CancelTaskBtn")
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)

        controls_layout.addWidget(self.eta_widget)
        controls_layout.addWidget(self.progress_bar)
        controls_layout.addWidget(self.btn_cancel)

        layout.addLayout(controls_layout)

    def _on_spinner_tick(self) -> None:
        self._spinner_idx = (self._spinner_idx + 1) % len(SPINNER_FRAMES)
        self.spinner_label.setText(SPINNER_FRAMES[self._spinner_idx])

    def start_busy(self, initial_text: str = "") -> None:
        """Start animated busy spinner and indeterminate progress animation."""
        self._task_start_time = time.monotonic()
        self.spinner_label.setText(SPINNER_FRAMES[0])
        self.spinner_label.setVisible(True)
        self.spinner_timer.start()
        self.progress_bar.setRange(0, 0)  # Continuous pulse animation
        if initial_text:
            self.set_status(initial_text)
        self.show_cancel(True)

    def set_status(self, text: str) -> None:
        # Check if text is a known locale token
        token = text.strip()
        if token in ("omnisweep_phase_1", "omnisweep_phase_2", "omnisweep_phase_3", "omnisweep_phase_4", "status_ready"):
            text = get_text(token, self._lang)
        self.status_label.setText(text)

    def set_progress(self, percentage: int, eta_seconds: int = 0, is_ready: bool = False) -> None:
        if percentage > 0:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(max(0, min(100, percentage)))
        else:
            self.progress_bar.setRange(0, 0)

        if is_ready or percentage >= 100:
            self._task_start_time = None
            self.eta_widget.set_eta(0, is_ready=True)
            return

        if self._task_start_time is None:
            self._task_start_time = time.monotonic()
        elapsed_sec = int(time.monotonic() - self._task_start_time)

        if eta_seconds > 1:
            self.eta_widget.set_eta(eta_seconds, is_ready=False)
        else:
            self.eta_widget.set_eta(0, is_ready=False, elapsed_seconds=elapsed_sec)

    def reset_state(self) -> None:
        """Clean state reset on task completion, cancellation, or watchdog timeout."""
        self._task_start_time = None
        self.spinner_timer.stop()
        self.spinner_label.setText("")
        self.spinner_label.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(get_text("status_ready", self._lang) or "Ready")
        self.eta_widget.clear()
        self.show_cancel(False)

    def show_cancel(self, show: bool = True) -> None:
        self.btn_cancel.setVisible(show)
        self.btn_cancel.setEnabled(show)

    def retranslate_ui(self, lang: str) -> None:
        self._lang = lang
        self.eta_widget.set_language(lang)
        self.btn_cancel.setText(get_text("btn_cancel", lang))
        if self.progress_bar.value() == 0 and not self.spinner_timer.isActive():
            self.status_label.setText(get_text("status_ready", self._lang) or "Ready")
