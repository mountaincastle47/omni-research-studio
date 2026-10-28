"""Interactive Causal Failure & Argument Graph Viewer: QGraphicsView rendering with discrete nodes, directed edges, zoom/pan controls."""

from __future__ import annotations

import html
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRectF, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:
    try:
        from PySide6.QtOpenGLWidgets import QOpenGLWidget
    except ImportError:
        QOpenGLWidget = None

from core.graph_generator import (
    MermaidEdge,
    MermaidNode,
    ParsedMermaidGraph,
    extract_mermaid_blocks,
    parse_mermaid_code,
    render_mermaid_to_svg,
)
from core.i18n import get_text


def intersect_card(cx: float, cy: float, hw: float, hh: float, dx: float, dy: float) -> QPointF:
    """Calculate intersection point of a ray from center (cx, cy) in direction (dx, dy) with rectangle [-hw, -hh, hw, hh]."""
    if dx == 0 and dy == 0:
        return QPointF(cx, cy)
    scale_x = abs(hw / dx) if dx != 0 else float("inf")
    scale_y = abs(hh / dy) if dy != 0 else float("inf")
    scale = min(scale_x, scale_y)
    return QPointF(cx + dx * scale, cy + dy * scale)


class _CausalNodeGraphicsItem(QGraphicsItem):
    """Discrete interactive causal node card rendering rounded dark pill with border and wrapped text."""

    def __init__(
        self,
        node_id: str,
        label: str,
        width: float = 240.0,
        height: float = 72.0,
        parent_widget: Optional[CausalGraphWidget] = None,
    ) -> None:
        super().__init__()
        self.node_id = node_id
        self.label = label
        self.width = width
        self.height = height
        self.parent_widget = parent_widget
        self.is_hovered = False

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"[{node_id}] {label}")

    def boundingRect(self) -> QRectF:
        return QRectF(-self.width / 2.0, -self.height / 2.0, self.width, self.height)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(self.boundingRect(), 10.0, 10.0)
        return path

    def paint(self, painter: QPainter, option: Any, widget: Optional[QWidget] = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.boundingRect()
        path = QPainterPath()
        path.addRoundedRect(rect, 10.0, 10.0)

        # Background fill
        bg_color = QColor("#1E293B") if self.is_hovered else QColor("#0F172A")
        painter.fillPath(path, QBrush(bg_color))

        # Border
        border_color = QColor("#7DD3FC") if self.is_hovered else QColor("#38BDF8")
        pen_width = 2.4 if self.is_hovered else 1.8
        painter.strokePath(path, QPen(border_color, pen_width))

        # Text rendering with padding and word wrap
        inner_rect = rect.adjusted(12.0, 8.0, -12.0, -8.0)
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.setPen(QPen(QColor("#F8FAFC")))
        painter.drawText(
            inner_rect,
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            self.label,
        )

    def hoverEnterEvent(self, event: Any) -> None:
        self.is_hovered = True
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: Any) -> None:
        self.is_hovered = False
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: Any) -> None:
        if self.parent_widget:
            self.parent_widget.node_selected.emit(self.node_id, self.label)
            # Check for bracketed citation [N] in label
            match = re.search(r"\[(\d+)\]", self.label)
            if match:
                self.parent_widget.citation_clicked.emit(QUrl(f"cite:{match.group(1)}"))
        super().mousePressEvent(event)


