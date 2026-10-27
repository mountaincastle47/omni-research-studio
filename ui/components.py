"""Custom PyQt6 widgets: source management, citation inspection, source inspector dialog, dialogue rendering, audio player."""

from __future__ import annotations

import html
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QTextCharFormat, QTextCursor, QTextDocument, QTextOption
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.audio_studio import DialogueTurn, PodcastScript
from core.citation_audit import CitationAudit
from core.document_loader import SourceDocument
from core.i18n import get_text
from core.notebook_synthesis import CitationMatch
from core.storm_discovery import GroundingReference
from core.token_ledger import GLOBAL_LEDGER, TokenLedger


def escape_mnemonic(text: str) -> str:
    """Double ampersands so Qt widgets do not interpret '&' as an underline mnemonic accelerator."""
    return text.replace("&", "&&")


PERSONA_I18N_KEY_MAP: Dict[str, str] = {
    "systems_architect": "persona_technical",
    "empirical_skeptic": "persona_skeptic",
    "domain_strategist": "persona_economic",
    "historical_comparativist": "persona_historical",
}


class ApiKeyBanner(QFrame):
    """Compact inline API Key widget: [● Active Key: ...xxxx] [Change] with expandable inline editor and clear credentials action."""

    api_key_Saved = pyqtSignal(str)
    api_key_Cleared = pyqtSignal()

    def __init__(self, initial_key: str = "", lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ApiKeyBanner")
        self._current_key = initial_key.strip()
        self._lang = lang
        self._editing = not bool(self._current_key)
        self._build_ui()

    def _build_ui(self) -> None:
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        self.badge_label = QLabel()
        self.badge_label.setStyleSheet("font-size: 12px; font-weight: 600; border: none; background: transparent;")

        self.change_btn = QPushButton(get_text("btn_change_key", self._lang))
        self.change_btn.setFixedHeight(24)
        self.change_btn.setFixedWidth(68)
        self.change_btn.setStyleSheet(
            "QPushButton { padding: 2px 8px; font-size: 11px; background-color: #1E293B; border: 1px solid #334155; border-radius: 4px; }"
            "QPushButton:hover { background-color: #334155; }"
        )
        self.change_btn.clicked.connect(self._on_start_editing)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("GEMINI_API_KEY...")
        self.key_input.setText(self._current_key)
        self.key_input.setMinimumWidth(220)
        self.key_input.setFixedHeight(26)
        self.key_input.returnPressed.connect(self._on_save_clicked)

        self.save_btn = QPushButton(get_text("btn_apply_key", self._lang))
        self.save_btn.setObjectName("PrimaryActionBtn")
        self.save_btn.setFixedHeight(26)
        self.save_btn.setMinimumWidth(96)
        self.save_btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        self.save_btn.clicked.connect(self._on_save_clicked)

        self.clear_btn = QPushButton(get_text("btn_clear_key", self._lang))
        self.clear_btn.setObjectName("ClearKeyBtn")
        self.clear_btn.setFixedHeight(26)
        self.clear_btn.setMinimumWidth(110)
        self.clear_btn.setStyleSheet(
            "QPushButton { padding: 2px 8px; font-size: 11px; background-color: #3F1B24; color: #F87171; "
            "border: 1px solid #7F1D1D; border-radius: 4px; font-weight: 600; } "
            "QPushButton:hover { background-color: #7F1D1D; color: #FECACA; }"
        )
        self.clear_btn.clicked.connect(self._on_clear_clicked)

        layout.addWidget(self.badge_label)
        layout.addWidget(self.change_btn)
        layout.addWidget(self.key_input)
        layout.addWidget(self.save_btn)
        layout.addWidget(self.clear_btn)

        self._sync_mode()

    def _mask_key(self, key: str) -> str:
        cleaned = key.strip()
        if not cleaned:
            return "None"
        tail = cleaned[-4:] if len(cleaned) >= 4 else cleaned
        return f"...{tail}"

    def _on_start_editing(self) -> None:
        self._editing = True
        self._sync_mode()
        self.key_input.setFocus()
        self.key_input.selectAll()

    def _on_save_clicked(self) -> None:
        self._current_key = self.key_input.text().strip()
        self._editing = False
        self._sync_mode()
        self.api_key_Saved.emit(self._current_key)

    def _on_clear_clicked(self) -> None:
        self._current_key = ""
        self.key_input.clear()
        self._editing = False
        self._sync_mode()
        self.api_key_Cleared.emit()
        self.api_key_Saved.emit("")

    def update_state(self, has_key: bool) -> None:
        if not has_key:
            self._current_key = ""
            self.key_input.clear()
        self._sync_mode()

    def retranslate_ui(self, lang: str = "en") -> None:
        """Update localized strings in the API key banner."""
        self._lang = lang
        self.change_btn.setText(get_text("btn_change_key", self._lang))
        self.save_btn.setText(get_text("btn_apply_key", self._lang))
        self.clear_btn.setText(get_text("btn_clear_key", self._lang))
        self._sync_mode()

    def _sync_mode(self) -> None:
        has_key = bool(self._current_key)
        if has_key:
            active_label = get_text("api_key_active", self._lang)
            self.badge_label.setText(f"● {active_label}: {self._mask_key(self._current_key)}")
            self.badge_label.setStyleSheet(
                "color: #10B981; font-size: 12px; font-weight: 600; border: none; background: transparent;"
            )
            self.setStyleSheet(
                "#ApiKeyBanner { background-color: #0D1F17; border: 1px solid #10B981; border-radius: 6px; }"
            )
        else:
            none_label = get_text("api_key_none", self._lang)
            self.badge_label.setText(f"● {none_label}")
            self.badge_label.setStyleSheet(
                "color: #e74c3c; font-size: 12px; font-weight: 600; border: none; background: transparent;"
            )
            self.setStyleSheet(
                "#ApiKeyBanner { background-color: #2A1217; border: 1px solid #e74c3c; border-radius: 6px; }"
            )

        self.change_btn.setVisible(not self._editing)
        self.key_input.setVisible(self._editing)
        self.save_btn.setVisible(self._editing)
        self.clear_btn.setVisible(self._editing)


class SourceListWidget(QWidget):
    """Interactive list of indexed local files and OmniSweep web discovery sources."""

    source_Selected = pyqtSignal(int)  # cite_id
    source_Toggled = pyqtSignal(int, bool)  # cite_id, enabled
    source_Removed = pyqtSignal(int)  # cite_id
    source_DoubleClicked = pyqtSignal(int)  # cite_id -> opens the Source Document Inspector

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(False)
        self.list_widget.setWordWrap(True)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.itemChanged.connect(self._on_item_changed)

        btn_row = QHBoxLayout()
        self.select_all_btn = QPushButton(get_text("btn_enable_all", self._lang))
        self.deselect_all_btn = QPushButton(get_text("btn_disable_all", self._lang))
        self.remove_btn = QPushButton(get_text("btn_remove_selected", self._lang))

        self.select_all_btn.clicked.connect(lambda: self._set_all_check_state(True))
        self.deselect_all_btn.clicked.connect(lambda: self._set_all_check_state(False))
        self.remove_btn.clicked.connect(self._on_remove_selected)

        btn_row.addWidget(self.select_all_btn)
        btn_row.addWidget(self.deselect_all_btn)
        btn_row.addWidget(self.remove_btn)

        layout.addWidget(self.list_widget, stretch=1)
        layout.addLayout(btn_row)

    def retranslate_ui(self, lang: str = "en") -> None:
        """Update button labels for the active language."""
        self._lang = lang
        self.select_all_btn.setText(get_text("btn_enable_all", self._lang))
        self.deselect_all_btn.setText(get_text("btn_disable_all", self._lang))
        self.remove_btn.setText(get_text("btn_remove_selected", self._lang))

    def refresh_sources(self, documents: List[SourceDocument]) -> None:
        """Rebuild the visual list from the current DocumentCorpus."""
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        badge_map = {
            "local_pdf": "PDF",
            "local_txt": "TXT",
            "local_md": "MD",
            "web_sweep": "WEB SWEEP",
        }

        for doc in documents:
            badge = badge_map.get(doc.source_type, "DOC")
            title_has_tag = doc.title.lstrip().startswith("[WEB ")
            badge_part = "" if title_has_tag else f"[{badge}] "
            label = f"[{doc.cite_id}] {badge_part}{doc.title} ({doc.word_count:,} words)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, doc.cite_id)
            item.setToolTip(f"{doc.path_or_uri}\n\nPreview:\n{doc.summary_snippet}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            item.setCheckState(Qt.CheckState.Checked if doc.enabled else Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

        self.list_widget.blockSignals(False)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        cite_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(cite_id, int):
            self.source_Selected.emit(cite_id)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        cite_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(cite_id, int):
            self.source_DoubleClicked.emit(cite_id)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        cite_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(cite_id, int):
            enabled = item.checkState() == Qt.CheckState.Checked
            self.source_Toggled.emit(cite_id, enabled)

    def _set_all_check_state(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            if item is not None:
                item.setCheckState(state)

    def _on_remove_selected(self) -> None:
        current = self.list_widget.currentItem()
        if current is not None:
            cite_id = current.data(Qt.ItemDataRole.UserRole)
            if isinstance(cite_id, int):
                self.source_Removed.emit(cite_id)


class PerspectiveSelectorWidget(QWidget):
    """Checkable list of expert OmniSweep research perspectives with mnemonic-safe localized labels."""

    def __init__(
        self,
        perspectives: List[Dict[str, str]],
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._perspectives = perspectives
        self._lang = lang
        self._checkboxes: List[tuple[QCheckBox, Dict[str, str]]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        for persona in self._perspectives:
            i18n_key = PERSONA_I18N_KEY_MAP.get(persona.get("id", ""), "")
            display_name = get_text(i18n_key, self._lang) if i18n_key else persona["name"]
            cb = QCheckBox(escape_mnemonic(display_name))
            cb.setChecked(True)
            cb.setToolTip(persona["role"])
            layout.addWidget(cb)
            self._checkboxes.append((cb, persona))

    def retranslate_ui(self, lang: str = "en") -> None:
        """Retranslate perspective checkbox labels without losing checked states."""
        self._lang = lang
        for cb, persona in self._checkboxes:
            i18n_key = PERSONA_I18N_KEY_MAP.get(persona.get("id", ""), "")
            display_name = get_text(i18n_key, self._lang) if i18n_key else persona["name"]
            cb.setText(escape_mnemonic(display_name))

    def get_selected_perspectives(self) -> List[Dict[str, str]]:
        """Return all currently checked expert perspective definitions."""
        return [persona for cb, persona in self._checkboxes if cb.isChecked()]


class GroundingSourceCard(QFrame):
    """Structured card widget for a retrieved Google Search grounding URI or verified synthesis citation."""

    HIGHLIGHT_BORDER = "#388bfd"
    HIGHLIGHT_BACKGROUND = "rgba(31, 111, 235, 51)"  # #1f6feb at 0x33 alpha (Qt stylesheets use rgba(), not #RRGGBBAA)

    def __init__(
        self,
        header_title: str,
        uri: str,
        perspective_badge: str,
        snippet: str,
        accent_color: str = "#A855F7",
        parent: Optional[QWidget] = None,
        cite_id: Optional[int] = None,
    ) -> None:
        super().__init__(parent)
        self._uri = uri
        self.cite_id = cite_id
        self._accent_color = accent_color
        self._build_ui(header_title, uri, perspective_badge, snippet, accent_color)

    def _base_style(self) -> str:
        return (
            f"QFrame {{ background-color: #0F172A; border: 1px solid #1E293B; "
            f"border-left: 4px solid {self._accent_color}; border-radius: 6px; }}"
        )

    def set_highlight(self, active: bool) -> None:
        """Toggle the flash highlight used when a citation anchor navigates to this card."""
        if active:
            self.setStyleSheet(
                f"QFrame {{ background-color: {self.HIGHLIGHT_BACKGROUND}; border: 2px solid {self.HIGHLIGHT_BORDER}; "
                f"border-left: 4px solid {self.HIGHLIGHT_BORDER}; border-radius: 6px; }}"
            )
        else:
            self.setStyleSheet(self._base_style())

    @property
    def is_highlighted(self) -> bool:
        return self.HIGHLIGHT_BORDER in self.styleSheet()

    def _build_ui(
        self,
        header_title: str,
        uri: str,
        perspective_badge: str,
        snippet: str,
        accent_color: str,
    ) -> None:
        self.setStyleSheet(self._base_style())
        vlayout = QVBoxLayout(self)
        vlayout.setContentsMargins(10, 8, 10, 8)
        vlayout.setSpacing(4)

        domain = ""
        if uri.startswith("http"):
            parsed = urlparse(uri)
            domain = parsed.netloc or uri

        display_header = header_title.strip() or domain or uri
        if domain and domain.lower() not in display_header.lower():
            display_header = f"{display_header} ({domain})"

        header_lbl = QLabel()
        header_lbl.setWordWrap(True)
        header_lbl.setStyleSheet("border: none; background: transparent;")
        if uri.startswith("http"):
            escaped_uri = html.escape(uri)
            escaped_title = html.escape(display_header)
            header_lbl.setText(
                f"<a style='color:#58A6FF; font-weight:700; font-size:13px; text-decoration:none;' "
                f"href='{escaped_uri}'>{escaped_title} ↗</a>"
            )
            header_lbl.setOpenExternalLinks(True)
        else:
            header_lbl.setText(display_header)
            header_lbl.setStyleSheet(
                "color: #58A6FF; font-weight: 700; font-size: 13px; border: none; background: transparent;"
            )

        sub_lbl = QLabel(escape_mnemonic(f"[{perspective_badge}]"))
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet(
            f"color: {accent_color}; font-size: 11px; font-weight: 600; border: none; background: transparent;"
        )

        bounded_snippet = self._bound_two_lines(snippet)
        snippet_lbl = QLabel(bounded_snippet)
        snippet_lbl.setWordWrap(True)
        snippet_lbl.setMaximumHeight(42)
        snippet_lbl.setStyleSheet(
            "color: #C9D1D9; font-size: 12px; line-height: 1.35; border: none; background: transparent;"
        )

        vlayout.addWidget(header_lbl)
        vlayout.addWidget(sub_lbl)
        vlayout.addWidget(snippet_lbl)

    @staticmethod
    def _bound_two_lines(text: str, max_chars: int = 165) -> str:
        cleaned = " ".join(text.split()).strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max_chars - 3].rstrip() + "..."


class CitationInspectorWidget(QWidget):
    """Structured card-based inspector for verified synthesis citations and Google Search grounding URIs."""

    FLASH_DURATION_MS = 1200
    SCROLL_DURATION_MS = 380

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._last_citations: List[CitationMatch] = []
        self._last_web_refs: List[GroundingReference] = []
        self._showing_cards: bool = False
        self._audit: Optional[CitationAudit] = None
        self._cards_by_cite_id: Dict[int, GroundingSourceCard] = {}
        self._scroll_animation: Optional[QPropertyAnimation] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.audit_chip = QLabel("")
        self.audit_chip.setWordWrap(True)
        self.audit_chip.setVisible(False)
        layout.addWidget(self.audit_chip)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setContentsMargins(8, 8, 8, 8)
        self.cards_layout.setSpacing(8)

        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area, stretch=1)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.browser.anchorClicked.connect(self._on_anchor_clicked)
        self.browser.setVisible(False)
        layout.addWidget(self.browser, stretch=1)

        self.show_empty_state()

    def _clear_cards(self) -> None:
        self._cards_by_cite_id.clear()
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_audit(self, audit: Optional[CitationAudit]) -> None:
        """Show the Groundedness verification chip at the top of the inspector (hidden when nothing to audit)."""
        self._audit = audit
        self._refresh_audit_chip()

    def _refresh_audit_chip(self) -> None:
        audit = self._audit
        if audit is None:
            self.audit_chip.setVisible(False)
            return
        if not audit.has_citations:
            self.audit_chip.setText(get_text("citation_audit_none", self._lang))
            self.audit_chip.setStyleSheet(
                "color: #94A3B8; background-color: #0F172A; border: 1px solid #334155; "
                "border-radius: 10px; padding: 5px 10px; font-size: 12px; font-weight: 600;"
            )
            self.audit_chip.setVisible(True)
            return

        invalid = audit.total_citations - audit.valid_citations
        key = "citation_audit_pass" if invalid == 0 else "citation_audit_warn"
        self.audit_chip.setText(
            get_text(key, self._lang).format(
                score=audit.score,
                valid=audit.valid_citations,
                total=audit.total_citations,
                invalid=invalid,
            )
        )
        if invalid == 0:
            style = "color: #3FB950; background-color: rgba(46, 160, 67, 38); border: 1px solid #238636;"
        elif audit.score >= 60:
            style = "color: #D29922; background-color: rgba(187, 128, 9, 38); border: 1px solid #9E6A03;"
        else:
            style = "color: #F85149; background-color: rgba(248, 81, 73, 38); border: 1px solid #DA3633;"
        self.audit_chip.setStyleSheet(
            f"{style} border-radius: 10px; padding: 5px 10px; font-size: 12px; font-weight: 700;"
        )
        self.audit_chip.setVisible(True)

    def focus_citation(self, cite_id: int) -> bool:
        """Scroll smoothly to center citation card `[cite_id]` and flash-highlight it for 1.2s."""
        if not self._showing_cards:
            if not self._last_citations:
                return False
            self.update_grounding_and_citations(self._last_citations, self._last_web_refs)
            self.container.layout().activate()

        card = self._cards_by_cite_id.get(cite_id)
        if card is None:
            return False

        self.scroll_area.setVisible(True)
        self.browser.setVisible(False)
        self.container.layout().activate()
        bar = self.scroll_area.verticalScrollBar()
        viewport_height = self.scroll_area.viewport().height()
        target = card.y() + card.height() // 2 - viewport_height // 2
        target = max(bar.minimum(), min(bar.maximum(), target))

        if self._scroll_animation is not None:
            self._scroll_animation.stop()
        animation = QPropertyAnimation(bar, b"value", self)
        animation.setDuration(self.SCROLL_DURATION_MS)
        animation.setStartValue(bar.value())
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.start()
        self._scroll_animation = animation

        card.set_highlight(True)

        def _clear_flash(widget: GroundingSourceCard = card) -> None:
            try:
                widget.set_highlight(False)
            except RuntimeError:
                pass  # card was rebuilt/deleted before the flash ended

        QTimer.singleShot(self.FLASH_DURATION_MS, _clear_flash)
        return True

    def retranslate_ui(self, lang: str = "en") -> None:
        """Refresh empty state or active cards using the current language."""
        self._lang = lang
        self._refresh_audit_chip()
        if self._showing_cards:
            self.update_grounding_and_citations(self._last_citations, self._last_web_refs)
        elif not self.browser.isVisible():
            self.show_empty_state()

    def show_empty_state(self) -> None:
        self._showing_cards = False
        self.browser.setVisible(False)
        self.scroll_area.setVisible(True)
        self._clear_cards()

        cite_header = QLabel(get_text("header_citations_inspector", self._lang))
        cite_header.setStyleSheet("color: #58A6FF; font-size: 14px; font-weight: 700;")

        no_cite_lbl = QLabel(get_text("no_citations_yet", self._lang))
        no_cite_lbl.setWordWrap(True)
        no_cite_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; padding-bottom: 6px;")

        web_header = QLabel(get_text("header_web_uris", self._lang))
        web_header.setStyleSheet("color: #79C0FF; font-size: 14px; font-weight: 700; padding-top: 6px;")

        web_help_lbl = QLabel(get_text("web_uris_help", self._lang))
        web_help_lbl.setWordWrap(True)
        web_help_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.5;")

        self.cards_layout.addWidget(cite_header)
        self.cards_layout.addWidget(no_cite_lbl)
        self.cards_layout.addWidget(web_header)
        self.cards_layout.addWidget(web_help_lbl)
        self.cards_layout.addStretch(1)

    def inspect_document(self, doc: SourceDocument) -> None:
        """Display the full metadata and content preview of a selected source document."""
        self._showing_cards = False
        self.scroll_area.setVisible(False)
        self.browser.setVisible(True)

        escaped_title = html.escape(doc.title)
        escaped_uri = html.escape(doc.path_or_uri)
        escaped_content = html.escape(doc.content[:4000])
        if len(doc.content) > 4000:
            escaped_content += "\n\n... [Content truncated in preview]"

        links_html = ""
        grounding_links = doc.metadata.get("grounding_links")
        if isinstance(grounding_links, list) and grounding_links:
            items = []
            for item in grounding_links:
                if isinstance(item, dict) and item.get("uri"):
                    u = html.escape(str(item.get("uri")))
                    t = html.escape(str(item.get("title") or u))
                    items.append(f"<li><a style='color:#58A6FF;' href='{u}'>{t}</a></li>")
            if items:
                links_html = f"<h4>{html.escape(get_text('header_web_uris', self._lang))}</h4><ul>{''.join(items)}</ul>"

        uri_html = (
            f"<a style='color:#58A6FF;' href='{escaped_uri}'>{escaped_uri}</a>"
            if doc.path_or_uri.startswith("http")
            else f"<code>{escaped_uri}</code>"
        )

        self.browser.setHtml(
            f"<div style='font-family:Segoe UI, sans-serif; color:#C9D1D9; font-size:13px; line-height:1.5;'>"
            f"<h3 style='color:#58A6FF; margin-bottom:4px;'>[{doc.cite_id}] {escaped_title}</h3>"
            f"<p style='color:#94A3B8; margin-top:0;'>Type: <b>{html.escape(doc.source_type)}</b> | "
            f"Words: <b>{doc.word_count:,}</b> | Pages: <b>{doc.page_count}</b></p>"
            f"<p><b>Source Location:</b> {uri_html}</p>"
            f"{links_html}"
            f"<hr style='border:1px solid #334155;'/>"
            f"<div style='white-space:pre-wrap; font-family:Consolas, monospace; font-size:12px; "
            f"background:#0F172A; padding:10px; border-radius:6px; border:1px solid #1E293B;'>{escaped_content}</div>"
            f"</div>"
        )

    def update_grounding_and_citations(
        self,
        citations: List[CitationMatch],
        web_references: List[GroundingReference],
    ) -> None:
        """Render structured GroundingSourceCard widgets for synthesis citations and Google Search grounding URIs."""
        self._last_citations = list(citations)
        self._last_web_refs = list(web_references)
        self._showing_cards = True
        self.browser.setVisible(False)
        self.scroll_area.setVisible(True)
        self._clear_cards()

        cite_header = QLabel(f"{get_text('header_citations_inspector', self._lang)} ({len(citations)})")
        cite_header.setStyleSheet("color: #58A6FF; font-size: 14px; font-weight: 700; padding-top: 2px;")
        self.cards_layout.addWidget(cite_header)

        if citations:
            for c in citations:
                card = GroundingSourceCard(
                    header_title=f"[{c.cite_id}] {c.title}",
                    uri=c.path_or_uri,
                    perspective_badge=f"{c.source_type.upper()} • {c.occurrences}",
                    snippet=c.excerpt,
                    accent_color="#10B981",
                    cite_id=c.cite_id,
                )
                self._cards_by_cite_id[c.cite_id] = card
                self.cards_layout.addWidget(card)
        else:
            empty_cite = QLabel(get_text("no_citations_yet", self._lang))
            empty_cite.setWordWrap(True)
            empty_cite.setStyleSheet("color: #94A3B8; font-size: 12px; padding-bottom: 6px;")
            self.cards_layout.addWidget(empty_cite)

        web_header = QLabel(f"{get_text('header_web_uris', self._lang)} ({len(web_references)})")
        web_header.setStyleSheet("color: #79C0FF; font-size: 14px; font-weight: 700; padding-top: 8px;")
        self.cards_layout.addWidget(web_header)

        if web_references:
            for ref in web_references:
                card = GroundingSourceCard(
                    header_title=ref.title,
                    uri=ref.uri,
                    perspective_badge=ref.perspective_name,
                    snippet=ref.snippet,
                    accent_color="#A855F7",
                )
                self.cards_layout.addWidget(card)
        else:
            empty_web = QLabel(get_text("web_uris_help", self._lang))
            empty_web.setWordWrap(True)
            empty_web.setStyleSheet("color: #94A3B8; font-size: 12px;")
            self.cards_layout.addWidget(empty_web)

        self.cards_layout.addStretch(1)

    @staticmethod
    def _on_anchor_clicked(url: QUrl) -> None:
        if url.scheme() in {"http", "https", "file"}:
            QDesktopServices.openUrl(url)


class DialogueRendererWidget(QWidget):
    """Renders the two-host conversational Audio Overview podcast script with distinct speaker cards."""

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._has_script: bool = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setContentsMargins(8, 8, 8, 8)
        self.cards_layout.setSpacing(10)

        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area, stretch=1)

        self.show_placeholder()

    def _clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def retranslate_ui(self, lang: str = "en") -> None:
        self._lang = lang
        if not self._has_script:
            self.show_placeholder()

    def show_placeholder(self) -> None:
        self._has_script = False
        self._clear_cards()
        placeholder = QLabel(get_text("audio_studio_desc", self._lang))
        placeholder.setWordWrap(True)
        placeholder.setStyleSheet("color: #94A3B8; padding: 16px; font-size: 13px;")
        self.cards_layout.addWidget(placeholder)
        self.cards_layout.addStretch(1)

    def render_script(self, script: PodcastScript) -> None:
        """Build speaker cards for every dialogue turn in the PodcastScript."""
        self._has_script = True
        self._clear_cards()

        header = QLabel(f"Episode: {script.title}")
        header.setWordWrap(True)
        header.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #F8FAFC; padding: 8px 4px; border-bottom: 1px solid #334155;"
        )
        self.cards_layout.addWidget(header)

        for idx, turn in enumerate(script.turns, start=1):
            card = self._create_turn_card(idx, turn)
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch(1)

    @staticmethod
    def _create_turn_card(turn_number: int, turn: DialogueTurn) -> QFrame:
        is_host_a = "alex" in turn.speaker.lower() or "host a" in turn.speaker.lower()
        border_color = "#38BDF8" if is_host_a else "#F59E0B"

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: #0F172A; border: 1px solid #1E293B; "
            f"border-left: 4px solid {border_color}; border-radius: 6px; }}"
        )

        vlayout = QVBoxLayout(frame)
        vlayout.setContentsMargins(12, 10, 12, 10)
        vlayout.setSpacing(6)

        speaker_lbl = QLabel(f"#{turn_number}  {turn.speaker}  •  {turn.role_tag}")
        speaker_lbl.setStyleSheet(
            f"color: {border_color}; font-weight: 700; font-size: 12px; border: none; background: transparent;"
        )

        body_lbl = QLabel(turn.text)
        body_lbl.setWordWrap(True)
        body_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body_font = QFont("Segoe UI", 10)
        body_lbl.setFont(body_font)
        body_lbl.setStyleSheet("color: #C9D1D9; border: none; background: transparent; line-height: 1.45;")

        vlayout.addWidget(speaker_lbl)
        vlayout.addWidget(body_lbl)
        return frame


