"""Interactive Causal Failure & Argument Graph Viewer: QGraphicsView rendering with discrete nodes, directed edges, zoom/pan controls."""

from __future__ import annotations

import html
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QUrl, pyqtSignal
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
    sanitize_node_label,
)
from core.i18n import get_text


def estimate_node_dimensions(label: str, min_w: float = 240.0, max_w: float = 280.0, min_h: float = 72.0) -> Tuple[float, float]:
    """Calculate dynamic card dimensions based on font metrics or line-count heuristics."""
    clean = sanitize_node_label(label)
    try:
        from PyQt6.QtGui import QFont, QFontMetrics
        from PyQt6.QtCore import QRect, Qt
        font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        fm = QFontMetrics(font)
        text_rect = fm.boundingRect(
            QRect(0, 0, int(max_w - 24), 0),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            clean,
        )
        w = max(min_w, min(max_w, float(text_rect.width() + 32.0)))
        h = max(min_h, float(text_rect.height() + 28.0))
        return round(w, 1), round(h, 1)
    except Exception:
        lines = clean.split("\n")
        est_lines = sum(max(1, math.ceil(len(l) / 26.0)) for l in lines)
        h = max(min_h, est_lines * 22.0 + 28.0)
        return min_w, round(h, 1)


def intersect_card(cx: float, cy: float, hw: float, hh: float, dx: float, dy: float) -> QPointF:
    """Calculate intersection point of a ray from center (cx, cy) in direction (dx, dy) with rectangle [-hw, -hh, hw, hh]."""
    if dx == 0 and dy == 0:
        return QPointF(cx, cy)
    scale_x = abs(hw / dx) if dx != 0 else float("inf")
    scale_y = abs(hh / dy) if dy != 0 else float("inf")
    scale = min(scale_x, scale_y)
    return QPointF(cx + dx * scale, cy + dy * scale)


