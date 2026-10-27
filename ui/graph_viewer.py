"""Interactive Causal Failure & Argument Graph Viewer: SVG rendering, zoom/pan controls, and text navigation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.graph_generator import extract_mermaid_blocks, render_mermaid_to_svg
from core.i18n import get_text


class CausalGraphWidget(QWidget):
    """Visualizes causal failure trees and argument flowcharts rendered from Mermaid syntax."""

    node_selected = pyqtSignal(str, str)  # (node_id, label)
    citation_clicked = pyqtSignal(QUrl)

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._current_svg: str = ""
        self._zoom_factor: float = 1.0
        self._raw_mermaid: str = ""
        self._build_ui()

    @property
    def svg_content(self) -> str:
        return self._current_svg

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.title_label = QLabel(get_text("tab_causal_graph", self._lang))
        self.title_label.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: 700;")
        toolbar.addWidget(self.title_label)

        toolbar.addStretch(1)

        self.btn_zoom_in = QToolButton(self)
        self.btn_zoom_in.setText("➕")
        self.btn_zoom_in.setToolTip(get_text("zoom_in_graph", self._lang))
        self.btn_zoom_in.clicked.connect(self._on_zoom_in)
        toolbar.addWidget(self.btn_zoom_in)

        self.btn_zoom_out = QToolButton(self)
        self.btn_zoom_out.setText("➖")
        self.btn_zoom_out.setToolTip(get_text("zoom_out_graph", self._lang))
        self.btn_zoom_out.clicked.connect(self._on_zoom_out)
        toolbar.addWidget(self.btn_zoom_out)

        self.btn_zoom_reset = QToolButton(self)
        self.btn_zoom_reset.setText("⟲")
        self.btn_zoom_reset.setToolTip(get_text("reset_graph", self._lang))
        self.btn_zoom_reset.clicked.connect(self._on_zoom_reset)
        toolbar.addWidget(self.btn_zoom_reset)

        self.btn_export = QPushButton("Export SVG" if self._lang == "en" else "SVG 내보내기", self)
        self.btn_export.setStyleSheet("background-color: #1E293B; color: #F1F5F9; border-radius: 4px; padding: 4px 10px; font-size: 11px;")
        self.btn_export.clicked.connect(self._on_export_svg)
        toolbar.addWidget(self.btn_export)

        layout.addLayout(toolbar)

        # SVG Display Viewer
        self.viewer = QTextBrowser(self)
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setOpenLinks(False)
        self.viewer.anchorClicked.connect(self._on_anchor_clicked)
        self.viewer.setStyleSheet(
            "QTextBrowser { background-color: #0B0F19; border: 1px solid #1E293B; border-radius: 6px; padding: 10px; }"
        )
        layout.addWidget(self.viewer, stretch=1)

    def set_markdown_report(self, markdown_text: str) -> None:
        """Extract and render Mermaid diagram from synthesis report text."""
        blocks = extract_mermaid_blocks(markdown_text)
        if blocks:
            self._raw_mermaid = blocks[0]
            self._current_svg = render_mermaid_to_svg(self._raw_mermaid)
        else:
            self._raw_mermaid = ""
            self._current_svg = (
                '<svg xmlns="http://www.w3.org/2005/svg" width="600" height="120">'
                '<rect width="100%" height="100%" fill="#0B0F19"/>'
                '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#94A3B8" font-size="13">'
                + ("No causal graph syntax detected in report. Generate or update synthesis." if self._lang == "en" else "보고서에서 인과 다이어그램 구문을 찾을 수 없습니다.") +
                '</text></svg>'
            )
        self._render_svg()

    def _render_svg(self) -> None:
        if not self._current_svg:
            self.viewer.clear()
            return
        # Wrap SVG in a centering container
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><style>body {{ background-color: #0B0F19; margin: 0; padding: 10px; text-align: center; }}</style></head>
        <body>
        <div style="transform: scale({self._zoom_factor}); transform-origin: top center; display: inline-block;">
        {self._current_svg}
        </div>
        </body>
        </html>
        """
        self.viewer.setHtml(html)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        url_str = url.toString()
        if url_str.startswith("node:"):
            node_id = url_str[5:]
            self.node_selected.emit(node_id, node_id)
        elif url_str.startswith("cite:"):
            self.citation_clicked.emit(url)
        else:
            QDesktopServices.openUrl(url)

    def _on_zoom_in(self) -> None:
        self._zoom_factor = min(3.0, self._zoom_factor + 0.15)
        self._render_svg()

    def _on_zoom_out(self) -> None:
        self._zoom_factor = max(0.4, self._zoom_factor - 0.15)
        self._render_svg()

    def _on_zoom_reset(self) -> None:
        self._zoom_factor = 1.0
        self._render_svg()

    def _on_export_svg(self) -> None:
        if not self._current_svg:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Causal Graph SVG" if self._lang == "en" else "인과 다이어그램 SVG 저장",
            "causal_graph.svg",
            "Scalable Vector Graphics (*.svg)",
        )
        if file_path:
            Path(file_path).write_text(self._current_svg, encoding="utf-8")

    def retranslate_ui(self, lang: str) -> None:
        self._lang = lang
        self.title_label.setText(get_text("tab_causal_graph", lang))
        self.btn_zoom_in.setToolTip(get_text("zoom_in_graph", lang))
        self.btn_zoom_out.setToolTip(get_text("zoom_out_graph", lang))
        self.btn_zoom_reset.setToolTip(get_text("reset_graph", lang))
        self.btn_export.setText("Export SVG" if lang == "en" else "SVG 내보내기")
