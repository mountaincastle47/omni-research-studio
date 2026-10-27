"""Document panel action toolbar accommodating variable text lengths without button text clipping."""

from __future__ import annotations

from typing import Optional
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
)

from core.i18n import get_text


class DocumentToolbar(QWidget):
    """
    Toolbar for document corpus actions.
    Diff comparison button uses QSizePolicy.Policy.Minimum and horizontal padding
    to accommodate variable text lengths in all languages without clipping.
    """

    add_files_clicked = pyqtSignal()
    diff_compare_clicked = pyqtSignal()
    clear_all_clicked = pyqtSignal()

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.upload_btn = QPushButton(get_text("btn_add_files", self._lang))
        self.upload_btn.setObjectName("PrimaryActionBtn")
        self.upload_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.upload_btn.clicked.connect(self.add_files_clicked.emit)

        # Diff button without rigid fixedWidth, with flexible size policy and 10px horizontal padding
        self.btn_diff_compare = QPushButton(get_text("menu_diff_compare", self._lang))
        self.btn_diff_compare.setObjectName("DiffCompareBtn")
        self.btn_diff_compare.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.btn_diff_compare.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #38BDF8; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #0F172A; }"
        )
        self.btn_diff_compare.clicked.connect(self.diff_compare_clicked.emit)

        self.clear_corpus_btn = QPushButton(get_text("btn_clear_all", self._lang))
        self.clear_corpus_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.clear_corpus_btn.clicked.connect(self.clear_all_clicked.emit)

        layout.addWidget(self.upload_btn, stretch=1)
        layout.addWidget(self.btn_diff_compare)
        layout.addWidget(self.clear_corpus_btn)

    def retranslate_ui(self, lang: str) -> None:
        self._lang = lang
        self.upload_btn.setText(get_text("btn_add_files", lang))
        self.btn_diff_compare.setText(get_text("menu_diff_compare", lang))
        self.clear_corpus_btn.setText(get_text("btn_clear_all", lang))
