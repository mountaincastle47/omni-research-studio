"""Dynamic Multi-Tab Research Workspace: encapsulating reports, chat drawer, and per-tab state."""

from __future__ import annotations

import re
import uuid
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QTextCursor, QTextDocument, QTextOption
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import get_text
from core.markdown_utils import build_dark_html
from core.project_manager import WorkspaceTabState
from ui.chat_drawer import FollowUpChatDrawer
from ui.graph_viewer import CausalGraphWidget
from ui.graph_widget import KnowledgeGraphWidget
from ui.streaming_renderer import StreamingMarkdownViewer
from ui.timeline_widget import ChronologyTimelineWidget


def auto_tab_title(query_or_topic: str, max_words: int = 5) -> str:
    """Generate a clean 5-word tab title from a research query or topic."""
    cleaned = re.sub(r"[#*_`\[\]\(\)]", " ", query_or_topic).strip()
    words = cleaned.split()
    if not words:
        return "Research Workspace"
    selected = words[:max_words]
    title = " ".join(selected)
    if len(words) > max_words:
        title += "..."
    return title[:40]


class InPageFindBar(QWidget):
    """Floating/docked in-page search bar for QTextBrowser instances (Ctrl+F)."""

    closed = pyqtSignal()

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._target_browser: Optional[QTextBrowser] = None
        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.setStyleSheet(
            "InPageFindBar { background-color: #0F172A; border: 1px solid #334155; border-radius: 6px; margin: 2px; }"
        )

        self.input_find = QLineEdit(self)
        self.input_find.setPlaceholderText(get_text("find_in_page_placeholder", self._lang))
        self.input_find.setStyleSheet(
            "QLineEdit { background-color: #1E293B; color: #F1F5F9; border: 1px solid #475569; "
            "border-radius: 4px; padding: 4px 8px; font-size: 12px; } "
            "QLineEdit:focus { border: 1px solid #38BDF8; }"
        )
        self.input_find.returnPressed.connect(self.find_next)
        self.input_find.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.input_find, stretch=1)

        self.count_label = QLabel("", self)
        self.count_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(self.count_label)

        self.btn_prev = QToolButton(self)
        self.btn_prev.setText("▲")
        self.btn_prev.setToolTip(get_text("find_prev", self._lang))
        self.btn_prev.setStyleSheet(
            "QToolButton { background-color: #1E293B; color: #F1F5F9; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 8px; font-size: 11px; } "
            "QToolButton:hover { background-color: #334155; }"
        )
        self.btn_prev.clicked.connect(self.find_prev)
        layout.addWidget(self.btn_prev)

        self.btn_next = QToolButton(self)
        self.btn_next.setText("▼")
        self.btn_next.setToolTip(get_text("find_next", self._lang))
        self.btn_next.setStyleSheet(
            "QToolButton { background-color: #1E293B; color: #F1F5F9; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 8px; font-size: 11px; } "
            "QToolButton:hover { background-color: #334155; }"
        )
        self.btn_next.clicked.connect(self.find_next)
        layout.addWidget(self.btn_next)

        self.chk_case = QPushButton("Aa", self)
        self.chk_case.setCheckable(True)
        self.chk_case.setToolTip(get_text("find_case_sensitive", self._lang))
        self.chk_case.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #94A3B8; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: bold; } "
            "QPushButton:checked { background-color: #38BDF8; color: #0F172A; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.chk_case.toggled.connect(self._on_case_toggled)
        layout.addWidget(self.chk_case)

        self.btn_close = QToolButton(self)
        self.btn_close.setText("✕")
        self.btn_close.setStyleSheet(
            "QToolButton { background-color: transparent; color: #94A3B8; border: none; font-size: 12px; padding: 4px; } "
            "QToolButton:hover { color: #F1F5F9; }"
        )
        self.btn_close.clicked.connect(self.hide_bar)
        layout.addWidget(self.btn_close)

    def attach_browser(self, browser: QTextBrowser) -> None:
        self._target_browser = browser

    def show_bar(self, browser: Optional[QTextBrowser] = None) -> None:
        if browser is not None:
            self._target_browser = browser
        self.show()
        self.input_find.setFocus()
        self.input_find.selectAll()
        if self.input_find.text():
            self._update_matches_count()

    def hide_bar(self) -> None:
        self.hide()
        self.closed.emit()
        if self._target_browser:
            self._target_browser.setFocus()

    def _flags(self, backward: bool = False) -> QTextDocument.FindFlag:
        flags = QTextDocument.FindFlag(0)
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        if self.chk_case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        return flags

    def find_next(self) -> bool:
        if not self._target_browser or not self.input_find.text():
            return False
        text = self.input_find.text()
        found = self._target_browser.find(text, self._flags(backward=False))
        if not found:
            # Wrap around to start
            cursor = self._target_browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._target_browser.setTextCursor(cursor)
            found = self._target_browser.find(text, self._flags(backward=False))
        self._update_matches_count()
        return found

    def find_prev(self) -> bool:
        if not self._target_browser or not self.input_find.text():
            return False
        text = self.input_find.text()
        found = self._target_browser.find(text, self._flags(backward=True))
        if not found:
            # Wrap around to end
            cursor = self._target_browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._target_browser.setTextCursor(cursor)
            found = self._target_browser.find(text, self._flags(backward=True))
        self._update_matches_count()
        return found

    def _on_text_changed(self, text: str) -> None:
        if not text:
            self.count_label.setText("")
            return
        if self._target_browser:
            cursor = self._target_browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._target_browser.setTextCursor(cursor)
            self.find_next()
        self._update_matches_count()

    def _on_case_toggled(self, checked: bool) -> None:
        self.find_next()

    def _update_matches_count(self) -> None:
        if not self._target_browser or not self.input_find.text():
            self.count_label.setText("")
            return
        text = self.input_find.text()
        content = self._target_browser.toPlainText()
        if not self.chk_case.isChecked():
            content = content.lower()
            text = text.lower()
        count = content.count(text)
        if count == 0:
            self.count_label.setText(get_text("find_no_matches", self._lang))
            self.count_label.setStyleSheet("color: #EF4444; font-size: 11px;")
        else:
            self.count_label.setText(f"{count} matches" if self._lang == "en" else f"{count}개 일치")
            self.count_label.setStyleSheet("color: #94A3B8; font-size: 11px;")