class _CausalEdgeGraphicsItem(QGraphicsItem):
    """Directed edge arrow connecting source and target causal cards with boundary snapping."""

    def __init__(
        self,
        source_item: _CausalNodeGraphicsItem,
        target_item: _CausalNodeGraphicsItem,
        relation: str = "",
        arrow: bool = True,
    ) -> None:
        super().__init__()
        self.source_item = source_item
        self.target_item = target_item
        self.relation = relation
        self.arrow = arrow
        self.setZValue(1.0)

    def boundingRect(self) -> QRectF:
        p1 = self.source_item.pos()
        p2 = self.target_item.pos()
        return QRectF(p1, p2).normalized().adjusted(-50.0, -50.0, 50.0, 50.0)

    def paint(self, painter: QPainter, option: Any, widget: Optional[QWidget] = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        p1 = self.source_item.pos()
        p2 = self.target_item.pos()

        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        dist = math.hypot(dx, dy)
        if dist < 1.0:
            return

        start_pt = intersect_card(
            p1.x(), p1.y(),
            self.source_item.width / 2.0, self.source_item.height / 2.0,
            dx, dy,
        )
        end_pt = intersect_card(
            p2.x(), p2.y(),
            self.target_item.width / 2.0, self.target_item.height / 2.0,
            -dx, -dy,
        )

        edge_color = QColor("#38BDF8")
        pen = QPen(edge_color, 2.0, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawLine(start_pt, end_pt)

        # Draw directed arrowhead at target card boundary
        if self.arrow:
            theta = math.atan2(end_pt.y() - start_pt.y(), end_pt.x() - start_pt.x())
            arrow_len = 12.0
            arrow_width = 6.0

            arrow_poly = QPolygonF([
                end_pt,
                QPointF(
                    end_pt.x() - arrow_len * math.cos(theta) + arrow_width * math.sin(theta),
                    end_pt.y() - arrow_len * math.sin(theta) - arrow_width * math.cos(theta),
                ),
                QPointF(
                    end_pt.x() - arrow_len * math.cos(theta) - arrow_width * math.sin(theta),
                    end_pt.y() - arrow_len * math.sin(theta) + arrow_width * math.cos(theta),
                ),
            ])
            painter.setBrush(QBrush(edge_color))
            painter.drawPolygon(arrow_poly)

        # Draw relation badge at midpoint
        if self.relation:
            mid_x = (start_pt.x() + end_pt.x()) / 2.0
            mid_y = (start_pt.y() + end_pt.y()) / 2.0

            font = QFont("Consolas", 8, QFont.Weight.Bold)
            painter.setFont(font)
            fm = QFontMetrics(font)
            text_width = fm.horizontalAdvance(self.relation)
            badge_rect = QRectF(mid_x - text_width / 2.0 - 6, mid_y - 10, text_width + 12, 20)

            badge_path = QPainterPath()
            badge_path.addRoundedRect(badge_rect, 4.0, 4.0)
            painter.fillPath(badge_path, QBrush(QColor("#070A10")))
            painter.strokePath(badge_path, QPen(QColor("#334155"), 1.2))

            painter.setPen(QPen(QColor("#94A3B8")))
            painter.drawText(badge_rect, int(Qt.AlignmentFlag.AlignCenter), self.relation)


class CausalGraphView(QGraphicsView):
    """OpenGL-accelerated QGraphicsView with cursor-centered wheel zoom and scrollbar elimination."""

    def __init__(self, scene: QGraphicsScene, parent: Optional[QWidget] = None) -> None:
        super().__init__(scene, parent)
        if QOpenGLWidget is not None:
            try:
                self.setViewport(QOpenGLWidget())
            except Exception:
                pass
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setStyleSheet("QGraphicsView { border: 1px solid #1E293B; border-radius: 6px; background-color: #070A10; }")

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            zoom_in = event.angleDelta().y() > 0
            factor = 1.15 if zoom_in else (1.0 / 1.15)
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)


class CausalGraphWidget(QWidget):
    """Visualizes causal failure trees and argument flowcharts with discrete interactive QGraphicsView nodes and directed edges."""

    node_selected = pyqtSignal(str, str)  # (node_id, label)
    citation_clicked = pyqtSignal(QUrl)

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._current_svg: str = ""
        self._raw_mermaid: str = ""
        self._parsed_graph: Optional[ParsedMermaidGraph] = None

        self._build_ui()

    @property
    def svg_content(self) -> str:
        if self._current_svg:
            return self._current_svg
        if self._raw_mermaid:
            return render_mermaid_to_svg(self._raw_mermaid)
        return ""

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
        self.btn_export.setStyleSheet(
            "background-color: #1E293B; color: #F1F5F9; border-radius: 4px; padding: 4px 10px; font-size: 11px;"
        )
        self.btn_export.clicked.connect(self._on_export_svg)
        toolbar.addWidget(self.btn_export)

        layout.addLayout(toolbar)

        # QGraphicsScene & QGraphicsView for discrete node & edge graph
        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QBrush(QColor("#070A10")))

        self.view = CausalGraphView(self.scene, self)
        layout.addWidget(self.view, stretch=1)

        self._show_empty_state()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            zoom_in = event.angleDelta().y() > 0
            factor = 1.15 if zoom_in else (1.0 / 1.15)
            self.view.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def load_precomputed_layout(self, layout_data: Optional[Dict[str, Any]]) -> None:
        """Instantly load precalculated causal graph layout without running topology math on GUI thread."""
        if not layout_data or not layout_data.get("nodes"):
            self._show_empty_state()
            return

        self._raw_mermaid = layout_data.get("raw_mermaid", "")
        self.scene.clear()

        node_items: Dict[str, _CausalNodeGraphicsItem] = {}
        for n in layout_data["nodes"]:
            nid = n["id"]
            item = _CausalNodeGraphicsItem(nid, n.get("label", nid), parent_widget=self)
            item.setPos(n.get("x", 0.0), n.get("y", 0.0))
            node_items[nid] = item
            self.scene.addItem(item)

        for edge in layout_data.get("edges", []):
            src_id = edge.get("source")
            tgt_id = edge.get("target")
            if src_id in node_items and tgt_id in node_items:
                edge_item = _CausalEdgeGraphicsItem(
                    source_item=node_items[src_id],
                    target_item=node_items[tgt_id],
                    relation=edge.get("label", ""),
                    arrow=edge.get("arrow", "-->"),
                )
                self.scene.addItem(edge_item)

        self._fit_and_clamp_viewport()

    def _fit_and_clamp_viewport(self) -> None:
        """Fit scene to viewport with 60px margins and clamp scale to readable 0.85x-1.0x bounds."""
        rect = self.scene.itemsBoundingRect().adjusted(-60, -60, 60, 60)
        if rect.isValid() and not rect.isEmpty():
            self.scene.setSceneRect(rect)
            self.view.resetTransform()
            self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            current_scale = self.view.transform().m11()
            if current_scale < 0.85:
                self.view.resetTransform()
                self.view.scale(0.85, 0.85)
            elif current_scale > 1.15:
                self.view.resetTransform()
                self.view.scale(1.0, 1.0)
            self.view.centerOn(rect.center())

    def _show_empty_state(self) -> None:
        self.scene.clear()
        msg = (
            "No causal graph syntax detected in report. Generate or update synthesis."
            if self._lang == "en"
            else "보고서에서 인과 다이어그램 구문을 찾을 수 없습니다."
        )
        placeholder = self.scene.addSimpleText(msg)
        placeholder.setFont(QFont("Segoe UI", 12))
        placeholder.setBrush(QBrush(QColor("#64748B")))
        bounds = placeholder.boundingRect()
        placeholder.setPos(-bounds.width() / 2.0, -bounds.height() / 2.0)
        self.scene.setSceneRect(placeholder.boundingRect().adjusted(-80, -80, 80, 80))

    def set_markdown_report(self, markdown_text: str) -> None:
        """Extract and render discrete causal failure diagram from synthesis report text."""
        blocks = extract_mermaid_blocks(markdown_text)
        if blocks:
            self._raw_mermaid = blocks[0]
            self._current_svg = render_mermaid_to_svg(self._raw_mermaid)
            self._parsed_graph = parse_mermaid_code(self._raw_mermaid)
            self._render_graph()
        else:
            self._raw_mermaid = ""
            self._current_svg = ""
            self._parsed_graph = None
            self._show_empty_state()

    def _render_graph(self) -> None:
        """Compute discrete node and edge layout and populate QGraphicsScene."""
        if not self._parsed_graph or not self._parsed_graph.nodes:
            self._show_empty_state()
            return

        self.scene.clear()
        graph = self._parsed_graph

        node_items: Dict[str, _CausalNodeGraphicsItem] = {}
        for nid, node in graph.nodes.items():
            item = _CausalNodeGraphicsItem(nid, node.label or nid, parent_widget=self)
            node_items[nid] = item
            self.scene.addItem(item)

        # Adjacency and in-degree mapping
        children_map: Dict[str, List[str]] = {nid: [] for nid in graph.nodes}
        in_degree: Dict[str, int] = {nid: 0 for nid in graph.nodes}
        for edge in graph.edges:
            if edge.source_id in graph.nodes and edge.target_id in graph.nodes:
                children_map[edge.source_id].append(edge.target_id)
                in_degree[edge.target_id] += 1

        # Layer assignment (Topological BFS)
        layers: List[List[str]] = []
        roots = [nid for nid, deg in in_degree.items() if deg == 0]
        if not roots:
            roots = [list(graph.nodes.keys())[0]]

        visited = set(roots)
        layers.append(roots)

        while True:
            next_layer: List[str] = []
            for nid in layers[-1]:
                for ch in children_map.get(nid, []):
                    if ch not in visited:
                        visited.add(ch)
                        next_layer.append(ch)
            if not next_layer:
                break
            layers.append(next_layer)

        # Append any unvisited nodes
        unvisited = [nid for nid in graph.nodes if nid not in visited]
        if unvisited:
            layers.append(unvisited)

        # Automatic layout coordinates enforcing minimum 150px horizontal and 100px vertical separation
        is_horizontal = graph.direction in ("LR", "RL")
        node_w = 240.0
        node_h = 72.0
        h_sep = 150.0  # Horizontal separation (exceeds 120px mandate)
        v_sep = 100.0  # Vertical separation (exceeds 80px mandate)

        for l_idx, layer in enumerate(layers):
            count = len(layer)
            if not is_horizontal:
                # Top-Down: each layer is a horizontal row
                total_w = count * node_w + (count - 1) * h_sep
                start_x = -total_w / 2.0 + node_w / 2.0
                y = l_idx * (node_h + v_sep)
                for n_idx, nid in enumerate(layer):
                    x = start_x + n_idx * (node_w + h_sep)
                    node_items[nid].setPos(x, y)
            else:
                # Left-to-Right: each layer is a vertical column
                total_h = count * node_h + (count - 1) * v_sep
                start_y = -total_h / 2.0 + node_h / 2.0
                x = l_idx * (node_w + h_sep)
                for n_idx, nid in enumerate(layer):
                    y = start_y + n_idx * (node_h + v_sep)
                    node_items[nid].setPos(x, y)

        # Add directed edge items
        for edge in graph.edges:
            if edge.source_id in node_items and edge.target_id in node_items:
                src_item = node_items[edge.source_id]
                tgt_item = node_items[edge.target_id]
                edge_item = _CausalEdgeGraphicsItem(
                    source_item=src_item,
                    target_item=tgt_item,
                    relation=edge.label,
                    arrow=edge.arrow,
                )
                self.scene.addItem(edge_item)

        # Update scene bounds and fit into view
        self._fit_and_clamp_viewport()

    def _on_zoom_in(self) -> None:
        self.view.scale(1.2, 1.2)

    def _on_zoom_out(self) -> None:
        self.view.scale(1.0 / 1.2, 1.0 / 1.2)

    def _on_zoom_reset(self) -> None:
        self._fit_and_clamp_viewport()

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """Programmatic anchor click handler for backward compatibility."""
        url_str = url.toString()
        if url_str.startswith("node:"):
            node_id = url_str[5:]
            self.node_selected.emit(node_id, node_id)
        elif url_str.startswith("cite:"):
            self.citation_clicked.emit(url)
        else:
            QDesktopServices.openUrl(url)

    def _on_export_svg(self) -> None:
        if not self._current_svg and self._raw_mermaid:
            self._current_svg = render_mermaid_to_svg(self._raw_mermaid)

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


