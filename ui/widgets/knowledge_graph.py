"""Interactive Knowledge Graph Widget with OpenGL Acceleration, Force-Directed Clustering, and Viewport Zoom/Pan."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Union

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
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

from core.i18n import get_text
from core.knowledge_graph import ENTITY_CATEGORIES, KnowledgeGraphEngine


class _KGNodeItem(QGraphicsEllipseItem):
    """Interactive circular entity node with hover tooltips, click selection, and movement flags."""

    def __init__(
        self,
        node_id: str,
        name: str,
        category: str,
        color_hex: str,
        citations: List[int],
        description: str,
        radius: float = 24.0,
        parent_widget: Optional[KnowledgeGraphWidget] = None,
    ) -> None:
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.node_id = node_id
        self.name = name
        self.category = category
        self.color_hex = color_hex
        self.citations = citations
        self.description = description
        self.radius = radius
        self.parent_widget = parent_widget

        self.setBrush(QBrush(QColor(color_hex)))
        self.setPen(QPen(QColor("#0F172A"), 2.0))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setAcceptHoverEvents(True)

        cite_str = f" | Citations: {', '.join(f'[{c}]' for c in citations)}" if citations else ""
        desc_str = f"\n{description}" if description else ""
        self.setToolTip(f"[{category}] {name}{cite_str}{desc_str}")

        # Label underneath
        self.label_item = QGraphicsSimpleTextItem(name, self)
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        self.label_item.setFont(font)
        self.label_item.setBrush(QBrush(QColor("#F1F5F9")))
        bounds = self.label_item.boundingRect()
        self.label_item.setPos(-bounds.width() / 2.0, radius + 4)

    def mousePressEvent(self, event: Any) -> None:
        if self.parent_widget:
            self.parent_widget._on_node_clicked(self.node_id)
        super().mousePressEvent(event)


class _KGEdgeItem(QGraphicsLineItem):
    """Directed edge line with midpoint label and interactive dimming."""

    def __init__(
        self,
        source_id: str,
        target_id: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        relation: str = "",
        premise: str = "",
    ) -> None:
        super().__init__(x1, y1, x2, y2)
        self.source_id = source_id
        self.target_id = target_id
        self.relation = relation
        self.premise = premise
        self.setPen(QPen(QColor("#334155"), 1.8))
        self.setZValue(1)

        self.label_item: Optional[QGraphicsSimpleTextItem] = None
        if relation:
            mid_x = (x1 + x2) / 2.0
            mid_y = (y1 + y2) / 2.0
            self.label_item = QGraphicsSimpleTextItem(relation, self)
            self.label_item.setFont(QFont("Consolas", 8))
            self.label_item.setBrush(QBrush(QColor("#94A3B8")))
            self.label_item.setPos(mid_x - 15, mid_y - 8)
            self.label_item.setZValue(2)


class KnowledgeGraphView(QGraphicsView):
    """OpenGL-accelerated QGraphicsView with wheel zoom and scrollbar elimination."""

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
        delta = event.angleDelta().y()
        if delta > 0:
            self.scale(1.15, 1.15)
        elif delta < 0:
            self.scale(1.0 / 1.15, 1.0 / 1.15)
        else:
            super().wheelEvent(event)


class KnowledgeGraphWidget(QWidget):
    """Main tab panel rendering interactive Cross-Corpus Entity Knowledge Graph with OpenGL acceleration and clustered layout."""

    entity_selected = pyqtSignal(str)

    def __init__(
        self,
        engine: Optional[KnowledgeGraphEngine] = None,
        lang: str = "en",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine or KnowledgeGraphEngine()
        self._lang = lang
        self._node_items: Dict[str, _KGNodeItem] = {}
        self._edge_items: List[_KGEdgeItem] = []
        self._selected_node: Optional[str] = None

        self._build_ui()
        self._render_graph()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Top Control Strip
        top_strip = QHBoxLayout()
        self.filter_input = QLineEdit(self)
        self.filter_input.setPlaceholderText(get_text("graph_filter_placeholder", self._lang))
        self.filter_input.setStyleSheet(
            "QLineEdit { background-color: #0F172A; color: #F1F5F9; border: 1px solid #1E293B; "
            "border-radius: 6px; padding: 6px 12px; font-size: 11px; }"
        )
        self.filter_input.textChanged.connect(self._on_filter_changed)
        top_strip.addWidget(self.filter_input, stretch=1)

        self.btn_relayout = QPushButton("Auto Layout" if self._lang == "en" else "자동 배치", self)
        self.btn_relayout.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #38BDF8; border: 1px solid #334155; "
            "border-radius: 6px; padding: 6px 12px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.btn_relayout.clicked.connect(self.auto_layout)
        top_strip.addWidget(self.btn_relayout)

        layout.addLayout(top_strip)

        # Scene and OpenGL Viewport
        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QBrush(QColor("#070A10")))

        self.view = KnowledgeGraphView(self.scene, self)
        layout.addWidget(self.view, stretch=1)

        # Bottom Legend Bar
        legend_frame = QFrame(self)
        legend_frame.setStyleSheet("QFrame { background-color: #0B0E14; border: 1px solid #1E293B; border-radius: 4px; padding: 4px; }")
        legend_layout = QHBoxLayout(legend_frame)
        legend_layout.setContentsMargins(6, 2, 6, 2)
        legend_layout.setSpacing(12)

        for cat, col in ENTITY_CATEGORIES.items():
            lbl = QLabel(f"● {cat}", legend_frame)
            lbl.setStyleSheet(f"color: {col}; font-size: 10px; font-weight: 600;")
            legend_layout.addWidget(lbl)

        legend_layout.addStretch(1)
        lbl_hint = QLabel("Tip: Click node to highlight connections | Double-click to search corpus", legend_frame)
        lbl_hint.setStyleSheet("color: #64748B; font-size: 10px; font-style: italic;")
        legend_layout.addWidget(lbl_hint)

        layout.addWidget(legend_frame)

    def load_precomputed_layout(self, layout_data: Optional[Dict[str, Any]]) -> None:
        """Instantly populate graph from background precalculated layout coordinates."""
        if not layout_data or not layout_data.get("nodes"):
            self.scene.clear()
            self._node_items.clear()
            self._edge_items.clear()
            self._show_empty_placeholder()
            return

        self.scene.clear()
        self._node_items.clear()
        self._edge_items.clear()
        self._selected_node = None

        # 1. Render Edges
        for e in layout_data.get("edges", []):
            x1, y1 = e.get("x1", 0.0), e.get("y1", 0.0)
            x2, y2 = e.get("x2", 0.0), e.get("y2", 0.0)
            edge_item = _KGEdgeItem(
                source_id=e["source"],
                target_id=e["target"],
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                relation=e.get("relation", ""),
                premise=e.get("premise", ""),
            )
            self.scene.addItem(edge_item)
            self._edge_items.append(edge_item)

        # 2. Render Nodes
        for n in layout_data.get("nodes", []):
            nid = n["id"]
            node_item = _KGNodeItem(
                node_id=nid,
                name=n.get("name", nid),
                category=n.get("category", "Concept"),
                color_hex=n.get("color", "#94A3B8"),
                citations=n.get("citations", []),
                description=n.get("description", ""),
                radius=20.0,
                parent_widget=self,
            )
            node_item.setPos(n.get("x", 0.0), n.get("y", 0.0))
            node_item.setZValue(3)
            self.scene.addItem(node_item)
            self._node_items[nid] = node_item

        self.auto_layout_fit()

    def auto_layout(self) -> None:
        """Re-cluster coordinates and fit scene to viewport with 50px margins."""
        layout_data = self.engine.compute_layout_data(min_repulsion=120.0)
        self.load_precomputed_layout(layout_data)

    def auto_layout_fit(self) -> None:
        """Fit scene to viewport with 50px margins."""
        rect = self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
        if not rect.isEmpty():
            self.scene.setSceneRect(rect)
            self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def load_graph(
        self,
        engine_or_entities: Any = None,
        relations: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Update and re-render knowledge graph from engine instance or (entities, relations) lists."""
        if isinstance(engine_or_entities, KnowledgeGraphEngine):
            self.engine = engine_or_entities
        elif isinstance(engine_or_entities, list):
            for e in engine_or_entities:
                if isinstance(e, dict) and e.get("name"):
                    self.engine.add_entity(
                        name=e["name"],
                        category=e.get("category", "Concept"),
                        description=e.get("description", ""),
                    )
            if relations and isinstance(relations, list):
                for r in relations:
                    if isinstance(r, dict) and r.get("source") and r.get("target"):
                        self.engine.add_relation(
                            source_name=r["source"],
                            target_name=r["target"],
                            relation=r.get("relation", "connected_to"),
                            premise=r.get("premise", ""),
                        )
        self.auto_layout()

    def _render_graph(self) -> None:
        self.auto_layout()

    def _show_empty_placeholder(self) -> None:
        placeholder = self.scene.addSimpleText(
            "No entities extracted yet. Ingest documents or run Grounded Synthesis."
            if self._lang == "en"
            else "추출된 지식 개체가 없습니다. 문서를 인제스트하거나 접지 합성을 실행하십시오."
        )
        placeholder.setFont(QFont("Segoe UI", 12))
        placeholder.setBrush(QBrush(QColor("#64748B")))
        bounds = placeholder.boundingRect()
        placeholder.setPos(-bounds.width() / 2.0, -bounds.height() / 2.0)
        self.scene.setSceneRect(placeholder.boundingRect().adjusted(-80, -80, 80, 80))

    def _on_node_clicked(self, node_id: str) -> None:
        """Highlight connected edges and neighbor nodes; dim unrelated items."""
        if self._selected_node == node_id:
            # Toggle off
            self._selected_node = None
            self._reset_selection()
            return

        self._selected_node = node_id
        connected_neighbors: Set[str] = {node_id}

        for edge in self._edge_items:
            is_connected = edge.source_id == node_id or edge.target_id == node_id
            if is_connected:
                edge.setOpacity(1.0)
                edge.setPen(QPen(QColor("#38BDF8"), 2.5))
                connected_neighbors.add(edge.source_id)
                connected_neighbors.add(edge.target_id)
            else:
                edge.setOpacity(0.15)
                edge.setPen(QPen(QColor("#334155"), 1.2))

        for nid, item in self._node_items.items():
            if nid in connected_neighbors:
                item.setOpacity(1.0)
                item.setScale(1.15 if nid == node_id else 1.05)
            else:
                item.setOpacity(0.2)
                item.setScale(1.0)

    def _reset_selection(self) -> None:
        for edge in self._edge_items:
            edge.setOpacity(1.0)
            edge.setPen(QPen(QColor("#334155"), 1.8))
        for item in self._node_items.values():
            item.setOpacity(1.0)
            item.setScale(1.0)

    def _on_filter_changed(self, text: str) -> None:
        """Filter node visibility or highlight matching nodes."""
        needle = text.strip().lower()
        for node_id, item in self._node_items.items():
            if not needle:
                item.setOpacity(1.0)
                item.setScale(1.0)
            elif needle in item.name.lower() or needle in item.category.lower():
                item.setOpacity(1.0)
                item.setScale(1.2)
            else:
                item.setOpacity(0.2)
                item.setScale(1.0)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        """Detect double-click on node item to emit search signal."""
        item = self.view.itemAt(self.view.mapFromParent(event.pos()))
        if isinstance(item, _KGNodeItem):
            self.entity_selected.emit(item.name)
        elif item and item.parentItem() and isinstance(item.parentItem(), _KGNodeItem):
            self.entity_selected.emit(item.parentItem().name)
        super().mouseDoubleClickEvent(event)

    def retranslate_ui(self, lang: str = "en") -> None:
        self._lang = lang
        self.filter_input.setPlaceholderText(get_text("graph_filter_placeholder", lang))
        self.btn_relayout.setText("Auto Layout" if lang == "en" else "자동 배치")