class WorkspaceReportPane(QWidget):
    """Encapsulates synthesis report viewer, perspective reports, follow-up chat drawer, and per-tab data."""

    citation_clicked = pyqtSignal(QUrl)
    chat_citation_clicked = pyqtSignal(int)
    chat_question_submitted = pyqtSignal(str)
    chat_cleared = pyqtSignal()
    toggle_synthesis_requested = pyqtSignal()
    toggle_perspective_requested = pyqtSignal()
    entity_selected = pyqtSignal(str)

    def __init__(self, tab_id: Optional[str] = None, title: str = "Research Workspace", lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tab_id = tab_id or str(uuid.uuid4())[:8]
        self.title = title
        self.current_language = lang

        # State attributes
        self.topic: str = ""
        self.query: str = ""
        self.synthesis_original_text: str = ""
        self.synthesis_translated_text: str = ""
        self.synthesis_showing_translation: bool = False
        self.perspective_original_text: str = ""
        self.perspective_translated_text: str = ""
        self.perspective_showing_translation: bool = False
        self.audio_directive: str = ""
        self.audio_script: str = ""
        self.audio_title: str = ""
        self.audio_mp3_path: Optional[str] = None
        self.citations: list = []
        self.grounding_refs: list = []

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.inner_tabs = QTabWidget(self)

        # Tab 1: Grounded Synthesis Report + Follow-Up Chat Drawer
        synthesis_tab = QWidget()
        synth_layout = QVBoxLayout(synthesis_tab)
        synth_layout.setContentsMargins(6, 6, 6, 6)
        synth_layout.setSpacing(6)

        synth_toolbar = QHBoxLayout()
        self.synthesis_translation_status = QLabel("")
        self.synthesis_translation_status.setStyleSheet("color: #38BDF8; font-size: 12px; font-weight: 600;")
        self.synthesis_toggle_btn = QPushButton()
        self.synthesis_toggle_btn.setObjectName("ToggleViewBtn")
        self._update_toggle_btn_label(self.synthesis_toggle_btn, self.synthesis_showing_translation)
        self.synthesis_toggle_btn.clicked.connect(self._on_toggle_synthesis)

        synth_toolbar.addWidget(self.synthesis_translation_status)
        synth_toolbar.addStretch(1)
        synth_toolbar.addWidget(self.synthesis_toggle_btn)
        synth_layout.addLayout(synth_toolbar)

        self.synthesis_viewer = StreamingMarkdownViewer(parent=self)
        self.synthesis_viewer.citation_clicked.connect(self.citation_clicked)
        self.synthesis_viewer.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.synthesis_viewer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        synth_layout.addWidget(self.synthesis_viewer, stretch=1)

        self.chat_drawer = FollowUpChatDrawer(lang=self.current_language, parent=self)
        self.chat_drawer.citation_url_clicked.connect(self.citation_clicked)
        self.chat_drawer.citation_clicked.connect(self.chat_citation_clicked)
        self.chat_drawer.question_submitted.connect(self.chat_question_submitted)
        self.chat_drawer.clear_requested.connect(self.chat_cleared)
        synth_layout.addWidget(self.chat_drawer)

        # Tab 2: Perspective Reports
        perspective_tab = QWidget()
        persp_layout = QVBoxLayout(perspective_tab)
        persp_layout.setContentsMargins(6, 6, 6, 6)
        persp_layout.setSpacing(6)

        persp_toolbar = QHBoxLayout()
        self.perspective_translation_status = QLabel("")
        self.perspective_translation_status.setStyleSheet("color: #38BDF8; font-size: 12px; font-weight: 600;")
        self.perspective_toggle_btn = QPushButton()
        self.perspective_toggle_btn.setObjectName("ToggleViewBtn")
        self._update_toggle_btn_label(self.perspective_toggle_btn, self.perspective_showing_translation)
        self.perspective_toggle_btn.clicked.connect(self._on_toggle_perspective)

        persp_toolbar.addWidget(self.perspective_translation_status)
        persp_toolbar.addStretch(1)
        persp_toolbar.addWidget(self.perspective_toggle_btn)
        persp_layout.addLayout(persp_toolbar)

        self.sweep_report_viewer = QTextBrowser()
        self.sweep_report_viewer.setOpenExternalLinks(False)
        self.sweep_report_viewer.setOpenLinks(False)
        self.sweep_report_viewer.anchorClicked.connect(self.citation_clicked)
        self.sweep_report_viewer.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.sweep_report_viewer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        persp_layout.addWidget(self.sweep_report_viewer, stretch=1)

        # Tab 3: Causal Graph Viewer
        self.causal_graph_viewer = CausalGraphWidget(lang=self.current_language, parent=self)
        self.causal_graph_viewer.citation_clicked.connect(self.citation_clicked)
        self.causal_graph_viewer.node_selected.connect(self._on_graph_node_selected)

        # Tab 4: Chronology Timeline Viewer
        self.chronology_viewer = ChronologyTimelineWidget(lang=self.current_language, parent=self)
        self.chronology_viewer.citation_clicked.connect(self.citation_clicked)

        # Tab 5: Cross-Corpus Entity Knowledge Graph Viewer
        self.knowledge_graph_viewer = KnowledgeGraphWidget(lang=self.current_language, parent=self)
        self.knowledge_graph_viewer.entity_selected.connect(self.entity_selected)

        self.inner_tabs.addTab(synthesis_tab, get_text("tab_synthesis_report", self.current_language))
        self.inner_tabs.addTab(perspective_tab, get_text("tab_perspective_reports", self.current_language))
        self.inner_tabs.addTab(self.causal_graph_viewer, get_text("tab_causal_graph", self.current_language))
        self.inner_tabs.addTab(self.chronology_viewer, get_text("tab_chronology", self.current_language))
        self.inner_tabs.addTab(self.knowledge_graph_viewer, get_text("tab_knowledge_graph", self.current_language))
        self.inner_tabs.currentChanged.connect(self._on_inner_tab_changed)
        layout.addWidget(self.inner_tabs, stretch=1)

        self.find_bar = InPageFindBar(lang=self.current_language, parent=self)
        self.find_bar.attach_browser(self.synthesis_viewer)
        layout.addWidget(self.find_bar)

        self._render_initial_content()

    def _on_graph_node_selected(self, node_id: str, label: str) -> None:
        self.inner_tabs.setCurrentIndex(0)
        clean = re.sub(r"[#*_`\[\]\(\)]", "", label).strip()
        if clean and len(clean) >= 2 and clean.lower() not in ("end", "subgraph", "graph", "flowchart"):
            from PyQt6.QtGui import QTextDocument
            # Prioritize whole-word / exact boundary matching to avoid partial substring hits
            found = self.synthesis_viewer.find(clean, QTextDocument.FindFlag.FindWholeWords)
            if not found:
                self.synthesis_viewer.find(clean)

    def update_synthesis_views(
        self,
        markdown_text: str,
        precomputed_causal_layout: Optional[Dict[str, Any]] = None,
        precomputed_kg_layout: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update synthesis viewer, causal graph, and chronology views."""
        self.synthesis_original_text = markdown_text
        self.synthesis_viewer.setHtml(build_dark_html(markdown_text, interactive_citations=True))
        if precomputed_causal_layout and hasattr(self.causal_graph_viewer, "load_precomputed_layout"):
            self.causal_graph_viewer.load_precomputed_layout(precomputed_causal_layout)
        else:
            self.causal_graph_viewer.set_markdown_report(markdown_text)

        if precomputed_kg_layout and hasattr(self, "knowledge_graph_viewer") and hasattr(self.knowledge_graph_viewer, "load_precomputed_layout"):
            self.knowledge_graph_viewer.load_precomputed_layout(precomputed_kg_layout)

        self.chronology_viewer.set_markdown_report(markdown_text)

    def _on_inner_tab_changed(self, index: int) -> None:
        target = self.synthesis_viewer if index == 0 else self.sweep_report_viewer
        self.find_bar.attach_browser(target)
        if self.find_bar.isVisible():
            self.find_bar.show_bar(target)

    def open_find_bar(self) -> None:
        target = self.synthesis_viewer if self.inner_tabs.currentIndex() == 0 else self.sweep_report_viewer
        self.find_bar.show_bar(target)

    def _update_toggle_btn_label(self, btn: QPushButton, showing_translation: bool) -> None:
        if showing_translation:
            btn.setText(get_text("btn_view_original", self.current_language))
        else:
            btn.setText(get_text("btn_view_translation", self.current_language))

    def _render_initial_content(self) -> None:
        welcome_md = (
            "### OmniResearch Studio — Grounded Synthesis Workspace\n\n"
            "Upload reference documents (`.pdf`, `.txt`, `.md`), or run OmniSweep web discovery to synthesize "
            "authoritative reports with interactive citations."
        )
        self.synthesis_viewer.setHtml(build_dark_html(welcome_md, interactive_citations=True))
        self.sweep_report_viewer.setHtml(build_dark_html(f"*{get_text('web_uris_help', self.current_language)}*", interactive_citations=True))

    def _on_toggle_synthesis(self) -> None:
        self.toggle_synthesis_requested.emit()

    def _on_toggle_perspective(self) -> None:
        self.toggle_perspective_requested.emit()

    def retranslate_ui(self, lang: str) -> None:
        self.current_language = lang
        self.inner_tabs.setTabText(0, get_text("tab_synthesis_report", lang))
        self.inner_tabs.setTabText(1, get_text("tab_perspective_reports", lang))
        self.inner_tabs.setTabText(2, get_text("tab_causal_graph", lang))
        self.inner_tabs.setTabText(3, get_text("tab_chronology", lang))
        self.inner_tabs.setTabText(4, get_text("tab_knowledge_graph", lang))
        self._update_toggle_btn_label(self.synthesis_toggle_btn, self.synthesis_showing_translation)
        self._update_toggle_btn_label(self.perspective_toggle_btn, self.perspective_showing_translation)
        self.chat_drawer.retranslate_ui(lang)
        self.causal_graph_viewer.retranslate_ui(lang)
        self.chronology_viewer.retranslate_ui(lang)
        self.knowledge_graph_viewer.retranslate_ui(lang)

    def export_state(self) -> WorkspaceTabState:
        """Export state into WorkspaceTabState."""
        return WorkspaceTabState(
            tab_id=self.tab_id,
            title=self.title,
            topic=self.topic,
            query=self.query,
            synthesis_original=self.synthesis_original_text,
            synthesis_translated=self.synthesis_translated_text,
            synthesis_showing_translation=self.synthesis_showing_translation,
            perspective_original=self.perspective_original_text,
            perspective_translated=self.perspective_translated_text,
            perspective_showing_translation=self.perspective_showing_translation,
            audio_directive=self.audio_directive,
            audio_script_raw=self.audio_script,
            audio_title=self.audio_title,
            audio_mp3_path=self.audio_mp3_path,
            chat_history=self.chat_drawer.history(),
            citations=list(self.citations),
            grounding_refs=list(self.grounding_refs),
        )

    def import_state(self, state: WorkspaceTabState) -> None:
        """Import state from WorkspaceTabState."""
        self.tab_id = state.tab_id or self.tab_id
        self.title = state.title or self.title
        self.topic = state.topic
        self.query = state.query
        self.synthesis_original_text = state.synthesis_original
        self.synthesis_translated_text = state.synthesis_translated
        self.synthesis_showing_translation = state.synthesis_showing_translation
        self.perspective_original_text = state.perspective_original
        self.perspective_translated_text = state.perspective_translated
        self.perspective_showing_translation = state.perspective_showing_translation
        self.audio_directive = state.audio_directive
        self.audio_script = state.audio_script_raw
        self.audio_title = state.audio_title
        self.audio_mp3_path = state.audio_mp3_path
        self.citations = list(state.citations)
        self.grounding_refs = list(state.grounding_refs)

        # Restore viewers
        synth_text = self.synthesis_translated_text if self.synthesis_showing_translation and self.synthesis_translated_text else self.synthesis_original_text
        if synth_text:
            self.synthesis_viewer.setHtml(build_dark_html(synth_text, interactive_citations=True))
            self.update_synthesis_views(synth_text)
        persp_text = self.perspective_translated_text if self.perspective_showing_translation and self.perspective_translated_text else self.perspective_original_text
        if persp_text:
            self.sweep_report_viewer.setHtml(build_dark_html(persp_text, interactive_citations=True))

        self._update_toggle_btn_label(self.synthesis_toggle_btn, self.synthesis_showing_translation)
        self._update_toggle_btn_label(self.perspective_toggle_btn, self.perspective_showing_translation)

        # Restore chat history
        if state.chat_history:
            self.chat_drawer.load_history(state.chat_history)


class SplitComparisonWidget(QWidget):
    """Dual-pane split workspace comparison view (QSplitter) with proportional synchronized scrolling."""

    citation_clicked = pyqtSignal(QUrl)
    close_requested = pyqtSignal()

    def __init__(
        self,
        workspace_tabs: ResearchWorkspaceTabs,
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.workspace_tabs = workspace_tabs
        self._lang = lang
        self._syncing = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Top Control Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 2, 4, 4)
        toolbar.setSpacing(10)

        badge = QLabel("◫ " + get_text("menu_split_view", self._lang))
        badge.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 13px;")
        toolbar.addWidget(badge)

        toolbar.addStretch(1)

        compare_lbl = QLabel(get_text("split_pane_select", self._lang))
        compare_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        toolbar.addWidget(compare_lbl)

        self.secondary_combo = QComboBox()
        self.secondary_combo.setMinimumWidth(180)
        self.secondary_combo.currentIndexChanged.connect(self._on_secondary_selected)
        toolbar.addWidget(self.secondary_combo)

        self.sync_scroll_chk = QCheckBox(get_text("sync_scroll", self._lang))
        self.sync_scroll_chk.setChecked(True)
        self.sync_scroll_chk.setStyleSheet("color: #C9D1D9; font-size: 12px; font-weight: 500;")
        toolbar.addWidget(self.sync_scroll_chk)

        self.btn_close = QPushButton("✕")
        self.btn_close.setToolTip("Close Split Comparison View")
        self.btn_close.setStyleSheet("background: transparent; color: #94A3B8; border: none; font-size: 14px; padding: 2px 8px;")
        self.btn_close.clicked.connect(self.close_requested)
        toolbar.addWidget(self.btn_close)

        layout.addLayout(toolbar)

        # Dual-Pane QSplitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setStyleSheet(
            "QSplitter::handle { background-color: #30363D; width: 4px; border-radius: 2px; } "
            "QSplitter::handle:hover { background-color: #58A6FF; }"
        )

        # Left Primary Pane
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(4)
        self.left_title = QLabel("Primary Workspace")
        self.left_title.setStyleSheet("font-weight: 600; color: #58A6FF; font-size: 12px; padding: 2px 4px;")
        left_layout.addWidget(self.left_title)

        self.left_browser = QTextBrowser()
        self.left_browser.setOpenLinks(False)
        self.left_browser.setOpenExternalLinks(False)
        self.left_browser.anchorClicked.connect(self.citation_clicked)
        left_layout.addWidget(self.left_browser, stretch=1)
        self.splitter.addWidget(left_container)

        # Right Secondary Pane
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(4)
        self.right_title = QLabel("Comparison Workspace")
        self.right_title.setStyleSheet("font-weight: 600; color: #38BDF8; font-size: 12px; padding: 2px 4px;")
        right_layout.addWidget(self.right_title)

        self.right_browser = QTextBrowser()
        self.right_browser.setOpenLinks(False)
        self.right_browser.setOpenExternalLinks(False)
        self.right_browser.anchorClicked.connect(self.citation_clicked)
        right_layout.addWidget(self.right_browser, stretch=1)
        self.splitter.addWidget(right_container)

        self.splitter.setSizes([500, 500])
        layout.addWidget(self.splitter, stretch=1)

        # Synchronized Scrolling Handlers
        self.left_browser.verticalScrollBar().valueChanged.connect(self._sync_scroll_from_left)
        self.right_browser.verticalScrollBar().valueChanged.connect(self._sync_scroll_from_right)

    def _sync_scroll_from_left(self, val: int) -> None:
        if self._syncing or not self.sync_scroll_chk.isChecked():
            return
        self._syncing = True
        try:
            l_max = self.left_browser.verticalScrollBar().maximum()
            r_max = self.right_browser.verticalScrollBar().maximum()
            if l_max > 0 and r_max > 0:
                ratio = val / l_max
                self.right_browser.verticalScrollBar().setValue(int(ratio * r_max))
        finally:
            self._syncing = False

    def _sync_scroll_from_right(self, val: int) -> None:
        if self._syncing or not self.sync_scroll_chk.isChecked():
            return
        self._syncing = True
        try:
            l_max = self.left_browser.verticalScrollBar().maximum()
            r_max = self.right_browser.verticalScrollBar().maximum()
            if l_max > 0 and r_max > 0:
                ratio = val / r_max
                self.left_browser.verticalScrollBar().setValue(int(ratio * l_max))
        finally:
            self._syncing = False

    def refresh_panes(self, primary_pane: Optional[WorkspaceReportPane] = None) -> None:
        """Populate panes with primary and secondary tab contents."""
        all_panes = self.workspace_tabs.get_all_panes()
        if not all_panes:
            return

        primary = primary_pane or all_panes[0]
        self.left_title.setText(f"Left: {primary.title}")

        left_text = primary.synthesis_translated_text if primary.synthesis_showing_translation and primary.synthesis_translated_text else primary.synthesis_original_text
        if left_text:
            self.left_browser.setHtml(build_dark_html(left_text, interactive_citations=True))
        else:
            self.left_browser.setHtml(build_dark_html("*No synthesis generated in primary tab yet.*"))

        self.secondary_combo.blockSignals(True)
        self.secondary_combo.clear()
        candidates = [p for p in all_panes if p != primary]
        if not candidates:
            candidates = [primary]

        for p in candidates:
            self.secondary_combo.addItem(p.title, p)
        self.secondary_combo.blockSignals(False)

        self._on_secondary_selected(0)

    def _on_secondary_selected(self, index: int) -> None:
        sec_pane = self.secondary_combo.currentData()
        if not isinstance(sec_pane, WorkspaceReportPane):
            return

        self.right_title.setText(f"Right: {sec_pane.title}")
        right_text = sec_pane.synthesis_translated_text if sec_pane.synthesis_showing_translation and sec_pane.synthesis_translated_text else sec_pane.synthesis_original_text
        if right_text:
            self.right_browser.setHtml(build_dark_html(right_text, interactive_citations=True))
        else:
            self.right_browser.setHtml(build_dark_html("*No synthesis generated in comparison tab yet.*"))


class ResearchWorkspaceTabs(QTabWidget):
    """Dynamic multi-tab workspace widget with '+' corner button, rename dialog, and 1-tab minimum guard."""

    workspace_changed = pyqtSignal(int, WorkspaceReportPane)
    citation_clicked = pyqtSignal(QUrl)
    chat_citation_clicked = pyqtSignal(int)
    split_view_toggled = pyqtSignal(bool)
    entity_selected = pyqtSignal(str)

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_language = lang
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)

        # Split comparison state
        self._split_widget: Optional[SplitComparisonWidget] = None
        self._split_tab_idx: Optional[int] = None

        # Corner Container with Split View Toggle + New Tab Buttons
        corner_widget = QWidget(self)
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 4, 0)
        corner_layout.setSpacing(4)

        self.split_view_btn = QToolButton(corner_widget)
        self.split_view_btn.setText("◫ " + get_text("menu_split_view", self.current_language))
        self.split_view_btn.setCheckable(True)
        self.split_view_btn.setToolTip("비교 뷰 활성화 / Split Comparison View")
        self.split_view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.split_view_btn.setStyleSheet(
            "QToolButton { font-size: 12px; font-weight: bold; background: #21262d; color: #38bdf8; "
            "border: 1px solid #30363d; border-radius: 4px; padding: 2px 8px; margin: 2px 2px; } "
            "QToolButton:hover { background: #30363d; color: #7dd3fc; } "
            "QToolButton:checked { background: #0284c7; color: #ffffff; }"
        )
        self.split_view_btn.clicked.connect(self._on_split_btn_clicked)
        corner_layout.addWidget(self.split_view_btn)

        # Corner '+' toolbutton
        self.new_tab_btn = QToolButton(corner_widget)
        self.new_tab_btn.setText("+")
        self.new_tab_btn.setToolTip(get_text("tab_new", self.current_language))
        self.new_tab_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_tab_btn.setStyleSheet(
            "QToolButton { font-size: 16px; font-weight: bold; background: #21262d; color: #58a6ff; "
            "border: 1px solid #30363d; border-radius: 4px; padding: 2px 8px; margin: 2px 2px; } "
            "QToolButton:hover { background: #30363d; color: #79c0ff; }"
        )
        self.new_tab_btn.clicked.connect(lambda: self.add_new_workspace())
        corner_layout.addWidget(self.new_tab_btn)

        self.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

        # Signals
        self.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tabBarDoubleClicked.connect(self._on_tab_double_clicked)
        self.currentChanged.connect(self._on_current_changed)

        # Start with 1 default tab
        self.add_new_workspace(title="Research Workspace 1")

    def _on_split_btn_clicked(self) -> None:
        self.enable_split_view(self.split_view_btn.isChecked())

    def enable_split_view(self, enabled: bool = True) -> None:
        """Activate or deactivate dual-pane split workspace comparison view."""
        self.split_view_btn.blockSignals(True)
        self.split_view_btn.setChecked(enabled)
        self.split_view_btn.blockSignals(False)
        self.split_view_toggled.emit(enabled)
        if enabled:
            if self._split_widget is not None and self._split_tab_idx is not None:
                self.setCurrentIndex(self._split_tab_idx)
                self._split_widget.refresh_panes(self.current_workspace_pane())
                return

            primary_pane = self.current_workspace_pane()
            self._split_widget = SplitComparisonWidget(self, lang=self.current_language, parent=self)
            self._split_widget.citation_clicked.connect(self.citation_clicked)
            self._split_widget.close_requested.connect(lambda: self.enable_split_view(False))

            title = "◫ " + get_text("menu_split_view", self.current_language)
            self._split_tab_idx = self.addTab(self._split_widget, title)
            self.setCurrentIndex(self._split_tab_idx)
            self._split_widget.refresh_panes(primary_pane)
        else:
            if self._split_widget is not None:
                idx = self.indexOf(self._split_widget)
                if idx >= 0:
                    self.removeTab(idx)
                self._split_widget.deleteLater()
                self._split_widget = None
                self._split_tab_idx = None
            if self.count() > 0:
                self.setCurrentIndex(0)

    def add_new_workspace(self, title: Optional[str] = None, state: Optional[WorkspaceTabState] = None) -> WorkspaceReportPane:
        """Create and append a new research workspace tab."""
        tab_idx = self.count() + 1
        default_title = title or f"Research Workspace {tab_idx}"
        pane = WorkspaceReportPane(title=default_title, lang=self.current_language, parent=self)

        # Connect signals
        pane.citation_clicked.connect(self.citation_clicked)
        pane.chat_citation_clicked.connect(self.chat_citation_clicked)
        pane.entity_selected.connect(self.entity_selected)

        if state is not None:
            pane.import_state(state)
            default_title = state.title or default_title

        index = self.addTab(pane, default_title)
        self.setCurrentIndex(index)
        return pane

    def current_workspace_pane(self) -> WorkspaceReportPane:
        """Return the active WorkspaceReportPane."""
        widget = self.currentWidget()
        if isinstance(widget, WorkspaceReportPane):
            return widget
        # Fallback if no tab exists
        return self.add_new_workspace()

    def get_all_panes(self) -> List[WorkspaceReportPane]:
        """Return all WorkspaceReportPanes in order."""
        panes: List[WorkspaceReportPane] = []
        for i in range(self.count()):
            widget = self.widget(i)
            if isinstance(widget, WorkspaceReportPane):
                panes.append(widget)
        return panes

    def auto_name_active_tab(self, query_or_topic: str) -> None:
        """Auto-name current tab based on the query or synthesis topic."""
        cur_pane = self.current_workspace_pane()
        # Only auto-rename if title looks like a generic name
        if "Research Workspace" in cur_pane.title or not cur_pane.title:
            new_title = auto_tab_title(query_or_topic)
            if new_title:
                cur_pane.title = new_title
                cur_idx = self.currentIndex()
                if cur_idx >= 0:
                    self.setTabText(cur_idx, new_title)

    def _on_tab_close_requested(self, index: int) -> None:
        """Handle tab close request respecting the 1-tab minimum guard."""
        if self._split_widget is not None and self.widget(index) == self._split_widget:
            self.enable_split_view(False)
            return

        if self.count() <= 1:
            # 1-tab guard: Do not delete, but reset pane to clean state
            pane = self.current_workspace_pane()
            pane.topic = ""
            pane.query = ""
            pane.synthesis_original_text = ""
            pane.synthesis_translated_text = ""
            pane.synthesis_showing_translation = False
            pane.perspective_original_text = ""
            pane.perspective_translated_text = ""
            pane.perspective_showing_translation = False
            pane.audio_directive = ""
            pane.audio_script = ""
            pane.chat_drawer.clear_chat(emit_signal=False)
            pane._render_initial_content()
            self.setTabText(0, "Research Workspace 1")
            pane.title = "Research Workspace 1"
            return

        # More than 1 tab: close it
        pane = self.widget(index)
        self.removeTab(index)
        if pane is not None:
            pane.deleteLater()

    def _on_tab_double_clicked(self, index: int) -> None:
        """Allow inline double-click renaming of research tabs."""
        if index < 0 or index >= self.count():
            return
        pane = self.widget(index)
        if not isinstance(pane, WorkspaceReportPane):
            return

        current_title = self.tabText(index)
        new_title, ok = QInputDialog.getText(
            self,
            get_text("tab_rename_title", self.current_language),
            get_text("tab_rename_prompt", self.current_language),
            text=current_title,
        )
        if ok and new_title.strip():
            clean_title = new_title.strip()[:40]
            self.setTabText(index, clean_title)
            pane.title = clean_title

    def _on_current_changed(self, index: int) -> None:
        widget = self.widget(index)
        if isinstance(widget, WorkspaceReportPane):
            self.workspace_changed.emit(index, widget)

    def retranslate_ui(self, lang: str) -> None:
        self.current_language = lang
        self.new_tab_btn.setToolTip(get_text("tab_new", lang))
        if hasattr(self, "split_view_btn"):
            self.split_view_btn.setText("◫ " + get_text("menu_split_view", lang))
        for pane in self.get_all_panes():
            pane.retranslate_ui(lang)