class _CausalNodeGraphicsItem(QGraphicsItem):
    """Discrete interactive causal node card rendering rounded dark pill with border and dynamically wrapped text."""

    def __init__(
        self,
        node_id: str,
        label: str,
        width: Optional[float] = None,
        height: Optional[float] = None,
        parent_widget: Optional[CausalGraphWidget] = None,
    ) -> None:
        super().__init__()
        self.node_id = node_id
        self.clean_label = sanitize_node_label(label) or node_id
        self.label = self.clean_label
        self.parent_widget = parent_widget
        self.is_hovered = False

        self.font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        fm = QFontMetrics(self.font)

        min_w = 240.0
        max_w = 280.0
        min_h = 72.0

        # Measure text bounding rect with word wrap within (max_w - 24)
        from PyQt6.QtCore import QRect
        text_rect = fm.boundingRect(
            QRect(0, 0, int(max_w - 24), 0),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            self.clean_label,
        )

        computed_w = max(min_w, min(max_w, float(text_rect.width() + 32.0)))
        computed_h = max(min_h, float(text_rect.height() + 28.0))

        self.width = max(computed_w, float(width)) if width is not None else computed_w
        self.height = max(computed_h, float(height)) if height is not None else computed_h

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setZValue(2.0)  # Rendered at Z=2.0 (above edge lines at Z=1.0)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"[{node_id}] {self.clean_label}")

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

        # Text rendering centered vertically and horizontally within inner box with full margin clearance
        inner_rect = rect.adjusted(12.0, 10.0, -12.0, -10.0)
        painter.setFont(self.font)
        painter.setPen(QPen(QColor("#F8FAFC")))
        painter.drawText(
            inner_rect,
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            self.clean_label,
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

    def update_label(self, new_label: str) -> None:
        """Update node text, recompute dimensions using QFontMetrics, and refresh geometry without moving position."""
        self.prepareGeometryChange()
        self.clean_label = sanitize_node_label(new_label) or self.node_id
        self.label = self.clean_label
        self.setToolTip(f"[{self.node_id}] {self.clean_label}")
        min_w = 240.0
        max_w = 280.0
        min_h = 72.0
        from PyQt6.QtCore import QRect
        fm = QFontMetrics(self.font)
        text_rect = fm.boundingRect(
            QRect(0, 0, int(max_w - 24), 0),
            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
            self.clean_label,
        )
        self.width = max(min_w, min(max_w, float(text_rect.width() + 32.0)))
        self.height = max(min_h, float(text_rect.height() + 28.0))
        self.update()

    def mousePressEvent(self, event: Any) -> None:
        if self.parent_widget:
            self.parent_widget.node_selected.emit(self.node_id, self.label)
            # Check for bracketed citation [N] in label
            match = re.search(r"\[(\d+)\]", self.label)
            if match:
                self.parent_widget.citation_clicked.emit(QUrl(f"cite:{match.group(1)}"))
        super().mousePressEvent(event)


class _CausalEdgeBadgeItem(QGraphicsItem):
    """Opaque pill badge displaying word-wrapped edge relation text above directed edge lines."""

    def __init__(self, edge_item: _CausalEdgeGraphicsItem, relation: str) -> None:
        super().__init__()
        self.edge_item = edge_item
        self.relation = relation.strip()
        self.is_edge_label = True
        self.is_edge_badge = True
        self.setZValue(3.0)  # Rendered strictly above lines (Z=1.0) and node cards (Z=2.0)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

        self.font = QFont("Consolas", 8, QFont.Weight.Bold)
        self.max_width = 160.0  # Constraint between 140px and 180px
        self.h_padding = 16.0
        self.v_padding = 10.0
        self.width = 60.0
        self.height = 24.0
        self.rect = QRectF(0.0, 0.0, self.width, self.height)
        self._recompute_dimensions()

    def _recompute_dimensions(self) -> None:
        fm = QFontMetrics(self.font)
        max_text_w = max(40, int(self.max_width - self.h_padding))
        flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere)
        text_box = fm.boundingRect(QRect(0, 0, max_text_w, 0), flags, self.relation)
        self.width = max(50.0, min(self.max_width, float(text_box.width() + self.h_padding)))
        self.height = max(22.0, float(text_box.height() + self.v_padding))
        cx = self.rect.center().x() if not self.rect.isNull() else 0.0
        cy = self.rect.center().y() if not self.rect.isNull() else 0.0
        self.rect = QRectF(cx - self.width / 2.0, cy - self.height / 2.0, self.width, self.height)

    def update_geometry(self, center_x: float, center_y: float) -> None:
        """Position badge centered at (center_x, center_y)."""
        self.prepareGeometryChange()
        self.rect = QRectF(
            center_x - self.width / 2.0,
            center_y - self.height / 2.0,
            self.width,
            self.height,
        )
        self.update()

    def move_by(self, dx: float, dy: float) -> None:
        """Translate badge by (dx, dy) for collision avoidance relaxation."""
        self.prepareGeometryChange()
        self.rect.translate(dx, dy)
        self.update()

    def update_text(self, new_relation: str) -> None:
        """Update badge relation label and recompute wrapped dimensions."""
        self.prepareGeometryChange()
        self.relation = new_relation.strip()
        self._recompute_dimensions()
        self.update()

    def boundingRect(self) -> QRectF:
        return self.rect

    def sceneBoundingRect(self) -> QRectF:
        return self.rect

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(self.rect, 4.0, 4.0)
        return path

    def paint(self, painter: QPainter, option: Any, widget: Optional[QWidget] = None) -> None:
        if not self.relation or self.rect.isEmpty():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(self.rect, 4.0, 4.0)

        # 1. Dark opaque background fill matching scene palette
        painter.fillPath(path, QBrush(QColor("#070A10")))
        # 2. Subtle slate border
        painter.strokePath(path, QPen(QColor("#334155"), 1.2))

        # 3. Wrapped label text centered with padding clearance
        painter.setFont(self.font)
        painter.setPen(QPen(QColor("#CBD5E1")))
        inner_rect = self.rect.adjusted(6.0, 4.0, -6.0, -4.0)
        flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere)
        painter.drawText(inner_rect, flags, self.relation)


