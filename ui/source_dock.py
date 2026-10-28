"""Non-modal dockable Source Inspector (QDockWidget) for inspecting reference documents in split-screen."""

from __future__ import annotations

import html
from typing import Dict, List, Optional

from PyQt6.QtCore import QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextOption,
)
from PyQt6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.document_loader import SourceDocument
from core.i18n import get_text


class FigureInspectorDialog(QDialog):
    """High-resolution pan-and-zoom inspection dialog for extracted PDF figures and diagrams."""

    def __init__(self, figure_path: str, title: str = "Figure Inspector", lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.figure_path = figure_path
        self._lang = lang
        self.vision_requested: bool = False
        self.setWindowTitle(title)
        self.resize(880, 660)
        self._pixmap = QPixmap(figure_path)
        self._zoom = 1.0
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Toolbar
        bar = QHBoxLayout()
        self.info_label = QLabel(f"Dimensions: {self._pixmap.width()} x {self._pixmap.height()} px")
        self.info_label.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 600;")
        bar.addWidget(self.info_label)

        bar.addStretch(1)

        self.btn_zoom_in = QPushButton("Zoom In (+)")
        self.btn_zoom_in.setToolTip(get_text("tooltip_zoom_in", self._lang))
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        bar.addWidget(self.btn_zoom_in)

        self.btn_zoom_out = QPushButton("Zoom Out (-)")
        self.btn_zoom_out.setToolTip(get_text("tooltip_zoom_out", self._lang))
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        bar.addWidget(self.btn_zoom_out)

        self.btn_reset = QPushButton("Reset Zoom")
        self.btn_reset.setToolTip(get_text("reset_graph", self._lang))
        self.btn_reset.clicked.connect(self._reset_zoom)
        bar.addWidget(self.btn_reset)

        self.btn_open_external = QPushButton("Open External")
        self.btn_open_external.setToolTip(get_text("tooltip_open_url", self._lang))
        self.btn_open_external.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.figure_path)))
        bar.addWidget(self.btn_open_external)

        self.btn_vision = QPushButton(get_text("btn_vision_analyze", self._lang))
        self.btn_vision.setToolTip(get_text("tooltip_vision_analyze", self._lang))
        self.btn_vision.setStyleSheet("QPushButton { background-color: #0284C7; color: #FFFFFF; font-weight: 700; border-radius: 4px; padding: 4px 12px; font-size: 11px; } QPushButton:hover { background-color: #0369A1; }")
        self.btn_vision.clicked.connect(self._on_vision_analyze)
        bar.addWidget(self.btn_vision)

        layout.addLayout(bar)

        # Image Scroll Display
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #0B0F19; border: 1px solid #1E293B; border-radius: 6px; }")
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background-color: #0B0F19;")
        self.scroll_area.setWidget(self.img_label)
        layout.addWidget(self.scroll_area, stretch=1)

        self._update_display()

    def _on_vision_analyze(self) -> None:
        self.vision_requested = True
        self.accept()

    def _zoom_in(self) -> None:
        self._zoom = min(4.0, self._zoom + 0.25)
        self._update_display()

    def _zoom_out(self) -> None:
        self._zoom = max(0.25, self._zoom - 0.25)
        self._update_display()

    def _reset_zoom(self) -> None:
        self._zoom = 1.0
        self._update_display()

    def _update_display(self) -> None:
        if self._pixmap.isNull():
            self.img_label.setText("Failed to load figure image.")
            return
        target_w = int(self._pixmap.width() * self._zoom)
        target_h = int(self._pixmap.height() * self._zoom)
        scaled = self._pixmap.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.img_label.setPixmap(scaled)
        self.info_label.setText(f"Dimensions: {self._pixmap.width()} x {self._pixmap.height()} px | Zoom: {int(self._zoom * 100)}%")


