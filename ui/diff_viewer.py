"""Visual Side-by-Side Document Diff Inspector: Synchronized dual-pane line comparison with gutter badges."""

from __future__ import annotations

import difflib
from typing import Any, List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.document_loader import SourceDocument
from core.i18n import get_text


def compute_line_diff(text_a: str, text_b: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, int, int]:
    """
    Compare text_a and text_b line-by-line using difflib.
    Returns:
        (left_lines, right_lines, added_count, deleted_count, unchanged_count)
    """
    lines_a = [l.rstrip("\r\n") for l in text_a.splitlines()]
    lines_b = [l.rstrip("\r\n") for l in text_b.splitlines()]

    matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
    left_rows: List[Dict[str, Any]] = []
    right_rows: List[Dict[str, Any]] = []

    added = 0
    deleted = 0
    unchanged = 0

    for tag, alo, ahi, blo, bhi in matcher.get_opcodes():
        if tag == "equal":
            for i in range(alo, ahi):
                unchanged += 1
                row_l = {"tag": "equal", "text": lines_a[i], "line_num": i + 1}
                row_r = {"tag": "equal", "text": lines_b[blo + (i - alo)], "line_num": blo + (i - alo) + 1}
                left_rows.append(row_l)
                right_rows.append(row_r)
        elif tag == "delete":
            for i in range(alo, ahi):
                deleted += 1
                left_rows.append({"tag": "delete", "text": lines_a[i], "line_num": i + 1})
                right_rows.append({"tag": "empty", "text": "", "line_num": ""})
        elif tag == "insert":
            for j in range(blo, bhi):
                added += 1
                left_rows.append({"tag": "empty", "text": "", "line_num": ""})
                right_rows.append({"tag": "insert", "text": lines_b[j], "line_num": j + 1})
        elif tag == "replace":
            len_a = ahi - alo
            len_b = bhi - blo
            max_len = max(len_a, len_b)
            for k in range(max_len):
                if k < len_a:
                    deleted += 1
                    left_rows.append({"tag": "replace", "text": lines_a[alo + k], "line_num": alo + k + 1})
                else:
                    left_rows.append({"tag": "empty", "text": "", "line_num": ""})

                if k < len_b:
                    added += 1
                    right_rows.append({"tag": "replace", "text": lines_b[blo + k], "line_num": blo + k + 1})
                else:
                    right_rows.append({"tag": "empty", "text": "", "line_num": ""})

    return left_rows, right_rows, added, deleted, unchanged


