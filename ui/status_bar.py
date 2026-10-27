"""Status bar component with font-metric dynamic ETA prefix and jitter-free fixed ETA value labels."""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
)

from core.i18n import get_text


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

    def set_eta(self, eta_seconds: int, is_ready: bool = False) -> None:
        """Update ETA with font-metric sizing for the prefix and jitter-free value formatting."""
        if is_ready:
            self.eta_prefix_label.setText("")
            self.eta_prefix_label.setFixedWidth(0)
            self.eta_value_label.setText(get_text("eta_ready", self._lang))
            return

        if eta_seconds > 0:
            prefix_text = "남은 시간:" if self._lang == "ko" else "ETA:"
            self.eta_prefix_label.setText(prefix_text)
            fm = self.eta_prefix_label.fontMetrics()
            prefix_width = fm.horizontalAdvance(prefix_text) + 4
            self.eta_prefix_label.setFixedWidth(prefix_width)
            self.eta_value_label.setText(f"~{eta_seconds}s")
        else:
            self.eta_prefix_label.setText("")
            self.eta_prefix_label.setFixedWidth(0)
            self.eta_value_label.setText("")

    def clear(self) -> None:
        """Clear both prefix and value labels."""
        self.eta_prefix_label.setText("")
        self.eta_prefix_label.setFixedWidth(0)
        self.eta_value_label.setText("")

    def set_language(self, lang: str) -> None:
        """Update active language."""
        self._lang = lang


class OmniStatusBar(QWidget):
    """Bottom status bar strip containing status text, ETA widget, progress bar, and cancel button."""

    cancel_requested = pyqtSignal()

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFixedHeight(30)
        self.setStyleSheet("background-color: #161B22; border-top: 1px solid #30363D;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        # Status text
        self.status_label = QLabel(get_text("welcome_step1", self._lang))
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

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_progress(self, percentage: int, eta_seconds: int = 0, is_ready: bool = False) -> None:
        self.progress_bar.setValue(max(0, min(100, percentage)))
        self.eta_widget.set_eta(eta_seconds, is_ready=is_ready)

    def show_cancel(self, show: bool = True) -> None:
        self.btn_cancel.setVisible(show)
        self.btn_cancel.setEnabled(show)

    def retranslate_ui(self, lang: str) -> None:
        self._lang = lang
        self.eta_widget.set_language(lang)
        self.btn_cancel.setText(get_text("btn_cancel", lang))
