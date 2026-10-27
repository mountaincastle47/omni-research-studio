"""System Health & Diagnostics Dialog: Subsystem test matrix with latency telemetry and troubleshooting."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import ConfigManager
from core.diagnostics import DiagnosticResult, SystemDiagnostics
from core.i18n import get_text


class DiagnosticDialog(QDialog):
    """Visual health check dashboard inspecting API, Local LLM, Audio, TTS, OCR, and SQLite FTS5."""

    def __init__(
        self,
        config_manager: ConfigManager,
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self._lang = lang
        self.setWindowTitle(get_text("diagnostic_title", self._lang))
        self.resize(880, 480)
        self._build_ui()
        self._run_diagnostics()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header card
        header = QFrame(self)
        header.setStyleSheet(
            "QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 10px; }"
        )
        hl = QHBoxLayout(header)
        desc = QLabel(
            "Comprehensive runtime diagnostic suite inspecting critical subsystems, network latency, and OS runtimes."
            if self._lang == "en"
            else "핵심 하위 시스템, 네트워크 지연 시간 및 OS 런타임 상태를 점검하는 종합 시스템 진단 대시보드입니다."
        )
        desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        hl.addWidget(desc)
        layout.addWidget(header)

        # Diagnostics Table
        self.table = QTableWidget(self)
        self.results_table = self.table
        headers = ["Subsystem", "Status", "Latency", "Diagnostics & Details", "Recommendation"] if self._lang == "en" else ["하위 시스템", "상태", "응답 지연", "세부 진단 결과", "권장 조치 사항"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #0B0F19; border: 1px solid #1E293B; border-radius: 6px; } "
            "QTableWidget::item { padding: 6px; font-size: 12px; } "
            "QHeaderView::section { background-color: #1E293B; color: #94A3B8; padding: 6px; font-weight: 600; border: none; }"
        )
        layout.addWidget(self.table, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_rerun = QPushButton(get_text("diagnostic_run_btn", self._lang), self)
        self.btn_rerun.setStyleSheet("background-color: #0284C7; color: #FFFFFF; font-weight: 700; border-radius: 4px; padding: 6px 16px;")
        self.btn_rerun.clicked.connect(self._run_diagnostics)
        btn_layout.addWidget(self.btn_rerun)

        btn_layout.addStretch(1)

        self.btn_close = QPushButton("Close" if self._lang == "en" else "닫기", self)
        self.btn_close.setStyleSheet("background-color: #334155; color: #F1F5F9; border-radius: 4px; padding: 6px 18px;")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _run_diagnostics(self) -> None:
        self.btn_rerun.setEnabled(False)
        self.btn_rerun.setText("Diagnosing..." if self._lang == "en" else "진단 중...")

        results = SystemDiagnostics.run_all_diagnostics(self.config_manager)

        self.table.setRowCount(len(results))
        for row, res in enumerate(results):
            # 0. Subsystem Name
            self.table.setItem(row, 0, QTableWidgetItem(res.name))

            # 1. Status Badge
            status_item = QTableWidgetItem()
            if res.status == "PASS":
                status_item.setText("  PASS ✓  ")
                status_item.setForeground(Qt.GlobalColor.green)
            elif res.status == "WARN":
                status_item.setText("  WARN ⚠  ")
                status_item.setForeground(Qt.GlobalColor.yellow)
            else:
                status_item.setText("  FAIL ✗  ")
                status_item.setForeground(Qt.GlobalColor.red)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, status_item)

            # 2. Latency
            lat_str = f"{res.latency_ms:.1f} ms" if res.latency_ms > 0 else "—"
            lat_item = QTableWidgetItem(lat_str)
            lat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, lat_item)

            # 3. Details
            self.table.setItem(row, 3, QTableWidgetItem(res.details))

            # 4. Recommendation
            rec_item = QTableWidgetItem(res.recommendation)
            if res.status == "FAIL":
                rec_item.setForeground(Qt.GlobalColor.red)
            elif res.status == "WARN":
                rec_item.setForeground(Qt.GlobalColor.yellow)
            self.table.setItem(row, 4, rec_item)

        self.btn_rerun.setEnabled(True)
        self.btn_rerun.setText(get_text("diagnostic_run_btn", self._lang))