class DocumentDiffDialog(QDialog):
    """Side-by-side synchronized document diff viewer dialog."""

    def __init__(
        self,
        documents: Optional[List[SourceDocument]] = None,
        corpus: Optional[Any] = None,
        doc_a: Optional[SourceDocument | str] = None,
        doc_b: Optional[SourceDocument | str] = None,
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._lang = lang
        if corpus is not None and not documents:
            if hasattr(corpus, "get_all_documents"):
                documents = corpus.get_all_documents()
            elif hasattr(corpus, "documents"):
                documents = list(corpus.documents.values()) if isinstance(corpus.documents, dict) else list(corpus.documents)
            else:
                documents = []
        self._documents = documents or []
        self._syncing_scroll = False

        self.setWindowTitle(get_text("diff_dialog_title", self._lang))
        self.resize(1100, 720)
        self._build_ui()

        if doc_a is not None or doc_b is not None:
            self._preselect_documents(doc_a, doc_b)
            self._run_diff()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top Control Bar
        top_bar = QFrame(self)
        top_bar.setStyleSheet("QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 8px; }")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setSpacing(12)

        # Selector A
        lbl_a = QLabel(get_text("diff_doc_a_label", self._lang))
        lbl_a.setStyleSheet("color: #F87171; font-weight: 700; font-size: 11px;")
        top_layout.addWidget(lbl_a)

        self.combo_a = QComboBox(self)
        self.combo_a.setStyleSheet("QComboBox { background-color: #1E293B; color: #F1F5F9; border: 1px solid #334155; border-radius: 4px; padding: 4px 8px; min-width: 240px; }")
        top_layout.addWidget(self.combo_a)

        top_layout.addSpacing(16)

        # Selector B
        lbl_b = QLabel(get_text("diff_doc_b_label", self._lang))
        lbl_b.setStyleSheet("color: #4ADE80; font-weight: 700; font-size: 11px;")
        top_layout.addWidget(lbl_b)

        self.combo_b = QComboBox(self)
        self.combo_b.setStyleSheet("QComboBox { background-color: #1E293B; color: #F1F5F9; border: 1px solid #334155; border-radius: 4px; padding: 4px 8px; min-width: 240px; }")
        top_layout.addWidget(self.combo_b)

        top_layout.addStretch(1)

        self.btn_run_diff = QPushButton(get_text("diff_run_btn", self._lang), self)
        self.btn_run_diff.setStyleSheet("QPushButton { background-color: #0284C7; color: #FFFFFF; font-weight: 700; border-radius: 6px; padding: 6px 16px; font-size: 12px; } QPushButton:hover { background-color: #0369A1; }")
        self.btn_run_diff.clicked.connect(self._run_diff)
        top_layout.addWidget(self.btn_run_diff)

        layout.addWidget(top_bar)

        # Populate Combos if documents given
        for doc in self._documents:
            entry = f"[{doc.cite_id}] {doc.title} ({doc.word_count} words)"
            self.combo_a.addItem(entry, userData=doc)
            self.combo_b.addItem(entry, userData=doc)

        if self.combo_b.count() > 1:
            self.combo_b.setCurrentIndex(1)

        # Dual-Pane Diff View
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setStyleSheet("QSplitter::handle { background-color: #1E293B; width: 4px; }")

        # Left Browser (Document A)
        pane_a = QWidget()
        pane_a_layout = QVBoxLayout(pane_a)
        pane_a_layout.setContentsMargins(0, 0, 0, 0)
        pane_a_layout.setSpacing(4)
        self.title_a = QLabel("Document A [Baseline]")
        self.title_a.setStyleSheet("color: #F87171; font-weight: 700; font-size: 12px; padding: 2px 4px;")
        pane_a_layout.addWidget(self.title_a)

        self.browser_a = QTextBrowser(self)
        self.browser_a.setFont(QFont("Consolas", 10))
        self.browser_a.setStyleSheet("QTextBrowser { background-color: #090D16; color: #E2E8F0; border: 1px solid #1E293B; border-radius: 6px; }")
        pane_a_layout.addWidget(self.browser_a)
        splitter.addWidget(pane_a)

        # Right Browser (Document B)
        pane_b = QWidget()
        pane_b_layout = QVBoxLayout(pane_b)
        pane_b_layout.setContentsMargins(0, 0, 0, 0)
        pane_b_layout.setSpacing(4)
        self.title_b = QLabel("Document B [Comparison]")
        self.title_b.setStyleSheet("color: #4ADE80; font-weight: 700; font-size: 12px; padding: 2px 4px;")
        pane_b_layout.addWidget(self.title_b)

        self.browser_b = QTextBrowser(self)
        self.browser_b.setFont(QFont("Consolas", 10))
        self.browser_b.setStyleSheet("QTextBrowser { background-color: #090D16; color: #E2E8F0; border: 1px solid #1E293B; border-radius: 6px; }")
        pane_b_layout.addWidget(self.browser_b)
        splitter.addWidget(pane_b)

        layout.addWidget(splitter, stretch=1)

        # Synchronize Vertical Scrollbars
        scroll_a = self.browser_a.verticalScrollBar()
        scroll_b = self.browser_b.verticalScrollBar()
        scroll_a.valueChanged.connect(self._sync_scroll_a_to_b)
        scroll_b.valueChanged.connect(self._sync_scroll_b_to_a)

        # Bottom Bar: Metrics Badge + Close
        bottom_bar = QHBoxLayout()
        self.metric_badge = QLabel("0 added / 0 deleted / 0 identical lines")
        self.metric_badge.setStyleSheet(
            "QLabel { background-color: #1E293B; color: #38BDF8; font-weight: 700; "
            "font-size: 11px; padding: 4px 12px; border-radius: 4px; border: 1px solid #334155; }"
        )
        bottom_bar.addWidget(self.metric_badge)

        bottom_bar.addStretch(1)

        btn_close = QPushButton("Close" if self._lang == "en" else "닫기", self)
        btn_close.setStyleSheet("QPushButton { background-color: #334155; color: #F1F5F9; border-radius: 4px; padding: 6px 16px; font-size: 11px; }")
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)

        layout.addLayout(bottom_bar)

    def _sync_scroll_a_to_b(self, val: int) -> None:
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        self.browser_b.verticalScrollBar().setValue(val)
        self._syncing_scroll = False

    def _sync_scroll_b_to_a(self, val: int) -> None:
        if self._syncing_scroll:
            return
        self._syncing_scroll = True
        self.browser_a.verticalScrollBar().setValue(val)
        self._syncing_scroll = False

    def _preselect_documents(self, doc_a: Any, doc_b: Any) -> None:
        if isinstance(doc_a, SourceDocument):
            for i in range(self.combo_a.count()):
                d = self.combo_a.itemData(i)
                if isinstance(d, SourceDocument) and d.cite_id == doc_a.cite_id:
                    self.combo_a.setCurrentIndex(i)
                    break
        elif isinstance(doc_a, str):
            # If plain text string passed
            self._text_override_a = doc_a

        if isinstance(doc_b, SourceDocument):
            for i in range(self.combo_b.count()):
                d = self.combo_b.itemData(i)
                if isinstance(d, SourceDocument) and d.cite_id == doc_b.cite_id:
                    self.combo_b.setCurrentIndex(i)
                    break
        elif isinstance(doc_b, str):
            self._text_override_b = doc_b

    def _run_diff(self) -> None:
        doc_a_obj = self.combo_a.currentData() if self.combo_a.count() > 0 else None
        doc_b_obj = self.combo_b.currentData() if self.combo_b.count() > 0 else None

        text_a = getattr(self, "_text_override_a", None) or (doc_a_obj.content if isinstance(doc_a_obj, SourceDocument) else "")
        text_b = getattr(self, "_text_override_b", None) or (doc_b_obj.content if isinstance(doc_b_obj, SourceDocument) else "")

        title_a = doc_a_obj.title if isinstance(doc_a_obj, SourceDocument) else "Document A"
        title_b = doc_b_obj.title if isinstance(doc_b_obj, SourceDocument) else "Document B"

        self.title_a.setText(f"Baseline: {title_a}")
        self.title_b.setText(f"Comparison: {title_b}")

        left_rows, right_rows, added, deleted, unchanged = compute_line_diff(text_a, text_b)

        # Build styled HTML for left & right browsers
        html_left = self._render_diff_html(left_rows, is_left=True)
        html_right = self._render_diff_html(right_rows, is_left=False)

        self.browser_a.setHtml(html_left)
        self.browser_b.setHtml(html_right)

        # Update Metrics Badge
        metrics_tmpl = get_text("diff_metrics_label", self._lang)
        self.metric_badge.setText(metrics_tmpl.format(added=added, deleted=deleted, unchanged=unchanged))

    @staticmethod
    def _render_diff_html(rows: List[Dict[str, Any]], is_left: bool) -> str:
        out: List[str] = [
            "<html><head><style>",
            "body { background-color: #090D16; color: #CBD5E1; font-family: Consolas, monospace; font-size: 12px; margin: 0; padding: 4px; }",
            ".row { display: flex; white-space: pre-wrap; word-break: break-all; padding: 1px 4px; line-height: 1.4; }",
            ".num { color: #475569; width: 35px; text-align: right; user-select: none; padding-right: 8px; }",
            ".equal { background-color: transparent; color: #94A3B8; }",
            ".delete { background-color: rgba(218, 54, 51, 0.22); color: #FCA5A5; border-left: 3px solid #EF4444; }",
            ".insert { background-color: rgba(35, 134, 54, 0.22); color: #86EFAC; border-left: 3px solid #22C55E; }",
            ".replace { background-color: rgba(210, 153, 34, 0.22); color: #FDE047; border-left: 3px solid #EAB308; }",
            ".empty { background-color: #0B0E14; color: transparent; }",
            "</style></head><body>",
        ]

        for r in rows:
            tag = r["tag"]
            num_str = str(r["line_num"]) if r["line_num"] else ""
            escaped = r["text"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") or " "
            gutter = "- " if tag in ("delete", "replace") and is_left else ("+ " if tag in ("insert", "replace") and not is_left else "  ")
            out.append(f'<div class="row {tag}"><span class="num">{num_str}</span><span>{gutter}{escaped}</span></div>')

        out.append("</body></html>")
        return "".join(out)
