"""Diagnostic timeout popup dialog triggered by worker watchdog abort."""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QWidget,
)

from core.i18n import get_text


class DiagnosticTimeoutDialog(QDialog):
    """
    Diagnostic dialog displayed when a background worker exceeds the 60-second inactivity limit.
    Provides root cause diagnostics, mitigation advice, and audio chime.
    """

    def __init__(
        self,
        current_stage: str = "OmniSweep Discovery",
        elapsed_seconds: float = 60.0,
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DiagnosticTimeoutDialog")
        self._lang = lang
        self._stage = current_stage
        self._elapsed = elapsed_seconds

        self.setWindowTitle(get_text("timeout_dialog_title", self._lang))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFixedSize(520, 360)
        self.setStyleSheet(
            "QDialog { background-color: #0D1117; color: #F0F6FC; border: 1px solid #30363D; border-radius: 8px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # Header warning box
        header_frame = QFrame()
        header_frame.setStyleSheet(
            "QFrame { background-color: #2D1515; border: 1px solid #E5534B; border-radius: 6px; padding: 10px; }"
        )
        h_layout = QVBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(4)

        header_label = QLabel(f"⚠️ {get_text('timeout_dialog_header', self._lang)}")
        header_label.setWordWrap(True)
        header_label.setStyleSheet("color: #FF7B72; font-size: 12px; font-weight: 700; border: none; background: transparent;")
        h_layout.addWidget(header_label)

        sub_label = QLabel(
            f"Stage: {self._stage} | Inactivity: {self._elapsed:.1f}s (Threshold: 60s)"
            if self._lang == "en"
            else f"중단 단계: {self._stage} | 무응답 시간: {self._elapsed:.1f}초 (기준: 60초)"
        )
        sub_label.setStyleSheet("color: #C9D1D9; font-size: 11px; border: none; background: transparent;")
        h_layout.addWidget(sub_label)
        layout.addWidget(header_frame)

        # Causes list
        causes_label = QLabel(get_text("timeout_dialog_causes", self._lang))
        causes_label.setWordWrap(True)
        causes_label.setStyleSheet("color: #8B949E; font-size: 11px; line-height: 1.4;")
        layout.addWidget(causes_label)

        # Recommendations list
        recs_label = QLabel(get_text("timeout_dialog_recommendations", self._lang))
        recs_label.setWordWrap(True)
        recs_label.setStyleSheet("color: #58A6FF; font-size: 11px; line-height: 1.4;")
        layout.addWidget(recs_label)

        layout.addStretch(1)

        # Single OK button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setObjectName("TimeoutOkBtn")
        self.ok_btn.setFixedSize(90, 30)
        self.ok_btn.setStyleSheet(
            "QPushButton { background-color: #21262D; color: #F0F6FC; border: 1px solid #30363D; "
            "border-radius: 4px; font-size: 12px; font-weight: 600; } "
            "QPushButton:hover { background-color: #30363D; border-color: #8B949E; }"
        )
        self.ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.ok_btn)

        layout.addLayout(btn_layout)


def play_warning_alert() -> None:
    """Trigger system warning sound on watchdog timeout."""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        try:
            from PyQt6.QtWidgets import QApplication
            QApplication.beep()
        except Exception:
            pass