class SourceInspectorDialog(QDialog):
    """Modal inspector showing a reference document's metadata and full extracted text with keyword search."""

    MAX_HIGHLIGHTS = 2000

    def __init__(self, doc: SourceDocument, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._doc = doc
        self._lang = lang
        self._origin_url = self._resolve_origin_url(doc)
        self.setWindowTitle(get_text("source_inspector_title", lang))
        self.setMinimumSize(760, 600)
        self.resize(860, 700)
        self.setModal(True)
        self._build_ui()

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

    def _origin_type_label(self) -> str:
        title = self._doc.title.lstrip()
        if title.startswith("[WEB FULL-TEXT]"):
            key = "source_type_web_full_text"
        elif title.startswith("[WEB SNIPPET]"):
            key = "source_type_web_snippet"
        else:
            key = f"source_type_{self._doc.source_type}"
        label = get_text(key, self._lang)
        return self._doc.source_type if label == key else label

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.title_label = QLabel(f"[{self._doc.cite_id}] {self._doc.title}")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("color: #58A6FF; font-size: 15px; font-weight: 700;")
        layout.addWidget(self.title_label)

        meta_frame = QFrame()
        meta_frame.setStyleSheet(
            "QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 6px; } "
            "QLabel { border: none; background: transparent; }"
        )
        meta_layout = QVBoxLayout(meta_frame)
        meta_layout.setContentsMargins(12, 8, 12, 8)
        meta_layout.setSpacing(3)

        self.meta_labels: Dict[str, QLabel] = {}
        rows = [
            ("inspector_label_title", self._doc.title),
            ("inspector_label_origin", self._origin_type_label()),
            ("inspector_label_words", f"{self._doc.word_count:,}"),
            ("inspector_label_tokens", f"~{self._doc.estimated_tokens:,}"),
            ("inspector_label_location", self._doc.path_or_uri),
        ]
        for key, value in rows:
            row_label = QLabel(f"<b>{html.escape(get_text(key, self._lang))}:</b> {html.escape(str(value))}")
            row_label.setWordWrap(True)
            row_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row_label.setStyleSheet("color: #C9D1D9; font-size: 12px;")
            meta_layout.addWidget(row_label)
            self.meta_labels[key] = row_label
        layout.addWidget(meta_frame)

        action_row = QHBoxLayout()
        self.open_url_btn = QPushButton(get_text("inspector_btn_open_url", self._lang))
        self.open_url_btn.setVisible(bool(self._origin_url))
        self.open_url_btn.clicked.connect(self._on_open_url)
        action_row.addWidget(self.open_url_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(get_text("inspector_search_placeholder", self._lang))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.search)
        self.search_input.returnPressed.connect(self.find_next)
        self.match_label = QLabel("")
        self.match_label.setStyleSheet("color: #94A3B8; font-size: 12px;")
        search_row.addWidget(self.search_input, stretch=1)
        search_row.addWidget(self.match_label)
        layout.addLayout(search_row)

        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_view.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.text_view.setFont(QFont("Consolas", 10))
        self.text_view.setStyleSheet(
            "QPlainTextEdit { background-color: #0D1117; color: #C9D1D9; border: 1px solid #30363D; "
            "border-radius: 6px; padding: 8px; selection-background-color: #1F6FEB; }"
        )
        self.text_view.setPlainText(self._doc.content)
        layout.addWidget(self.text_view, stretch=1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        self.close_btn = QPushButton(get_text("btn_close", self._lang))
        self.close_btn.clicked.connect(self.accept)
        close_row.addWidget(self.close_btn)
        layout.addLayout(close_row)

    def _on_open_url(self) -> None:
        if self._origin_url:
            QDesktopServices.openUrl(QUrl(self._origin_url))

    def search(self, term: str) -> int:
        """Highlight every case-insensitive match of `term`, jump to the first, and return the match count."""
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
        """Advance to the next match (wrapping around)."""
        needle = self.search_input.text().strip()
        if not needle:
            return
        if not self.text_view.find(needle):
            cursor = self.text_view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.text_view.setTextCursor(cursor)
            self.text_view.find(needle)


def format_media_time(milliseconds: int) -> str:
    """Format a millisecond position as MM:SS (or H:MM:SS when over an hour)."""
    total_seconds = max(0, int(milliseconds // 1000))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class AudioPlayerWidget(QFrame):
    """Embedded audio briefing player: play/pause, scrub slider, time label, volume, and MP3 export."""

    audio_Saved = pyqtSignal(str)

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self.current_path: Optional[str] = None
        self._duration_ms: int = 0
        self.setStyleSheet(
            "AudioPlayerWidget { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; }"
        )

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.8)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

        self._build_ui()
        self._sync_enabled()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        self.hint_label = QLabel(get_text("audio_player_empty", self._lang))
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #94A3B8; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(self.hint_label)

        transport = QHBoxLayout()
        transport.setSpacing(8)
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(44)
        self.play_btn.clicked.connect(self.toggle_playback)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self.player.setPosition)
        self.position_slider.sliderReleased.connect(lambda: self.player.setPosition(self.position_slider.value()))

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #C9D1D9; font-size: 12px; border: none; background: transparent;")
        self.time_label.setMinimumWidth(96)

        transport.addWidget(self.play_btn)
        transport.addWidget(self.position_slider, stretch=1)
        transport.addWidget(self.time_label)
        layout.addLayout(transport)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        volume_icon = QLabel("🔊")
        volume_icon.setStyleSheet("border: none; background: transparent;")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100.0))

        self.speed_combo = QComboBox()
        self.speed_combo.setToolTip("Playback Speed")
        self.speed_combo.setFixedWidth(72)
        self.speed_combo.addItem("1.0x", 1.0)
        self.speed_combo.addItem("1.25x", 1.25)
        self.speed_combo.addItem("1.5x", 1.5)
        self.speed_combo.addItem("2.0x", 2.0)
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)

        self.save_btn = QPushButton(get_text("btn_save_audio", self._lang))
        self.save_btn.clicked.connect(self._on_save_clicked)

        footer.addWidget(volume_icon)
        footer.addWidget(self.volume_slider)
        footer.addWidget(self.speed_combo)
        footer.addStretch(1)
        footer.addWidget(self.save_btn)
        layout.addLayout(footer)

    # --- public API ---

    def retranslate_ui(self, lang: str = "en") -> None:
        self._lang = lang
        self.save_btn.setText(get_text("btn_save_audio", lang))
        self.hint_label.setText(get_text("audio_player_empty", lang))

    def load_file(self, path: str) -> None:
        """Load an MP3 into the player and enable the controls."""
        self.player.stop()
        self.current_path = str(path)
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self._sync_enabled()

    def release(self) -> None:
        """Release the file handle so the MP3 can be re-rendered/overwritten (required on Windows)."""
        self.player.stop()
        self.player.setSource(QUrl())
        self._duration_ms = 0
        self.position_slider.setRange(0, 0)
        self.time_label.setText("00:00 / 00:00")

    def clear(self) -> None:
        self.release()
        self.current_path = None
        self.speed_combo.setCurrentIndex(0)
        self.player.setPlaybackRate(1.0)
        self._sync_enabled()

    def toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    # --- internals ---

    def _sync_enabled(self) -> None:
        has_audio = bool(self.current_path)
        self.play_btn.setEnabled(has_audio)
        self.position_slider.setEnabled(has_audio)
        self.save_btn.setEnabled(has_audio)
        self.speed_combo.setEnabled(has_audio)
        self.hint_label.setVisible(not has_audio)

    def _on_speed_changed(self) -> None:
        rate = float(self.speed_combo.currentData() or 1.0)
        self.player.setPlaybackRate(rate)

    def _on_position_changed(self, position: int) -> None:
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        self.time_label.setText(f"{format_media_time(position)} / {format_media_time(self._duration_ms)}")

    def _on_duration_changed(self, duration: int) -> None:
        self._duration_ms = max(0, duration)
        self.position_slider.setRange(0, self._duration_ms)
        self.time_label.setText(
            f"{format_media_time(self.player.position())} / {format_media_time(self._duration_ms)}"
        )

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_btn.setText("⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶")

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.play_btn.setText("▶")

    def _on_save_clicked(self) -> None:
        if not self.current_path:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            get_text("audio_save_dialog_title", self._lang),
            str(Path.home() / "audio_briefing.mp3"),
            "MP3 Audio (*.mp3)",
        )
        if destination:
            self.save_copy_to(destination)

    def save_copy_to(self, destination: str) -> str:
        """Copy the rendered MP3 to `destination` and emit `audio_Saved`."""
        if not self.current_path:
            raise FileNotFoundError("No rendered audio is loaded.")
        target = Path(destination)
        if target.suffix.lower() != ".mp3":
            target = target.with_suffix(".mp3")
        shutil.copyfile(self.current_path, target)
        self.audio_Saved.emit(str(target))
        return str(target)


