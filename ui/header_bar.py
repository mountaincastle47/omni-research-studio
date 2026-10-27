"""Header bar widget for OmniResearch Studio with model selection, language combo, and API Key banner."""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QLayout,
)

from core.i18n import get_text
from ui.components import ApiKeyBanner
from ui.dialogs.api_key_dialog import ApiKeyDialog


class HeaderBar(QWidget):
    """Application header bar with task-aware language control."""

    language_changed = pyqtSignal(str)

    def __init__(self, current_language: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_language = current_language
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Title & Subtitle
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title_label = QLabel(get_text("app_title", self.current_language))
        self.title_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #F0F6FC;")
        self.subtitle_label = QLabel(get_text("app_subtitle", self.current_language))
        self.subtitle_label.setStyleSheet("font-size: 11px; color: #8B949E;")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        layout.addLayout(title_box)

        layout.addStretch(1)

        # API Key Banner
        self.api_banner = ApiKeyBanner(lang=self.current_language, parent=self)
        layout.addWidget(self.api_banner)

        # Language Selector
        self.language_label = QLabel(get_text("label_language", self.current_language))
        self.language_label.setStyleSheet("font-size: 11px; color: #8B949E;")
        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("한국어", "ko")
        self.language_combo.setCurrentIndex(1 if self.current_language == "ko" else 0)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

        layout.addWidget(self.language_label)
        layout.addWidget(self.language_combo)

    def set_task_running(self, is_running: bool) -> None:
        """Lock language selector during task execution to prevent mid-task deadlocks."""
        self.language_combo.setEnabled(not is_running)

    def _on_language_changed(self, index: int) -> None:
        lang_code = self.language_combo.itemData(index) or "en"
        self.current_language = str(lang_code)
        self.language_changed.emit(self.current_language)

    def retranslate_ui(self, lang: str) -> None:
        """Retranslate texts without modifying widget references or layouts."""
        self.current_language = lang
        self.title_label.setText(get_text("app_title", lang))
        self.subtitle_label.setText(get_text("app_subtitle", lang))
        self.language_label.setText(get_text("label_language", lang))
        self.api_banner.retranslate_ui(lang)