class SourceInspectorDock(QDockWidget):
    """Split-screen non-modal dockable inspector showing document metadata, full extracted text, and keyword navigation."""

    MAX_HIGHLIGHTS = 2000
    analyze_figure_requested = pyqtSignal(str, str)

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SourceInspectorDock")
        self._lang = lang
        self._doc: Optional[SourceDocument] = None
        self._origin_url: str = ""

        self.setWindowTitle(get_text("source_inspector_title", self._lang))
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        self._build_ui()
        self.clear()

    @staticmethod
    def _resolve_origin_url(doc: SourceDocument) -> str:
        if doc.source_type != "web_sweep":
            return ""
        if doc.path_or_uri.lower().startswith(("http://", "https://")):
            return doc.path_or_uri
        links = doc.metadata.get("grounding_links")
        if isinstance(links, list):
            for link in links:
                if isinstance(link, dict) and str(link.get("uri", "")).lower().startswith(("http://", "https://")):
                    return str(link["uri"])
        return ""

    def _origin_type_label(self, doc: SourceDocument) -> str:
        title = doc.title.lstrip()
        if title.startswith("[WEB FULL-TEXT]"):
            key = "source_type_web_full_text"
        elif title.startswith("[WEB SNIPPET]"):
            key = "source_type_web_snippet"
        else:
            key = f"source_type_{doc.source_type}"
        label = get_text(key, self._lang)
        return doc.source_type if label == key else label

    def _build_ui(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header card (Title, Origin Badge, Word Count, Open URL)
        self.header_card = QFrame()
        self.header_card.setStyleSheet(
            "QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 6px; padding: 4px; }"
        )
        header_layout = QVBoxLayout(self.header_card)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(6)

        self.title_label = QLabel()
        self.title_label.setWordWrap(True)
        self.title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.title_label.setStyleSheet("color: #58A6FF; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        header_layout.addWidget(self.title_label)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)

        self.origin_badge = QLabel()
        self.origin_badge.setStyleSheet(
            "background-color: #1F2937; color: #38BDF8; font-size: 11px; font-weight: 600; "
            "padding: 2px 8px; border-radius: 4px; border: 1px solid #374151;"
        )
        meta_row.addWidget(self.origin_badge)

        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #94A3B8; font-size: 12px; border: none; background: transparent;")
        meta_row.addWidget(self.stats_label)

        meta_row.addStretch(1)

        self.open_url_btn = QPushButton(get_text("inspector_btn_open_url", self._lang))
        self.open_url_btn.setToolTip(get_text("tooltip_open_url", self._lang))
        self.open_url_btn.setStyleSheet(
            "background-color: #1E293B; color: #58A6FF; font-size: 11px; font-weight: 600; "
            "padding: 3px 10px; border: 1px solid #334155; border-radius: 4px;"
        )
        self.open_url_btn.clicked.connect(self._on_open_url)
        meta_row.addWidget(self.open_url_btn)

        header_layout.addLayout(meta_row)
        layout.addWidget(self.header_card)

        # Search Toolbar (Search input, Prev, Next, Matches counter)
        search_row = QHBoxLayout()
        search_row.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(get_text("inspector_search_placeholder", self._lang))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.search)
        self.search_input.returnPressed.connect(self.find_next)
        search_row.addWidget(self.search_input, stretch=1)

        self.prev_btn = QPushButton(get_text("inspector_btn_prev", self._lang))
        self.prev_btn.setToolTip(get_text("tooltip_source_prev", self._lang))
        self.prev_btn.setFixedWidth(50)
        self.prev_btn.clicked.connect(self.find_prev)
        search_row.addWidget(self.prev_btn)

        self.next_btn = QPushButton(get_text("inspector_btn_next", self._lang))
        self.next_btn.setToolTip(get_text("tooltip_source_next", self._lang))
        self.next_btn.setFixedWidth(50)
        self.next_btn.clicked.connect(self.find_next)
        search_row.addWidget(self.next_btn)

        self.match_label = QLabel("")
        self.match_label.setStyleSheet("color: #94A3B8; font-size: 12px; min-width: 70px;")
        search_row.addWidget(self.match_label)

        layout.addLayout(search_row)

        # Figures / Schematics Sub-panel (collapsible thumbnail carousel)
        self.figures_panel = QFrame()
        self.figures_panel.setStyleSheet(
            "QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 6px; padding: 4px; }"
        )
        figures_layout = QVBoxLayout(self.figures_panel)
        figures_layout.setContentsMargins(6, 6, 6, 6)
        figures_layout.setSpacing(4)

        self.figures_title = QLabel(get_text("figures_panel_title", self._lang))
        self.figures_title.setStyleSheet("color: #38BDF8; font-weight: 700; font-size: 11px;")
        figures_layout.addWidget(self.figures_title)

        self.figures_scroll = QScrollArea()
        self.figures_scroll.setFixedHeight(140)
        self.figures_scroll.setWidgetResizable(True)
        self.figures_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.figures_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.figures_scroll.setStyleSheet("background-color: #090D16; border: none;")

        self.figures_container = QWidget()
        self.figures_thumbnails_layout = QHBoxLayout(self.figures_container)
        self.figures_thumbnails_layout.setContentsMargins(4, 4, 4, 4)
        self.figures_thumbnails_layout.setSpacing(8)
        self.figures_scroll.setWidget(self.figures_container)
        figures_layout.addWidget(self.figures_scroll)
        self.figures_panel.hide()

        layout.addWidget(self.figures_panel)

        # Text Viewer
        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.text_view.setFont(QFont("Consolas", 10))
        self.text_view.setStyleSheet(
            "QPlainTextEdit { background-color: #0D1117; color: #C9D1D9; border: 1px solid #30363D; "
            "border-radius: 6px; padding: 8px; selection-background-color: #1F6FEB; line-height: 1.45; }"
        )
        layout.addWidget(self.text_view, stretch=1)

        self.setWidget(container)

    def _on_open_url(self) -> None:
        if self._origin_url:
            QDesktopServices.openUrl(QUrl(self._origin_url))

    def inspect_document(self, doc: SourceDocument, lang: str = "en", target_page: Optional[int] = None) -> None:
        """Load and display the given document in the inspector dock, optionally scrolling to a specific page."""
        self._doc = doc
        self._lang = lang
        self._origin_url = self._resolve_origin_url(doc)

        page_suffix = f" (p.{target_page})" if target_page else ""
        self.setWindowTitle(f"{get_text('source_inspector_title', self._lang)} — [{doc.cite_id}]{page_suffix}")
        self.title_label.setText(f"[{doc.cite_id}] {doc.title}{page_suffix}")

        origin_label = self._origin_type_label(doc)
        self.origin_badge.setText(origin_label)

        # Color-code origin badge
        if "full-text" in origin_label.lower() or "전문" in origin_label:
            self.origin_badge.setStyleSheet(
                "background-color: #064E3B; color: #34D399; font-size: 11px; font-weight: 600; "
                "padding: 2px 8px; border-radius: 4px; border: 1px solid #059669;"
            )
        elif "sweep" in origin_label.lower() or "탐색" in origin_label:
            self.origin_badge.setStyleSheet(
                "background-color: #581C87; color: #C084FC; font-size: 11px; font-weight: 600; "
                "padding: 2px 8px; border-radius: 4px; border: 1px solid #7E22CE;"
            )
        else:
            self.origin_badge.setStyleSheet(
                "background-color: #0C4A6E; color: #38BDF8; font-size: 11px; font-weight: 600; "
                "padding: 2px 8px; border-radius: 4px; border: 1px solid #0284C7;"
            )

        words_str = f"{doc.word_count:,} words" if lang == "en" else f"{doc.word_count:,} 단어"
        tokens_str = f"~{doc.estimated_tokens:,} tokens" if lang == "en" else f"약 {doc.estimated_tokens:,} 토큰"
        self.stats_label.setText(f"{words_str}  •  {tokens_str}")

        self.open_url_btn.setVisible(bool(self._origin_url))
        self.search_input.clear()
        self.match_label.setText("")

        # Populate Figure Schematics
        figures = doc.metadata.get("figures", []) if isinstance(doc.metadata.get("figures"), list) else []
        if target_page:
            figures = [f for f in figures if f.get("page_num") == target_page]

        while self.figures_thumbnails_layout.count() > 0:
            item = self.figures_thumbnails_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from pathlib import Path
        valid_figs = [f for f in figures if Path(f.get("path", "")).exists()]
        if valid_figs:
            for fig in valid_figs:
                fig_path = fig.get("path", "")
                fig_name = f"Figure p.{fig.get('page_num')}-{fig.get('index')}"

                card = QFrame()
                card.setStyleSheet("QFrame { background-color: #1E293B; border: 1px solid #334155; border-radius: 6px; padding: 2px; }")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(2, 2, 2, 2)
                card_layout.setSpacing(2)

                btn = QPushButton()
                btn.setFixedSize(110, 75)
                btn.setIcon(QIcon(fig_path))
                btn.setIconSize(QSize(100, 68))
                btn.setToolTip(f"{fig_name} ({fig.get('width')}x{fig.get('height')})\nClick to inspect in high-resolution")
                btn.setStyleSheet(
                    "QPushButton { background-color: #0F172A; border: none; border-radius: 4px; } "
                    "QPushButton:hover { background-color: #162032; }"
                )
                btn.clicked.connect(lambda _, fp=fig_path, fn=fig_name: self._open_figure_inspector(fp, fn))
                card_layout.addWidget(btn)

                btn_vision = QPushButton(get_text("btn_vision_analyze", self._lang))
                btn_vision.setToolTip(f"AI Vision Analysis for {fig_name}")
                btn_vision.setStyleSheet("QPushButton { background-color: #0284C7; color: #FFFFFF; font-size: 9px; font-weight: 700; border-radius: 3px; padding: 2px 4px; } QPushButton:hover { background-color: #0369A1; }")
                btn_vision.clicked.connect(lambda _, fp=fig_path, fn=fig_name: self.analyze_figure_requested.emit(fp, fn))
                card_layout.addWidget(btn_vision)

                self.figures_thumbnails_layout.addWidget(card)
            self.figures_thumbnails_layout.addStretch(1)
            self.figures_panel.show()
        else:
            self.figures_panel.hide()

        self.text_view.setPlainText(doc.content)
        self.text_view.moveCursor(QTextCursor.MoveOperation.Start)
        self.show()
        self.raise_()

        if target_page:
            self.navigate_to_page(target_page)

    def navigate_to_page(self, page_num: int) -> bool:
        """Jump to the `<!--PAGE_START:{page_num}-->` anchor, select the page heading, and highlight."""
        marker = f"<!--PAGE_START:{page_num}-->"
        document = self.text_view.document()
        cursor = document.find(marker)
        if not cursor.isNull():
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            self.text_view.setTextCursor(cursor)
            self.text_view.ensureCursorVisible()

            highlight = QTextCharFormat()
            highlight.setBackground(QColor("#1F6FEB"))
            highlight.setForeground(QColor("#FFFFFF"))
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = highlight
            self.text_view.setExtraSelections([selection])

            page_msg = f"Page {page_num}" if self._lang == "en" else f"{page_num}페이지"
            self.match_label.setText(page_msg)
            return True
        return False

    def _open_figure_inspector(self, path: str, title: str) -> None:
        dialog = FigureInspectorDialog(figure_path=path, title=title, lang=self._lang, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and getattr(dialog, "vision_requested", False):
            self.analyze_figure_requested.emit(path, title)

    def clear(self) -> None:
        """Reset inspector to empty placeholder state."""
        self._doc = None
        self._origin_url = ""
        self.setWindowTitle(get_text("source_inspector_title", self._lang))
        self.title_label.setText(get_text("inspector_empty_hint", self._lang))
        self.title_label.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500; border: none; background: transparent;")
        self.origin_badge.setText("—")
        self.origin_badge.setStyleSheet(
            "background-color: #1F2937; color: #94A3B8; font-size: 11px; font-weight: 600; "
            "padding: 2px 8px; border-radius: 4px; border: 1px solid #374151;"
        )
        self.stats_label.setText("")
        self.open_url_btn.setVisible(False)
        self.search_input.clear()
        self.match_label.setText("")
        if hasattr(self, "figures_panel"):
            self.figures_panel.hide()
        self.text_view.clear()

    def retranslate_ui(self, lang: str = "en") -> None:
        """Retranslate static labels and rebuild metadata strings."""
        self._lang = lang
        self.open_url_btn.setText(get_text("inspector_btn_open_url", lang))
        self.open_url_btn.setToolTip(get_text("tooltip_open_url", lang))
        self.prev_btn.setText(get_text("inspector_btn_prev", lang))
        self.prev_btn.setToolTip(get_text("tooltip_source_prev", lang))
        self.next_btn.setText(get_text("inspector_btn_next", lang))
        self.next_btn.setToolTip(get_text("tooltip_source_next", lang))
        self.search_input.setPlaceholderText(get_text("inspector_search_placeholder", lang))
        if hasattr(self, "figures_title"):
            self.figures_title.setText(get_text("figures_panel_title", lang))

        if self._doc is not None:
            self.setWindowTitle(f"{get_text('source_inspector_title', lang)} — [{self._doc.cite_id}]")
            self.origin_badge.setText(self._origin_type_label(self._doc))
            words_str = f"{self._doc.word_count:,} words" if lang == "en" else f"{self._doc.word_count:,} 단어"
            tokens_str = f"~{self._doc.estimated_tokens:,} tokens" if lang == "en" else f"약 {self._doc.estimated_tokens:,} 토큰"
            self.stats_label.setText(f"{words_str}  •  {tokens_str}")
            if self.search_input.text():
                self.search(self.search_input.text())
        else:
            self.clear()

    def search(self, term: str) -> int:
        """Highlight matches of `term`, jump to the first, and display count."""
        selections: List[QTextEdit.ExtraSelection] = []
        needle = term.strip()
        if not needle:
            self.text_view.setExtraSelections([])
            self.match_label.setText("")
            return 0

        highlight = QTextCharFormat()
        highlight.setBackground(QColor("#9E6A03"))
        highlight.setForeground(QColor("#FFFFFF"))

        document = self.text_view.document()
        cursor = QTextCursor(document)
        first_cursor: Optional[QTextCursor] = None

        while len(selections) < self.MAX_HIGHLIGHTS:
            cursor = document.find(needle, cursor)
            if cursor.isNull():
                break
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format = highlight
            selections.append(selection)
            if first_cursor is None:
                first_cursor = QTextCursor(cursor)

        self.text_view.setExtraSelections(selections)
        if first_cursor is not None:
            self.text_view.setTextCursor(first_cursor)
            self.text_view.ensureCursorVisible()
            self.match_label.setText(get_text("inspector_matches", self._lang).format(n=len(selections)))
        else:
            self.match_label.setText(get_text("inspector_no_match", self._lang))
        return len(selections)

    def find_next(self) -> None:
        """Advance to next match, wrapping to top when reaching end."""
        needle = self.search_input.text().strip()
        if not needle:
            return
        found = self.text_view.find(needle)
        if not found:
            cursor = self.text_view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.text_view.setTextCursor(cursor)
            self.text_view.find(needle)

    def find_prev(self) -> None:
        """Advance to previous match, wrapping to bottom when reaching start."""
        needle = self.search_input.text().strip()
        if not needle:
            return
        found = self.text_view.find(needle, QTextDocument.FindFlag.FindBackward)
        if not found:
            cursor = self.text_view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text_view.setTextCursor(cursor)
            self.text_view.find(needle, QTextDocument.FindFlag.FindBackward)
