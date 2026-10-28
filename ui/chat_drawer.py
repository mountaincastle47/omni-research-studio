"""Collapsible Follow-Up Q&A Console drawer shown beneath the Grounded Synthesis report viewer."""

from __future__ import annotations

import html
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QTextOption
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.i18n import get_text
from core.markdown_utils import build_dark_html

BODY_EXPANDED_HEIGHT = 270

USER_BUBBLE_CSS = (
    "QTextBrowser { background-color: rgba(31, 111, 235, 46); border: 1px solid #1F6FEB; "
    "border-radius: 10px; padding: 4px 8px; color: #E6EDF3; }"
)
ASSISTANT_BUBBLE_CSS = (
    "QTextBrowser { background-color: #0F172A; border: 1px solid #30363D; "
    "border-radius: 10px; padding: 4px 8px; color: #C9D1D9; }"
)
ERROR_BUBBLE_CSS = (
    "QTextBrowser { background-color: rgba(248, 81, 73, 30); border: 1px solid #DA3633; "
    "border-radius: 10px; padding: 4px 8px; color: #FFA198; }"
)


class ChatBubble(QTextBrowser):
    """A single chat message bubble. Citation anchors (`cite:N` or `cite:N:P`) are emitted, never navigated."""

    citation_clicked = pyqtSignal(int)
    citation_url_clicked = pyqtSignal(QUrl)

    def __init__(self, role: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.role = role
        self._text = ""
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(USER_BUBBLE_CSS if role == "user" else ASSISTANT_BUBBLE_CSS)
        self.anchorClicked.connect(self._on_anchor_clicked)
        self.set_message_text("")

    @property
    def message_text(self) -> str:
        return self._text

    def set_message_text(self, text: str) -> None:
        """Render `text` (Markdown for assistant, escaped plain text for user) and fit the bubble height."""
        self._text = text
        if self.role == "user":
            escaped = html.escape(text).replace("\n", "<br/>")
            self.setHtml(f"<body style='color:#E6EDF3; font-size:13px; line-height:1.5;'>{escaped}</body>")
        else:
            self.setHtml(build_dark_html(text or " ", interactive_citations=True))
        self.fit_height()

    def mark_error(self) -> None:
        self.setStyleSheet(ERROR_BUBBLE_CSS)

    def fit_height(self) -> None:
        width = self.viewport().width()
        if width < 120:
            width = max(220, (self.parentWidget().width() - 40) if self.parentWidget() else 360)
        self.document().setTextWidth(width)
        self.setFixedHeight(int(self.document().size().height()) + 20)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self.fit_height()

    def _on_anchor_clicked(self, url: QUrl) -> None:
        if url.scheme() == "cite":
            self.citation_url_clicked.emit(url)
            try:
                self.citation_clicked.emit(int(url.toString().split(":")[1]))
            except (ValueError, IndexError):
                pass
        elif url.scheme() in {"http", "https"}:
            QDesktopServices.openUrl(url)


class ChatMessageWidget(QWidget):
    """Role caption + bubble with distinct alignment for user vs assistant messages."""

    def __init__(self, role: str, caption: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.role = role
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0 if role == "assistant" else 36, 0, 36 if role == "assistant" else 0, 0)
        layout.setSpacing(2)
        self.caption_label = QLabel(caption)
        self.caption_label.setAlignment(
            Qt.AlignmentFlag.AlignRight if role == "user" else Qt.AlignmentFlag.AlignLeft
        )
        self.caption_label.setStyleSheet(
            f"color: {'#58A6FF' if role == 'user' else '#3FB950'}; font-size: 11px; font-weight: 700;"
            "border: none; background: transparent;"
        )
        self.bubble = ChatBubble(role)
        layout.addWidget(self.caption_label)
        layout.addWidget(self.bubble)


class _HistoryAccessor(list):
    """List subclass that can also be called as a zero-argument method: history() or history[:]."""

    def __call__(self) -> List[Dict[str, str]]:
        return list(self)


class FollowUpChatDrawer(QWidget):
    """Collapsible bottom drawer: header toggle, clear button, scrollable bubbles, and a single-line prompt input."""

    question_submitted = pyqtSignal(str)
    citation_clicked = pyqtSignal(int)
    citation_url_clicked = pyqtSignal(QUrl)
    clear_requested = pyqtSignal()

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._expanded = False
        self._busy = False
        self._history: List[Dict[str, str]] = []
        self._pending_question: Optional[str] = None
        self._active_assistant: Optional[ChatMessageWidget] = None
        self._build_ui()
        self.set_expanded(False)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.toggle_btn = QPushButton()
        self.toggle_btn.setObjectName("ChatDrawerToggle")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setStyleSheet(
            "QPushButton#ChatDrawerToggle { background-color: #161B22; border: 1px solid #30363D; border-radius: 6px; "
            "color: #58A6FF; font-weight: 700; padding: 6px 12px; text-align: left; } "
            "QPushButton#ChatDrawerToggle:hover { background-color: #1E293B; }"
        )
        self.toggle_btn.clicked.connect(lambda: self.set_expanded(not self._expanded))

        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._on_clear_clicked)

        header.addWidget(self.toggle_btn, stretch=1)
        header.addWidget(self.clear_btn)
        root.addLayout(header)

        self.body = QFrame()
        self.body.setStyleSheet("QFrame#ChatBody { background-color: #0B0F19; border: 1px solid #1E293B; border-radius: 8px; }")
        self.body.setObjectName("ChatBody")
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(8)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(2, 2, 2, 2)
        self.messages_layout.setSpacing(10)

        self.empty_hint = QLabel()
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet("color: #94A3B8; font-size: 12px; padding: 8px;")
        self.messages_layout.addWidget(self.empty_hint)
        self.messages_layout.addStretch(1)
        self.scroll_area.setWidget(self.messages_container)
        body_layout.addWidget(self.scroll_area, stretch=1)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input = QLineEdit()
        self.input.returnPressed.connect(self._on_send_clicked)
        self.send_btn = QPushButton()
        self.send_btn.setObjectName("PrimaryActionBtn")
        self.send_btn.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self.input, stretch=1)
        input_row.addWidget(self.send_btn)
        body_layout.addLayout(input_row)

        root.addWidget(self.body)
        self.retranslate_ui(self._lang)

    # --- state ---

    def is_expanded(self) -> bool:
        return self._expanded

    def is_busy(self) -> bool:
        return self._busy

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.body.setVisible(expanded)
        self.body.setFixedHeight(BODY_EXPANDED_HEIGHT)
        self._refresh_toggle_text()
        if expanded:
            self.input.setFocus()

    def _refresh_toggle_text(self) -> None:
        arrow = "▼" if self._expanded else "▲"
        self.toggle_btn.setText(f"{arrow} {get_text('chat_drawer_toggle', self._lang)}")

    def set_busy(self, busy: bool) -> None:
        """Disable the prompt controls while an answer is streaming."""
        self._busy = busy
        self.input.setEnabled(not busy)
        self.send_btn.setEnabled(not busy)
        self.clear_btn.setEnabled(not busy)

    def retranslate_ui(self, lang: str = "en") -> None:
        self._lang = lang
        self._refresh_toggle_text()
        self.toggle_btn.setToolTip(get_text("tooltip_chat_toggle", lang))
        self.clear_btn.setText(get_text("chat_btn_clear", lang))
        self.clear_btn.setToolTip(get_text("tooltip_chat_clear", lang))
        self.send_btn.setText(get_text("chat_btn_send", lang))
        self.send_btn.setToolTip(get_text("tooltip_chat_send", lang))
        self.input.setPlaceholderText(get_text("chat_placeholder", lang))
        self.empty_hint.setText(get_text("chat_empty_hint", lang))
        for index in range(self.messages_layout.count()):
            widget = self.messages_layout.itemAt(index).widget()
            if isinstance(widget, ChatMessageWidget):
                key = "chat_role_user" if widget.role == "user" else "chat_role_assistant"
                widget.caption_label.setText(get_text(key, lang))

    # --- messages ---

    def _insert_message(self, role: str, text: str) -> ChatMessageWidget:
        key = "chat_role_user" if role == "user" else "chat_role_assistant"
        message = ChatMessageWidget(role, get_text(key, self._lang))
        message.bubble.citation_clicked.connect(self.citation_clicked)
        message.bubble.citation_url_clicked.connect(self.citation_url_clicked)
        message.bubble.set_message_text(text)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, message)
        self.empty_hint.setVisible(False)
        self._scroll_to_bottom()
        return message

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, lambda: self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum()))

    def add_user_message(self, text: str) -> None:
        """Append the user's question bubble and clear the prompt input."""
        self._pending_question = text
        self._insert_message("user", text)
        self.input.clear()

    def begin_assistant_message(self) -> None:
        """Create an empty assistant bubble that will receive streamed chunks."""
        self._active_assistant = self._insert_message("assistant", "")

    def append_assistant_chunk(self, chunk: str) -> None:
        """Append a streamed token chunk and re-render the active assistant bubble."""
        if self._active_assistant is None:
            self.begin_assistant_message()
        assert self._active_assistant is not None
        bubble = self._active_assistant.bubble
        bubble.set_message_text(bubble.message_text + chunk)
        self._scroll_to_bottom()

    def finish_assistant_message(self, final_text: Optional[str] = None) -> None:
        """Finalize the active answer and persist the (question, answer) pair into the chat history."""
        if self._active_assistant is None:
            self.begin_assistant_message()
        assert self._active_assistant is not None
        bubble = self._active_assistant.bubble
        if final_text is not None and final_text != bubble.message_text:
            bubble.set_message_text(final_text)
        if self._pending_question is not None:
            self._history.append({"role": "user", "text": self._pending_question})
            self._history.append({"role": "assistant", "text": bubble.message_text})
        self._pending_question = None
        self._active_assistant = None

    def abort_assistant_message(self, error_text: str = "") -> None:
        """Replace the partial answer with an error note; the pair is not added to the history."""
        if self._active_assistant is not None:
            bubble = self._active_assistant.bubble
            if error_text:
                bubble.set_message_text(error_text)
                bubble.mark_error()
            else:
                self._active_assistant.setParent(None)
                self._active_assistant.deleteLater()
        self._pending_question = None
        self._active_assistant = None

    @property
    def history(self) -> _HistoryAccessor:
        return _HistoryAccessor(dict(entry) for entry in self._history)

    # Aliases
    to_dict_list = history
    start_assistant_message = begin_assistant_message
    def load_history(self, history: List[Dict[str, str]]) -> None:
        """Rebuild the conversation UI from a saved history (used by project load)."""
        self.clear_chat(emit_signal=False)
        for entry in history:
            role = "assistant" if entry.get("role") == "assistant" else "user"
            text = str(entry.get("text", ""))
            self._insert_message(role, text)
            self._history.append({"role": role, "text": text})

    load_from_dict_list = load_history

    def clear_chat(self, emit_signal: bool = True) -> None:
        """Remove all bubbles and history."""
        for index in reversed(range(self.messages_layout.count())):
            widget = self.messages_layout.itemAt(index).widget()
            if isinstance(widget, ChatMessageWidget):
                self.messages_layout.removeWidget(widget)
                widget.setParent(None)
                widget.deleteLater()
        self._history.clear()
        self._pending_question = None
        self._active_assistant = None
        self.empty_hint.setVisible(True)
        if emit_signal:
            self.clear_requested.emit()

    def message_count(self) -> int:
        return sum(
            1
            for index in range(self.messages_layout.count())
            if isinstance(self.messages_layout.itemAt(index).widget(), ChatMessageWidget)
        )

    # --- slots ---

    def _on_send_clicked(self) -> None:
        text = self.input.text().strip()
        if text and not self._busy:
            self.question_submitted.emit(text)

    def _on_clear_clicked(self) -> None:
        if not self._busy:
            self.clear_chat(emit_signal=True)
