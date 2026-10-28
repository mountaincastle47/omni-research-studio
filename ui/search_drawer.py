"""Global full-text search drawer and dock widget powered by SQLite FTS5 with BM25 ranking."""

from __future__ import annotations

import html
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import get_text
from core.search_index import CorpusSearchIndex, SearchResult


class SearchResultItemWidget(QWidget):
    """Custom rich-text display widget for an individual FTS5 search result item."""

    def __init__(self, result: SearchResult, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Header: Doc Title and Page badge
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        title_lbl = QLabel(f"[{result.doc_id}] {result.doc_title}")
        title_lbl.setStyleSheet("font-weight: 600; color: #58A6FF; font-size: 13px;")
        title_lbl.setWordWrap(True)
        header_layout.addWidget(title_lbl, stretch=1)

        page_badge = QLabel(f"p.{result.page_num}")
        page_badge.setStyleSheet(
            "background-color: #1E293B; color: #94A3B8; font-size: 11px; "
            "padding: 2px 6px; border-radius: 4px; font-weight: bold;"
        )
        header_layout.addWidget(page_badge)
        layout.addLayout(header_layout)

        # Snippet body with <mark> styling
        snippet_html = result.snippet.replace(
            "<mark>",
            '<span style="background-color: rgba(234, 179, 8, 0.35); color: #FDE047; font-weight: bold; padding: 1px 3px; border-radius: 2px;">',
        ).replace("</mark>", "</span>")

        snippet_lbl = QLabel(f'<span style="color: #CBD5E1; font-size: 12px; line-height: 1.4;">{snippet_html}</span>')
        snippet_lbl.setWordWrap(True)
        snippet_lbl.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(snippet_lbl)

        self.setStyleSheet(
            "SearchResultItemWidget:hover { background-color: #161B22; border-radius: 6px; }"
        )


class SearchDrawerWidget(QWidget):
    """Full-text search interface offering instant BM25 matching and source page navigation."""

    result_selected = pyqtSignal(int, int)  # (doc_id, page_num)

    def __init__(
        self,
        search_index: Optional[CorpusSearchIndex] = None,
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.search_index = search_index or CorpusSearchIndex()
        self._lang = lang
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Search Input and Action Bar
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(get_text("search_fts_placeholder", self._lang))
        self.search_input.setStyleSheet(
            "QLineEdit { background-color: #0F172A; color: #F1F5F9; border: 1px solid #334155; "
            "border-radius: 6px; padding: 7px 10px; font-size: 13px; } "
            "QLineEdit:focus { border: 1px solid #38BDF8; }"
        )
        self.search_input.returnPressed.connect(self.perform_search)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_row.addWidget(self.search_input, stretch=1)

        self.btn_search = QPushButton(get_text("action_search_fts", self._lang))
        self.btn_search.setToolTip(get_text("tooltip_search_fts", self._lang))
        self.btn_search.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #F1F5F9; border: 1px solid #334155; "
            "border-radius: 6px; padding: 7px 14px; font-weight: 600; font-size: 12px; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.btn_search.clicked.connect(self.perform_search)
        search_row.addWidget(self.btn_search)
        layout.addLayout(search_row)

        # Status count banner
        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        layout.addWidget(self.count_label)

        # Results List Widget
        self.results_list = QListWidget()
        self.results_list.setStyleSheet(
            "QListWidget { background-color: #0B0F19; border: 1px solid #1E293B; border-radius: 6px; outline: none; } "
            "QListWidget::item { border-bottom: 1px solid #1E293B; padding: 4px; } "
            "QListWidget::item:selected { background-color: #1E293B; } "
            "QListWidget::item:hover { background-color: #161B22; }"
        )
        self.results_list.itemClicked.connect(self._on_item_clicked)
        self.results_list.itemDoubleClicked.connect(self._on_item_clicked)
        layout.addWidget(self.results_list, stretch=1)

    def set_search_index(self, index: CorpusSearchIndex) -> None:
        """Update active search index reference."""
        self.search_index = index

    def update_language(self, lang: str) -> None:
        """Update localized UI strings."""
        self._lang = lang
        self.search_input.setPlaceholderText(get_text("search_fts_placeholder", self._lang))
        self.btn_search.setText(get_text("action_search_fts", self._lang))
        self.btn_search.setToolTip(get_text("tooltip_search_fts", self._lang))

    def _on_search_text_changed(self, text: str) -> None:
        if len(text.strip()) >= 2:
            self.perform_search()
        elif not text.strip():
            self.clear_results()

    def perform_search(self) -> None:
        """Execute BM25 search across indexed corpus and populate results."""
        query = self.search_input.text().strip()
        if not query:
            self.clear_results()
            return

        results = self.search_index.search_corpus(query, limit=30)
        self.results_list.clear()

        if not results:
            self.count_label.setText(get_text("find_no_matches", self._lang))
            return

        count_msg = f"{len(results)} matches" if self._lang == "en" else f"{len(results)}개 결과 일치"
        self.count_label.setText(count_msg)

        for res in results:
            item = QListWidgetItem(self.results_list)
            item_widget = SearchResultItemWidget(res)
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, (res.doc_id, res.page_num))
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, item_widget)

    def clear_results(self) -> None:
        """Clear query results and reset status label."""
        self.results_list.clear()
        self.count_label.setText("")

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and isinstance(data, (tuple, list)) and len(data) == 2:
            doc_id, page_num = data
            self.result_selected.emit(int(doc_id), int(page_num))

    def focus_search(self) -> None:
        """Give keyboard focus to search input."""
        self.search_input.setFocus()
        self.search_input.selectAll()


class SearchDockWidget(QDockWidget):
    """Dockable panel housing the full-text search drawer (Ctrl+Shift+F)."""

    result_selected = pyqtSignal(int, int)

    def __init__(
        self,
        search_index: Optional[CorpusSearchIndex] = None,
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SearchDockWidget")
        self._lang = lang
        self.setWindowTitle(get_text("action_search_fts", self._lang))
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        self.drawer = SearchDrawerWidget(search_index=search_index, lang=lang, parent=self)
        self.drawer.result_selected.connect(self.result_selected)
        self.setWidget(self.drawer)

    def set_search_index(self, index: CorpusSearchIndex) -> None:
        self.drawer.set_search_index(index)

    def update_language(self, lang: str) -> None:
        self._lang = lang
        self.setWindowTitle(get_text("action_search_fts", self._lang))
        self.drawer.update_language(lang)

    def focus_search(self) -> None:
        self.drawer.focus_search()

    @property
    def search_input(self) -> QLineEdit:
        return self.drawer.search_input

    def perform_search(self) -> None:
        self.drawer.perform_search()

    def _run_search(self) -> None:
        self.drawer.perform_search()