_CausalEdgeLabelGraphicsItem = _CausalEdgeBadgeItem


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
        self.badge_fraction: float = 0.50
        self.badge_item: Optional[_CausalEdgeBadgeItem] = (
            _CausalEdgeBadgeItem(self, self.relation) if self.relation.strip() else None
        )

    @property
    def badge_rect(self) -> QRectF:
        if self.badge_item:
            return self.badge_item.boundingRect()
        return QRectF()

    def get_badge_rect(self) -> QRectF:
        return self.badge_rect

    def update_relation(self, new_relation: str) -> None:
        """Update edge relation badge text and trigger repaint."""
        self.prepareGeometryChange()
        self.relation = new_relation
        clean_rel = new_relation.strip()
        if clean_rel:
            if self.badge_item is None:
                self.badge_item = _CausalEdgeBadgeItem(self, clean_rel)
                if self.scene():
                    self.scene().addItem(self.badge_item)
            else:
                self.badge_item.update_text(clean_rel)
        elif self.badge_item is not None:
            if self.scene():
                self.scene().removeItem(self.badge_item)
            self.badge_item = None
        self.update()

    def boundingRect(self) -> QRectF:
        p1 = self.source_item.pos()
        p2 = self.target_item.pos()
        base_rect = QRectF(p1, p2).normalized().adjusted(-30.0, -30.0, 30.0, 30.0)
        if self.badge_item and not self.badge_item.boundingRect().isEmpty():
            return base_rect.united(self.badge_item.boundingRect())
        return base_rect

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
        self._node_items: Dict[str, _CausalNodeGraphicsItem] = {}
        self._edge_items: List[_CausalEdgeGraphicsItem] = []

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
        self.btn_zoom_in.setToolTip(get_text("tooltip_zoom_in", self._lang))
        self.btn_zoom_in.clicked.connect(self._on_zoom_in)
        toolbar.addWidget(self.btn_zoom_in)

        self.btn_zoom_out = QToolButton(self)
        self.btn_zoom_out.setText("➖")
        self.btn_zoom_out.setToolTip(get_text("tooltip_zoom_out", self._lang))
        self.btn_zoom_out.clicked.connect(self._on_zoom_out)
        toolbar.addWidget(self.btn_zoom_out)

        self.btn_zoom_reset = QToolButton(self)
        self.btn_zoom_reset.setText("⟲")
        self.btn_zoom_reset.setToolTip(get_text("reset_graph", self._lang))
        self.btn_zoom_reset.clicked.connect(self._on_zoom_reset)
        toolbar.addWidget(self.btn_zoom_reset)

        self.btn_export_png = QPushButton("Export PNG" if self._lang == "en" else "PNG 내보내기", self)
        self.btn_export_png.setToolTip(get_text("tooltip_export_png", self._lang))
        self.btn_export_png.setStyleSheet(
            "background-color: #1E293B; color: #F1F5F9; border-radius: 4px; padding: 4px 10px; font-size: 11px;"
        )
        self.btn_export_png.clicked.connect(self._on_export_png)
        toolbar.addWidget(self.btn_export_png)

        self.btn_export_svg = QPushButton("Export SVG" if self._lang == "en" else "SVG 내보내기", self)
        self.btn_export_svg.setToolTip(get_text("tooltip_export_svg", self._lang))
        self.btn_export_svg.setStyleSheet(
            "background-color: #1E293B; color: #F1F5F9; border-radius: 4px; padding: 4px 10px; font-size: 11px;"
        )
        self.btn_export_svg.clicked.connect(self._on_export_svg)
        toolbar.addWidget(self.btn_export_svg)
        self.btn_export = self.btn_export_svg

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
        self._node_items.clear()
        self._edge_items.clear()

        for n in layout_data["nodes"]:
            nid = n["id"]
            item = _CausalNodeGraphicsItem(
                nid,
                n.get("label", nid),
                width=n.get("width"),
                height=n.get("height"),
                parent_widget=self,
            )
            item.setPos(n.get("x", 0.0), n.get("y", 0.0))
            self._node_items[nid] = item
            self.scene.addItem(item)

        for edge in layout_data.get("edges", []):
            src_id = edge.get("source")
            tgt_id = edge.get("target")
            if src_id in self._node_items and tgt_id in self._node_items:
                edge_item = _CausalEdgeGraphicsItem(
                    source_item=self._node_items[src_id],
                    target_item=self._node_items[tgt_id],
                    relation=edge.get("label", ""),
                    arrow=edge.get("arrow", "-->"),
                )
                self.scene.addItem(edge_item)
                if edge_item.badge_item:
                    self.scene.addItem(edge_item.badge_item)
                self._edge_items.append(edge_item)

        self._relayout_edge_badges()
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
        self._node_items.clear()
        self._edge_items.clear()
        graph = self._parsed_graph

        for nid, node in graph.nodes.items():
            item = _CausalNodeGraphicsItem(nid, node.label or nid, parent_widget=self)
            self._node_items[nid] = item
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
        h_sep = 150.0  # Horizontal separation (exceeds 120px mandate)
        v_sep = 100.0  # Vertical separation (exceeds 80px mandate)

        if not is_horizontal:
            # Top-Down layout: layer by layer with cumulative row height and centered items
            current_y = 0.0
            for layer in layers:
                layer_h = max((self._node_items[nid].height for nid in layer), default=72.0)
                row_widths = [self._node_items[nid].width for nid in layer]
                total_w = sum(row_widths) + (len(layer) - 1) * h_sep
                cur_x = -total_w / 2.0
                for nid in layer:
                    w = self._node_items[nid].width
                    node_x = cur_x + w / 2.0
                    node_y = current_y + layer_h / 2.0
                    self._node_items[nid].setPos(round(node_x, 1), round(node_y, 1))
                    cur_x += w + h_sep
                current_y += layer_h + v_sep
        else:
            # Left-to-Right layout: column by column with cumulative column width and centered items
            current_x = 0.0
            for layer in layers:
                layer_w = max((self._node_items[nid].width for nid in layer), default=240.0)
                col_heights = [self._node_items[nid].height for nid in layer]
                total_h = sum(col_heights) + (len(layer) - 1) * v_sep
                cur_y = -total_h / 2.0
                for nid in layer:
                    h = self._node_items[nid].height
                    node_x = current_x + layer_w / 2.0
                    node_y = cur_y + h / 2.0
                    self._node_items[nid].setPos(round(node_x, 1), round(node_y, 1))
                    cur_y += h + v_sep
                current_x += layer_w + h_sep

        # Add directed edge items and their badge items
        for edge in graph.edges:
            if edge.source_id in self._node_items and edge.target_id in self._node_items:
                src_item = self._node_items[edge.source_id]
                tgt_item = self._node_items[edge.target_id]
                edge_item = _CausalEdgeGraphicsItem(
                    source_item=src_item,
                    target_item=tgt_item,
                    relation=edge.label,
                    arrow=edge.arrow,
                )
                self.scene.addItem(edge_item)
                if edge_item.badge_item:
                    self.scene.addItem(edge_item.badge_item)
                self._edge_items.append(edge_item)

        self._relayout_edge_badges()
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

    def _on_export_png(self) -> None:
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Causal Graph" if self._lang == "en" else "인과 다이어그램 저장",
            "causal_graph.png",
            "High-Resolution PNG (*.png);;Scalable Vector Graphics (*.svg)",
        )
        if file_path:
            if file_path.lower().endswith(".svg") or "SVG" in selected_filter:
                if not file_path.lower().endswith(".svg"):
                    file_path = re.sub(r"\.png$", "", file_path, flags=re.I) + ".svg"
                self.export_to_svg(file_path)
            else:
                if not file_path.lower().endswith(".png"):
                    file_path = re.sub(r"\.svg$", "", file_path, flags=re.I) + ".png"
                self.export_image(file_path)

    def _on_export_svg(self) -> None:
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Causal Graph" if self._lang == "en" else "인과 다이어그램 저장",
            "causal_graph.svg",
            "Scalable Vector Graphics (*.svg);;High-Resolution PNG (*.png)",
        )
        if file_path:
            if file_path.lower().endswith(".png") or "PNG" in selected_filter:
                if not file_path.lower().endswith(".png"):
                    file_path = re.sub(r"\.svg$", "", file_path, flags=re.I) + ".png"
                self.export_image(file_path)
            else:
                if not file_path.lower().endswith(".svg"):
                    file_path = re.sub(r"\.png$", "", file_path, flags=re.I) + ".svg"
                self.export_to_svg(file_path)

    def export_to_svg(self, file_path: str | Path) -> Path:
        """Export causal graph to standard-compliant scalable vector SVG 1.1 with positive (0,0) origin and accurate coordinate scaling."""
        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        source_rect = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        if source_rect.isNull() or source_rect.isEmpty() or source_rect.width() < 10 or source_rect.height() < 10:
            source_rect = QRectF(-400, -300, 800, 600)

        width = max(100.0, source_rect.width())
        height = max(100.0, source_rect.height())
        target_rect = QRectF(0.0, 0.0, width, height)
        w = int(round(width))
        h = int(round(height))

        try:
            from PyQt6.QtSvg import QSvgGenerator
            from core.graph_generator import normalize_svg_xml

            generator = QSvgGenerator()
            generator.setFileName(str(target))
            generator.setSize(QSize(w, h))
            generator.setViewBox(target_rect)
            generator.setTitle("Causal Graph")
            generator.setDescription("Generated by OmniResearch Studio")

            painter = QPainter()
            if painter.begin(generator):
                try:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                    # Fill background across target_rect
                    painter.fillRect(target_rect, QColor("#0d1117"))
                    orig_bg = self.scene.backgroundBrush()
                    self.scene.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
                    try:
                        # Qt automatically maps source_rect coordinates into target_rect (0, 0, w, h)
                        self.scene.render(painter, target_rect, source_rect)
                    finally:
                        self.scene.setBackgroundBrush(orig_bg)
                finally:
                    painter.end()

            if target.exists() and target.stat().st_size > 0:
                svg_txt = target.read_text(encoding="utf-8", errors="replace")
                normalized_svg = normalize_svg_xml(svg_txt, w, h)
                target.write_text(normalized_svg, encoding="utf-8")
        except Exception as ex:
            xml_fallback = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'version="1.1" width="{w}px" height="{h}px" viewBox="0 0 {w} {h}">\n'
                f'<rect width="100%" height="100%" fill="#0d1117"/>\n'
                '<text x="50%" y="50%" fill="#94A3B8" font-size="16" font-family="sans-serif" text-anchor="middle">Causal Graph</text>\n'
                '</svg>'
            )
            target.write_text(xml_fallback, encoding="utf-8")
        return target

    def export_image(self, file_path: str | Path, scale: float = 3.0) -> Path:
        """Render razor-sharp high-resolution (4K equivalent, capped <= 5120px) raster image with safe file size."""
        from PyQt6.QtGui import QImage
        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        items_rect = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        if items_rect.isNull() or items_rect.isEmpty() or items_rect.width() < 10 or items_rect.height() < 10:
            items_rect = QRectF(-400, -300, 800, 600)

        # Enforce strict maximum dimension clamp (dominant dimension bounded between 3840px and 5120px)
        dom_src = max(items_rect.width(), items_rect.height())
        target_dom = max(3840.0, min(5120.0, dom_src * scale))
        scale_factor = target_dom / max(1.0, dom_src)

        w = int(round(items_rect.width() * scale_factor))
        h = int(round(items_rect.height() * scale_factor))

        # Hard safety ceiling: strictly <= 5120px on both dimensions
        if w > 5120:
            h = max(300, int(round(h * (5120.0 / w))))
            w = 5120
        if h > 5120:
            w = max(400, int(round(w * (5120.0 / h))))
            h = 5120

        w = max(400, w)
        h = max(300, h)

        image = QImage(w, h, QImage.Format.Format_ARGB32)
        image.fill(QColor("#0d1117"))
        painter = QPainter()
        if painter.begin(image):
            painter.setRenderHints(
                QPainter.RenderHint.Antialiasing
                | QPainter.RenderHint.TextAntialiasing
                | QPainter.RenderHint.SmoothPixmapTransform
            )
            target_rect = QRectF(0, 0, float(w), float(h))
            self.scene.render(painter, target=target_rect, source=items_rect)
            painter.end()

        # Balanced PNG compression (quality=80 applies standard deflate, keeping size under 2MB instead of 33MB)
        image.save(str(target), "PNG", quality=80)
        return target

    def retranslate_ui(self, lang: str) -> None:
        self._lang = lang
        self.title_label.setText(get_text("tab_causal_graph", lang))
        self.btn_zoom_in.setToolTip(get_text("tooltip_zoom_in", lang))
        self.btn_zoom_out.setToolTip(get_text("tooltip_zoom_out", lang))
        self.btn_zoom_reset.setToolTip(get_text("reset_graph", lang))
        if hasattr(self, "btn_export_png"):
            self.btn_export_png.setText(get_text("btn_export_png", lang))
            self.btn_export_png.setToolTip(get_text("tooltip_export_png", lang))
        if hasattr(self, "btn_export_svg"):
            self.btn_export_svg.setText(get_text("btn_export_svg", lang))
            self.btn_export_svg.setToolTip(get_text("tooltip_export_svg", lang))
        if hasattr(self, "btn_export"):
            self.btn_export.setText(get_text("btn_export_svg", lang))
            self.btn_export.setToolTip(get_text("tooltip_export_svg", lang))

    def update_language(self, lang_code: str, label_map: Optional[Dict[str, str]] = None) -> None:
        """Dynamically update node and edge labels to requested language without moving positions or resetting zoom/pan."""
        self.retranslate_ui(lang_code)
        if not label_map:
            try:
                from core.synthesis import COMMON_CAUSAL_TRANSLATIONS
                trans_map = COMMON_CAUSAL_TRANSLATIONS if lang_code == "ko" else {v: k for k, v in COMMON_CAUSAL_TRANSLATIONS.items()}
                for edge in self._edge_items:
                    if edge.relation in trans_map:
                        edge.update_relation(trans_map[edge.relation])
                self._relayout_edge_badges()
            except Exception:
                pass
            return

        for nid, item in self._node_items.items():
            new_label = label_map.get(nid) or label_map.get(item.clean_label) or label_map.get(item.label)
            if new_label:
                item.update_label(new_label)

        for edge in self._edge_items:
            new_rel = label_map.get(edge.relation)
            if new_rel:
                edge.update_relation(new_rel)

        self._relayout_edge_badges()

    def _relayout_edge_badges(self) -> None:
        """Compute collision-free, staggered, word-wrapped positions for all edge badges in the scene."""
        edges_with_badges = [
            e for e in self._edge_items
            if e.badge_item is not None and e.relation.strip()
        ]
        if not edges_with_badges:
            return

        # 1. Group outgoing edges by source node to stagger radiating edges
        from collections import defaultdict
        source_groups: Dict[Any, List[_CausalEdgeGraphicsItem]] = defaultdict(list)
        for edge in edges_with_badges:
            source_groups[edge.source_item].append(edge)

        for src_item, group in source_groups.items():
            if len(group) == 1:
                group[0].badge_fraction = 0.50
            else:
                # Sort group by target item X position
                sorted_group = sorted(group, key=lambda e: e.target_item.pos().x())
                for idx, edge in enumerate(sorted_group):
                    # Stagger fraction alternately between upper (~0.36) and lower (~0.64)
                    if idx % 2 == 0:
                        frac = 0.36 - 0.04 * (idx // 2)
                    else:
                        frac = 0.64 + 0.04 * (idx // 2)
                    edge.badge_fraction = max(0.24, min(0.76, frac))

        # 2. Assign initial coordinates along edge connection vectors
        for edge in edges_with_badges:
            p1 = edge.source_item.pos()
            p2 = edge.target_item.pos()
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            dist = math.hypot(dx, dy)
            if dist < 1.0:
                continue

            start_pt = intersect_card(
                p1.x(), p1.y(),
                edge.source_item.width / 2.0, edge.source_item.height / 2.0,
                dx, dy,
            )
            end_pt = intersect_card(
                p2.x(), p2.y(),
                edge.target_item.width / 2.0, edge.target_item.height / 2.0,
                -dx, -dy,
            )

            t = getattr(edge, "badge_fraction", 0.50)
            base_x = start_pt.x() + t * (end_pt.x() - start_pt.x())
            base_y = start_pt.y() + t * (end_pt.y() - start_pt.y())
            edge.badge_item.update_geometry(base_x, base_y)

        # 3. Collision Avoidance Relaxation Pass (< 20px gap clearance threshold)
        min_clearance = 20.0
        max_iterations = 50

        for iteration in range(max_iterations):
            had_collision = False
            for i in range(len(edges_with_badges)):
                badge_a = edges_with_badges[i].badge_item
                rect_a = badge_a.boundingRect()

                for j in range(i + 1, len(edges_with_badges)):
                    badge_b = edges_with_badges[j].badge_item
                    rect_b = badge_b.boundingRect()

                    dx = rect_b.center().x() - rect_a.center().x()
                    req_dx = (rect_a.width() + rect_b.width()) / 2.0 + min_clearance
                    ov_x = req_dx - abs(dx)

                    dy = rect_b.center().y() - rect_a.center().y()
                    req_dy = (rect_a.height() + rect_b.height()) / 2.0 + min_clearance
                    ov_y = req_dy - abs(dy)

                    # Overlap or clearance violation in both dimensions
                    if ov_x > 0.0 and ov_y > 0.0:
                        had_collision = True
                        if ov_y <= ov_x:
                            shift_y = ov_y / 2.0 + 1.5
                            sign_y = 1.0 if dy >= 0.0 else -1.0
                            badge_a.move_by(0.0, -sign_y * shift_y)
                            badge_b.move_by(0.0, sign_y * shift_y)
                        else:
                            shift_x = ov_x / 2.0 + 1.5
                            sign_x = 1.0 if dx >= 0.0 else -1.0
                            badge_a.move_by(-sign_x * shift_x, 0.0)
                            badge_b.move_by(sign_x * shift_x, 0.0)

            if not had_collision:
                break

        # 4. Prevent badge collision with node cards
        for edge in edges_with_badges:
            badge = edge.badge_item
            for nid, node_item in self._node_items.items():
                node_rect = node_item.sceneBoundingRect()
                b_rect = badge.boundingRect()
                if b_rect.intersects(node_rect):
                    diff_y = b_rect.center().y() - node_rect.center().y()
                    sign = 1.0 if diff_y >= 0.0 else -1.0
                    shift = node_rect.height() / 2.0 + b_rect.height() / 2.0 + 6.0 - abs(diff_y)
                    if shift > 0.0:
                        badge.move_by(0.0, sign * shift)


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
    h_sep = 150.0
    v_sep = 100.0

    node_sizes: Dict[str, Tuple[float, float]] = {
        nid: estimate_node_dimensions(node.label or nid)
        for nid, node in graph.nodes.items()
    }

    node_positions: Dict[str, Tuple[float, float]] = {}
    if not is_horizontal:
        current_y = 0.0
        for layer in layers:
            layer_h = max((node_sizes[nid][1] for nid in layer), default=72.0)
            row_widths = [node_sizes[nid][0] for nid in layer]
            total_w = sum(row_widths) + (len(layer) - 1) * h_sep
            cur_x = -total_w / 2.0
            for nid in layer:
                w = node_sizes[nid][0]
                node_x = cur_x + w / 2.0
                node_y = current_y + layer_h / 2.0
                node_positions[nid] = (round(node_x, 1), round(node_y, 1))
                cur_x += w + h_sep
            current_y += layer_h + v_sep
    else:
        current_x = 0.0
        for layer in layers:
            layer_w = max((node_sizes[nid][0] for nid in layer), default=240.0)
            col_heights = [node_sizes[nid][1] for nid in layer]
            total_h = sum(col_heights) + (len(layer) - 1) * v_sep
            cur_y = -total_h / 2.0
            for nid in layer:
                h = node_sizes[nid][1]
                node_x = current_x + layer_w / 2.0
                node_y = cur_y + h / 2.0
                node_positions[nid] = (round(node_x, 1), round(node_y, 1))
                cur_y += h + v_sep
            current_x += layer_w + h_sep

    nodes_data = [
        {
            "id": nid,
            "label": sanitize_node_label(node.label or nid),
            "x": node_positions[nid][0],
            "y": node_positions[nid][1],
            "width": node_sizes[nid][0],
            "height": node_sizes[nid][1],
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