def compute_causal_layout_from_markdown(markdown_text: str) -> Optional[Dict[str, Any]]:
    """Compute causal graph layout coordinates off-main-thread in background worker."""
    if not markdown_text or not markdown_text.strip():
        return None

    blocks = extract_mermaid_blocks(markdown_text)
    if not blocks:
        return None

    raw_mermaid = blocks[0]
    graph = parse_mermaid_code(raw_mermaid)
    if not graph or not graph.nodes:
        return None

    children_map: Dict[str, List[str]] = {nid: [] for nid in graph.nodes}
    in_degree: Dict[str, int] = {nid: 0 for nid in graph.nodes}
    for edge in graph.edges:
        if edge.source_id in graph.nodes and edge.target_id in graph.nodes:
            children_map[edge.source_id].append(edge.target_id)
            in_degree[edge.target_id] += 1

    layers: List[List[str]] = []
    roots = [nid for nid, deg in in_degree.items() if deg == 0]
    if not roots:
        roots = [list(graph.nodes.keys())[0]]

    visited = set(roots)
    layers.append(roots)

    while True:
        next_layer: List[str] = []
        for nid in layers[-1]:
            for ch in children_map.get(nid, []):
                if ch not in visited:
                    visited.add(ch)
                    next_layer.append(ch)
        if not next_layer:
            break
        layers.append(next_layer)

    unvisited = [nid for nid in graph.nodes if nid not in visited]
    if unvisited:
        layers.append(unvisited)

    is_horizontal = graph.direction in ("LR", "RL")
    node_w = 240.0
    node_h = 72.0
    h_sep = 150.0
    v_sep = 100.0

    node_positions: Dict[str, Tuple[float, float]] = {}
    for l_idx, layer in enumerate(layers):
        count = len(layer)
        if not is_horizontal:
            total_w = count * node_w + (count - 1) * h_sep
            start_x = -total_w / 2.0 + node_w / 2.0
            y = l_idx * (node_h + v_sep)
            for n_idx, nid in enumerate(layer):
                x = start_x + n_idx * (node_w + h_sep)
                node_positions[nid] = (round(x, 1), round(y, 1))
        else:
            total_h = count * node_h + (count - 1) * v_sep
            start_y = -total_h / 2.0 + node_h / 2.0
            x = l_idx * (node_w + h_sep)
            for n_idx, nid in enumerate(layer):
                y = start_y + n_idx * (node_h + v_sep)
                node_positions[nid] = (round(x, 1), round(y, 1))

    nodes_data = [
        {
            "id": nid,
            "label": node.label or nid,
            "x": node_positions[nid][0],
            "y": node_positions[nid][1],
        }
        for nid, node in graph.nodes.items()
        if nid in node_positions
    ]
    edges_data = [
        {
            "source": edge.source_id,
            "target": edge.target_id,
            "label": edge.label,
            "arrow": edge.arrow,
        }
        for edge in graph.edges
    ]

    return {
        "raw_mermaid": raw_mermaid,
        "nodes": nodes_data,
        "edges": edges_data,
    }

