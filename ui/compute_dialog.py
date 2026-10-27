"""Compute & Hardware Acceleration Management Dialog for OmniResearch Studio."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.compute_manager import ComputeManager
from core.i18n import get_text


class ComputeDialog(QDialog):
    """Modal dialog displaying active hardware telemetry and allowing execution provider switching."""

    provider_changed = pyqtSignal(str)

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.lang = lang
        self.compute_mgr = ComputeManager.get_instance()
        self.setWindowTitle(get_text("compute_dialog_title", self.lang))
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Telemetry Card
        telemetry_frame = QFrame(self)
        telemetry_frame.setStyleSheet(
            "QFrame { background-color: #161B22; border: 1px solid #30363D; border-radius: 6px; padding: 12px; }"
        )
        form_layout = QFormLayout(telemetry_frame)
        form_layout.setSpacing(10)

        p = self.compute_mgr.profile

        self.lbl_active_dev = QLabel(p.display_name)
        self.lbl_active_dev.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 13px;")
        form_layout.addRow(get_text("compute_active_provider", self.lang), self.lbl_active_dev)

        self.lbl_threads = QLabel(f"{p.cpu_cores} threads")
        self.lbl_threads.setStyleSheet("color: #E2E8F0; font-weight: 500;")
        form_layout.addRow(get_text("compute_thread_count", self.lang), self.lbl_threads)

        self.lbl_precision = QLabel(f"{p.precision.upper()} Quantized" if p.precision == "int8" else f"{p.precision.upper()} Native")
        self.lbl_precision.setStyleSheet("color: #34D399; font-weight: bold;")
        form_layout.addRow(get_text("compute_quantization", self.lang), self.lbl_precision)

        gpu_info = p.gpu_name or ("None (Host CPU Only)" if self.lang == "en" else "없음 (호스트 CPU 사용)")
        self.lbl_gpu = QLabel(gpu_info)
        self.lbl_gpu.setStyleSheet("color: #E2E8F0;")
        form_layout.addRow(get_text("compute_hardware_info", self.lang), self.lbl_gpu)

        layout.addWidget(telemetry_frame)

        # Provider Selector Section
        sel_label = QLabel(get_text("compute_onnx_providers", self.lang))
        sel_label.setStyleSheet("font-weight: bold; color: #F8FAFC;")
        layout.addWidget(sel_label)

        self.combo_providers = QComboBox(self)
        self.combo_providers.setStyleSheet(
            "QComboBox { background-color: #0F172A; color: #F8FAFC; border: 1px solid #334155; "
            "padding: 6px 10px; border-radius: 4px; font-size: 12px; }"
        )
        self.supported = self.compute_mgr.get_supported_providers()
        current_type = p.device_type

        sel_idx = 0
        for idx, prov in enumerate(self.supported):
            detected_txt = "✓ Detected" if prov["available"] else "Not Detected"
            if self.lang == "ko":
                detected_txt = "✓ 감지됨" if prov["available"] else "감지 안 됨"
            label = f"{prov['name']} [{detected_txt}]"
            self.combo_providers.addItem(label, prov["id"])
            if prov["device_type"] == current_type:
                sel_idx = idx

        self.combo_providers.setCurrentIndex(sel_idx)
        layout.addWidget(self.combo_providers)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_apply = QPushButton(get_text("compute_btn_switch", self.lang), self)
        self.btn_apply.setStyleSheet(
            "QPushButton { background-color: #2563EB; color: white; font-weight: bold; "
            "padding: 6px 16px; border-radius: 4px; border: none; } "
            "QPushButton:hover { background-color: #1D4ED8; }"
        )
        self.btn_apply.clicked.connect(self._on_apply_provider)
        btn_layout.addWidget(self.btn_apply)

        self.btn_close = QPushButton("Close" if self.lang == "en" else "닫기", self)
        self.btn_close.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #94A3B8; "
            "padding: 6px 14px; border-radius: 4px; border: 1px solid #334155; } "
            "QPushButton:hover { background-color: #334155; color: white; }"
        )
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _on_apply_provider(self) -> None:
        chosen_id = self.combo_providers.currentData()
        if chosen_id:
            new_profile = self.compute_mgr.set_provider(chosen_id)
            self.lbl_active_dev.setText(new_profile.display_name)
            self.lbl_precision.setText(
                f"{new_profile.precision.upper()} Quantized"
                if new_profile.precision == "int8"
                else f"{new_profile.precision.upper()} Native"
            )
            self.lbl_gpu.setText(new_profile.gpu_name or ("None (Host CPU Only)" if self.lang == "en" else "없음 (호스트 CPU 사용)"))
            self.provider_changed.emit(chosen_id)
            QMessageBox.information(
                self,
                get_text("compute_dialog_title", self.lang),
                get_text("compute_status_applied", self.lang),
            )
