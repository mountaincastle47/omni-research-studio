"""Live incremental streaming Markdown renderer with debounce timer and syntax auto-repair."""

from __future__ import annotations

import re
from typing import List, Optional

from PyQt6.QtCore import QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QTextBrowser, QWidget

from core.document_loader import SourceDocument
from core.markdown_utils import build_dark_html
from core.notebook_synthesis import create_semantic_anchor_builder, sanitize_unclosed_markdown


def repair_streaming_markdown(raw_text: str) -> str:
    """Auto-close dangling markdown syntax on live streaming partial tokens."""
    if not raw_text:
        return ""
    text = sanitize_unclosed_markdown(raw_text)

    # Auto-close unclosed bolding or italics
    if text.count("**") % 2 != 0:
        text += "**"
    elif text.count("*") % 2 != 0:
        text += "*"

    return text


class StreamingMarkdownViewer(QTextBrowser):
    """Incremental streaming Markdown renderer with 80ms debounce and sticky scroll locking."""

    citation_clicked = pyqtSignal(QUrl)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._on_anchor_clicked)

        self._raw_buffer: str = ""
        self._documents: Optional[List[SourceDocument]] = None
        self._critic_verdicts: Optional[dict] = None
        self._user_scrolled_up: bool = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(80)  # 80ms debounce
        self._debounce_timer.timeout.connect(self._render_buffered_html)

        # Monitor user scroll position
        vbar = self.verticalScrollBar()
        vbar.valueChanged.connect(self._on_scroll_value_changed)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        self.citation_clicked.emit(url)

    def _on_scroll_value_changed(self, value: int) -> None:
        vbar = self.verticalScrollBar()
        # If within 25px of the bottom, user is anchored to the bottom
        is_at_bottom = value >= (vbar.maximum() - 25)
        self._user_scrolled_up = not is_at_bottom

    def set_documents(self, documents: Optional[List[SourceDocument]]) -> None:
        self._documents = documents

    def set_critic_verdicts(self, verdicts: Optional[dict]) -> None:
        self._critic_verdicts = verdicts

    def append_chunk(self, chunk: str) -> None:
        """Append incoming streaming token chunk and restart 80ms debounce timer."""
        self._raw_buffer += chunk
        if not self._debounce_timer.isActive():
            self._debounce_timer.start()

    def flush(self) -> None:
        """Force immediate render of the accumulated buffer."""
        self._debounce_timer.stop()
        self._render_buffered_html()

    def set_markdown_text(self, markdown_text: str) -> None:
        """Set complete markdown text and render immediately."""
        self._debounce_timer.stop()
        self._raw_buffer = markdown_text
        self._user_scrolled_up = False
        self._render_buffered_html()

    def get_raw_markdown(self) -> str:
        return self._raw_buffer

    def clear_viewer(self) -> None:
        self._debounce_timer.stop()
        self._raw_buffer = ""
        self.clear()

    def _render_buffered_html(self) -> None:
        if not self._raw_buffer:
            self.clear()
            return

        repaired_md = repair_streaming_markdown(self._raw_buffer)
        anchor_builder = (
            create_semantic_anchor_builder(self._documents, critic_verdicts=self._critic_verdicts)
            if self._documents
            else None
        )
        html_content = build_dark_html(
            repaired_md,
            interactive_citations=True,
            anchor_builder=anchor_builder,
        )

        vbar = self.verticalScrollBar()
        prev_val = vbar.value()

        self.setHtml(html_content)

        if not self._user_scrolled_up:
            self.moveCursor(QTextCursor.MoveOperation.End)
            vbar.setValue(vbar.maximum())
        else:
            vbar.setValue(min(prev_val, vbar.maximum()))