class SpendLedgerDialog(QDialog):
    """Detailed audit dialogue displaying per-call token breakdown and dollar spend."""

    def __init__(self, ledger: Optional[TokenLedger] = None, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ledger = ledger or TokenLedger.get_instance()
        self._lang = lang
        self.setWindowTitle(get_text("token_ledger_dialog_title", self._lang))
        self.resize(820, 500)
        self._build_ui()
        self._populate_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Summary Header Card
        self.summary_card = QFrame()
        self.summary_card.setStyleSheet(
            "QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 10px; }"
        )
        card_layout = QHBoxLayout(self.summary_card)

        self.totals_label = QLabel()
        self.totals_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #38BDF8;")
        card_layout.addWidget(self.totals_label)
        layout.addWidget(self.summary_card)

        # Audit Table
        self.table = QTableWidget()
        headers = [
            get_text("token_ledger_col_time", self._lang),
            "Session",
            get_text("token_ledger_col_model", self._lang),
            get_text("token_ledger_col_prompt", self._lang),
            get_text("token_ledger_col_output", self._lang),
            get_text("token_ledger_col_cached", self._lang),
            get_text("token_ledger_col_cost", self._lang),
        ]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #0B0F19; border: 1px solid #1E293B; border-radius: 6px; } "
            "QTableWidget::item { padding: 4px; } "
            "QHeaderView::section { background-color: #1E293B; color: #94A3B8; padding: 6px; font-weight: 600; border: none; }"
        )
        layout.addWidget(self.table, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_clear = QPushButton("Clear Audit History" if self._lang == "en" else "내역 초기화")
        self.btn_clear.setStyleSheet("background-color: #334155; color: #F1F5F9; border-radius: 4px; padding: 6px 14px;")
        self.btn_clear.clicked.connect(self._on_clear)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch(1)

        self.btn_close = QPushButton("Close" if self._lang == "en" else "닫기")
        self.btn_close.setStyleSheet("background-color: #2563EB; color: #FFFFFF; font-weight: bold; border-radius: 4px; padding: 6px 18px;")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _populate_data(self) -> None:
        records = self.ledger.get_all_records()
        totals = self.ledger.get_session_totals()

        summary_text = (
            f"Spend: ${totals.total_cost_usd:.4f} USD  |  "
            f"Prompt: {totals.prompt_tokens:,}  |  "
            f"Output: {totals.candidate_tokens:,}  |  "
            f"Cached: {totals.cached_tokens:,}  |  "
            f"Calls: {len(records)}"
        )
        self.totals_label.setText(summary_text)

        self.table.setRowCount(len(records))
        for row, rec in enumerate(records):
            self.table.setItem(row, 0, QTableWidgetItem(rec.timestamp))
            self.table.setItem(row, 1, QTableWidgetItem(rec.session_id))
            self.table.setItem(row, 2, QTableWidgetItem(rec.model))
            self.table.setItem(row, 3, QTableWidgetItem(f"{rec.prompt_tokens:,}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{rec.candidate_tokens:,}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{rec.cached_tokens:,}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"${rec.cost_usd:.6f}"))

    def _on_clear(self) -> None:
        self.ledger.clear()
        self._populate_data()


class CheckpointManagerDialog(QDialog):
    """Dialog for managing project snapshots, branching, and historical delta restoration."""

    restore_requested = pyqtSignal(str)
    fork_requested = pyqtSignal(str)
    create_requested = pyqtSignal(str, str)

    def __init__(
        self,
        checkpoints: List[Dict[str, Any]],
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.checkpoints = list(checkpoints)
        self._lang = lang
        self.selected_checkpoint_id: Optional[str] = None
        self.setWindowTitle(get_text("checkpoint_dialog_title", self._lang))
        self.resize(760, 460)
        self._build_ui()
        self._populate_data()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header card
        header = QFrame()
        header.setStyleSheet("QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 10px; }")
        hl = QHBoxLayout(header)
        desc = QLabel(
            "Track research milestones, branch into alternative inquiries, or restore prior synthesis states."
            if self._lang == "en"
            else "연구 마일스톤을 체크포인트로 저장하고 다른 가설로 분기하거나 이전 상태로 복원합니다."
        )
        desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        hl.addWidget(desc)
        layout.addWidget(header)

        # Table
        self.table = QTableWidget()
        headers = ["Timestamp", "Snapshot Name", "Description", "Tabs", "Docs"] if self._lang == "en" else ["일시", "스냅샷 이름", "설명", "탭 수", "문서 수"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #0B0F19; border: 1px solid #1E293B; border-radius: 6px; } "
            "QTableWidget::item { padding: 4px; } "
            "QHeaderView::section { background-color: #1E293B; color: #94A3B8; padding: 6px; font-weight: 600; border: none; }"
        )
        layout.addWidget(self.table, stretch=1)

        # Action Buttons
        btn_row = QHBoxLayout()
        self.btn_create = QPushButton(get_text("checkpoint_create", self._lang))
        self.btn_create.setStyleSheet("background-color: #059669; color: #FFFFFF; font-weight: 600; border-radius: 4px; padding: 6px 14px;")
        self.btn_create.clicked.connect(self._on_create_clicked)
        btn_row.addWidget(self.btn_create)

        self.btn_restore = QPushButton(get_text("checkpoint_restore", self._lang))
        self.btn_restore.setStyleSheet("background-color: #2563EB; color: #FFFFFF; font-weight: 600; border-radius: 4px; padding: 6px 14px;")
        self.btn_restore.setEnabled(False)
        self.btn_restore.clicked.connect(self._on_restore_clicked)
        btn_row.addWidget(self.btn_restore)

        self.btn_fork = QPushButton(get_text("checkpoint_fork", self._lang))
        self.btn_fork.setStyleSheet("background-color: #7E22CE; color: #FFFFFF; font-weight: 600; border-radius: 4px; padding: 6px 14px;")
        self.btn_fork.setEnabled(False)
        self.btn_fork.clicked.connect(self._on_fork_clicked)
        btn_row.addWidget(self.btn_fork)

        btn_row.addStretch(1)

        self.btn_close = QPushButton("Close" if self._lang == "en" else "닫기")
        self.btn_close.setStyleSheet("background-color: #334155; color: #F1F5F9; border-radius: 4px; padding: 6px 16px;")
        self.btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_close)

        layout.addLayout(btn_row)

    def _populate_data(self) -> None:
        self.table.setRowCount(len(self.checkpoints))
        for row, cp in enumerate(self.checkpoints):
            self.table.setItem(row, 0, QTableWidgetItem(str(cp.get("timestamp", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(str(cp.get("name", ""))))
            self.table.setItem(row, 2, QTableWidgetItem(str(cp.get("description", ""))))
            self.table.setItem(row, 3, QTableWidgetItem(str(cp.get("workspaces_count", 1))))
            self.table.setItem(row, 4, QTableWidgetItem(str(cp.get("documents_count", 0))))

    def _on_selection_changed(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            if 0 <= row < len(self.checkpoints):
                self.selected_checkpoint_id = self.checkpoints[row].get("id")
                self.btn_restore.setEnabled(True)
                self.btn_fork.setEnabled(True)
                return
        self.selected_checkpoint_id = None
        self.btn_restore.setEnabled(False)
        self.btn_fork.setEnabled(False)

    def _on_create_clicked(self) -> None:
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self,
            get_text("checkpoint_create", self._lang),
            get_text("checkpoint_name_prompt", self._lang),
            text=f"Checkpoint {len(self.checkpoints) + 1}",
        )
        if ok and name.strip():
            self.create_requested.emit(name.strip(), "")
            self.accept()

    def _on_restore_clicked(self) -> None:
        if self.selected_checkpoint_id:
            self.restore_requested.emit(self.selected_checkpoint_id)
            self.accept()

    def _on_fork_clicked(self) -> None:
        if self.selected_checkpoint_id:
            self.fork_requested.emit(self.selected_checkpoint_id)
            self.accept()
