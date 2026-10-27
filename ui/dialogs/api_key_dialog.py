"""Dedicated modal dialog for managing Google Gemini API Key."""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from core.i18n import get_text
from core.config_manager import ConfigManager


class ApiKeyDialog(QDialog):
    """
    Dedicated modal dialog for entering or clearing Google Gemini API key.
    - ApplicationModal
    - Fixed dimension: 440 x 190
    - Password masked input field
    - Save Key (primary), Clear Key (destructive), Cancel (neutral)
    """

    key_saved = pyqtSignal(str)
    key_cleared = pyqtSignal()

    def __init__(self, initial_key: str = "", lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ApiKeyDialog")
        self._lang = lang
        self._config_manager = ConfigManager()
        self._current_key = (initial_key or self._config_manager.get_api_key()).strip()

        title = "Gemini API Key" if lang == "en" else "Gemini API 키 설정"
        self.setWindowTitle(title)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFixedSize(440, 190)
        self.setStyleSheet(
            "QDialog { background-color: #0D1117; color: #F0F6FC; border: 1px solid #30363D; border-radius: 8px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Explanatory persistence label
        info_text = (
            "API keys are stored strictly in local OS user-space (Windows Registry / %APPDATA%) "
            "and are never included in distributions or tracked in source control."
            if self._lang == "en"
            else "API 키는 OS 사용자 공간(Windows 레지스트리 / %APPDATA%)에만 안전하게 "
            "저장되며 배포판이나 소스 코드에 절대 포함되지 않습니다."
        )
        self.desc_label = QLabel(info_text)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #8B949E; font-size: 11px; line-height: 1.4;")
        layout.addWidget(self.desc_label)

        # Password masked input field with placeholder
        self.key_input = QLineEdit()
        self.key_input.setObjectName("ApiKeyInput")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("AIzaSy...")
        self.key_input.setText(self._current_key)
        self.key_input.setFixedHeight(30)
        self.key_input.setStyleSheet(
            "QLineEdit { background-color: #161B22; color: #F0F6FC; border: 1px solid #30363D; "
            "border-radius: 5px; padding: 4px 8px; font-size: 12px; } "
            "QLineEdit:focus { border: 1px solid #38BDF8; }"
        )
        self.key_input.setCursorPosition(0)
        layout.addWidget(self.key_input)

        # Action buttons row: Clear Key, Cancel, Save Key
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        clear_label = get_text("btn_clear_key", self._lang) or "Clear Key"
        self.clear_btn = QPushButton(clear_label)
        self.clear_btn.setObjectName("ClearKeyBtn")
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.setStyleSheet(
            "QPushButton { background-color: #3F1B24; color: #F87171; border: 1px solid #7F1D1D; "
            "border-radius: 4px; padding: 4px 12px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #7F1D1D; color: #FECACA; }"
        )
        self.clear_btn.clicked.connect(self._on_clear_clicked)

        cancel_label = get_text("btn_cancel", self._lang) or "Cancel"
        self.cancel_btn = QPushButton(cancel_label)
        self.cancel_btn.setObjectName("CancelKeyBtn")
        self.cancel_btn.setFixedHeight(28)
        self.cancel_btn.setStyleSheet(
            "QPushButton { background-color: #21262D; color: #C9D1D9; border: 1px solid #30363D; "
            "border-radius: 4px; padding: 4px 14px; font-size: 11px; } "
            "QPushButton:hover { background-color: #30363D; color: #F0F6FC; }"
        )
        self.cancel_btn.clicked.connect(self.reject)

        save_label = get_text("btn_apply_key", self._lang) or "Save Key"
        self.save_btn = QPushButton(save_label)
        self.save_btn.setObjectName("SaveKeyBtn")
        self.save_btn.setFixedHeight(28)
        self.save_btn.setStyleSheet(
            "QPushButton { background-color: #0284C7; color: #FFFFFF; border: none; "
            "border-radius: 4px; padding: 4px 16px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #0369A1; }"
        )
        self.save_btn.clicked.connect(self._on_save_clicked)

        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch(1)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def _on_save_clicked(self) -> None:
        key = self.key_input.text().strip()
        self._current_key = key
        self._config_manager.save_api_key(key)
        self.key_saved.emit(key)
        self.accept()

    def _on_clear_clicked(self) -> None:
        self._current_key = ""
        self.key_input.clear()
        self._config_manager.clear_api_key()
        self.key_cleared.emit()
        self.accept()
