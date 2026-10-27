"""API Key configuration modal dialog with constrained geometry and password masking."""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QLayout,
    QWidget,
)

from core.i18n import get_text
from core.config_manager import ConfigManager


class ApiKeyDialog(QDialog):
    """Constrained modal dialog for managing Google Gemini API Key."""

    def __init__(self, initial_key: str = "", lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ApiKeyDialog")
        self._lang = lang
        self._config_manager = ConfigManager()
        self._current_key = (initial_key or self._config_manager.get_api_key()).strip()

        self.setWindowTitle("Gemini API Key")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        # Fix size constraint to prevent horizontal or vertical layout deformation
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        desc_label = QLabel(
            "Enter your Google Gemini API Key. Keys are securely stored in OS user-space storage."
            if lang == "en"
            else "Google Gemini API 키를 입력하세요. API 키는 OS 사용자 공간에 안전하게 저장됩니다."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        layout.addWidget(desc_label)

        # Constrained input box
        self.key_input = QLineEdit()
        self.key_input.setObjectName("ApiKeyInput")
        self.key_input.setMaximumWidth(320)
        self.key_input.setFixedWidth(320)
        self.key_input.setFixedHeight(28)
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("GEMINI_API_KEY...")
        self.key_input.setText(self._current_key)
        self.key_input.setCursorPosition(0)
        layout.addWidget(self.key_input)

        # Button Row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.clear_btn = QPushButton(get_text("btn_clear_key", self._lang))
        self.clear_btn.setStyleSheet(
            "QPushButton { background-color: #3F1B24; color: #F87171; border: 1px solid #7F1D1D; "
            "border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #7F1D1D; color: #FECACA; }"
        )
        self.clear_btn.clicked.connect(self._on_clear_clicked)

        self.save_btn = QPushButton(get_text("btn_apply_key", self._lang))
        self.save_btn.setStyleSheet(
            "QPushButton { background-color: #0284C7; color: #FFFFFF; border: none; "
            "border-radius: 4px; padding: 4px 14px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #0369A1; }"
        )
        self.save_btn.clicked.connect(self._on_save_clicked)

        self.cancel_btn = QPushButton(get_text("btn_cancel", self._lang))
        self.cancel_btn.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #94A3B8; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 12px; font-size: 11px; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def _on_save_clicked(self) -> None:
        key = self.key_input.text().strip()
        self._config_manager.save_api_key(key)
        self.accept()

    def _on_clear_clicked(self) -> None:
        self.key_input.clear()
        self._config_manager.clear_api_key()
