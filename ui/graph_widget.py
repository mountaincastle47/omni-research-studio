"""Interactive Knowledge Graph Viewer: QGraphicsView rendering of entity-relationship networks."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import networkx as nx
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
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

from core.i18n import get_text
from core.knowledge_graph import ENTITY_CATEGORIES, KnowledgeGraphEngine


class _NodeGraphicsItem(QGraphicsEllipseItem):
    """Interactive circular entity node with hover tooltips and double-click signal."""

    def __init__(
        self,
        node_id: str,
        name: str,
        category: str,
        color_hex: str,
        citations: List[int],
        description: str,
        radius: float = 24.0,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        super().__init__(-radius, -radius, radius * 2, radius * 2, parent)
        self.node_id = node_id
        self.name = name
        self.category = category
        self.color_hex = color_hex
        self.citations = citations
        self.description = description
        self.radius = radius

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
        # Center label under the node
        bounds = self.label_item.boundingRect()
        self.label_item.setPos(-bounds.width() / 2, radius + 4)


class KnowledgeGraphWidget(QWidget):
    """Main tab panel rendering interactive Cross-Corpus Entity Knowledge Graph."""

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
        self._node_items: Dict[str, _NodeGraphicsItem] = {}

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

        self.btn_relayout = QPushButton("Auto Layout", self)
        self.btn_relayout.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #38BDF8; border: 1px solid #334155; "
            "border-radius: 6px; padding: 6px 12px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.btn_relayout.clicked.connect(self._render_graph)
        top_strip.addWidget(self.btn_relayout)

        layout.addLayout(top_strip)

        # QGraphicsView & Scene
        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QBrush(QColor("#070A10")))

        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.view.setStyleSheet("QGraphicsView { border: 1px solid #1E293B; border-radius: 6px; }")
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
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
        lbl_hint = QLabel("Tip: Double-click any node to perform global FTS5 corpus search", legend_frame)
        lbl_hint.setStyleSheet("color: #64748B; font-size: 10px; font-style: italic;")
        legend_layout.addWidget(lbl_hint)

        layout.addWidget(legend_frame)

    def load_graph(self, engine: KnowledgeGraphEngine) -> None:
        """Update and re-render knowledge graph from engine."""
        self.engine = engine
        self._render_graph()

    def _render_graph(self) -> None:
        """Compute layout coordinates and populate QGraphicsScene."""
        self.scene.clear()
        self._node_items.clear()

        g = self.engine.graph
        if g.number_of_nodes() == 0:
            placeholder = self.scene.addSimpleText("No entities extracted yet. Ingest documents or run Grounded Synthesis.")
            placeholder.setFont(QFont("Segoe UI", 12))
            placeholder.setBrush(QBrush(QColor("#64748B")))
            placeholder.setPos(-200, -20)
            return

        # Compute Spring Layout coordinates scaled to viewport
        try:
            pos = nx.spring_layout(g, k=1.4, iterations=50, seed=42)
        except Exception:
            pos = nx.circular_layout(g)

        scale_factor = 420.0

        # 1. Render Edges
        for u, v, data in g.edges(data=True):
            if u not in pos or v not in pos:
                continue
            x1, y1 = pos[u][0] * scale_factor, pos[u][1] * scale_factor
            x2, y2 = pos[v][0] * scale_factor, pos[v][1] * scale_factor

            edge_line = self.scene.addLine(x1, y1, x2, y2, QPen(QColor("#334155"), 1.5))
            edge_line.setZValue(1)

            rel_text = data.get("relation", "")
            if rel_text:
                mid_x = (x1 + x2) / 2.0
                mid_y = (y1 + y2) / 2.0
                label = self.scene.addSimpleText(rel_text)
                label.setFont(QFont("Consolas", 8))
                label.setBrush(QBrush(QColor("#94A3B8")))
                label.setPos(mid_x - 15, mid_y - 8)
                label.setZValue(2)

        # 2. Render Nodes
        for node_id, data in g.nodes(data=True):
            if node_id not in pos:
                continue
            cx, cy = pos[node_id][0] * scale_factor, pos[node_id][1] * scale_factor

            name = data.get("name", node_id)
            category = data.get("category", "Concept")
            color = data.get("color", ENTITY_CATEGORIES.get(category, "#94A3B8"))
            cites = data.get("citations", [])
            desc = data.get("description", "")

            node_item = _NodeGraphicsItem(
                node_id=node_id,
                name=name,
                category=category,
                color_hex=color,
                citations=cites,
                description=desc,
                radius=18.0,
            )
            node_item.setPos(cx, cy)
            node_item.setZValue(3)
            self.scene.addItem(node_item)
            self._node_items[node_id] = node_item

        self.view.setSceneRect(self.scene.itemsBoundingRect().adjusted(-60, -60, 60, 60))

    def _on_filter_changed(self, text: str) -> None:
        """Filter node visibility or highlight matching nodes."""
        needle = text.strip().lower()
        for node_id, item in self._node_items.items():
            if not needle:
                item.setOpacity(1.0)
            elif needle in item.name.lower() or needle in item.category.lower():
                item.setOpacity(1.0)
                item.setScale(1.2)
            else:
                item.setOpacity(0.2)
                item.setScale(1.0)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        """Detect double-click on node item to emit search signal."""
        item = self.view.itemAt(self.view.mapFromParent(event.pos()))
        if isinstance(item, _NodeGraphicsItem):
            self.entity_selected.emit(item.name)
        elif item and item.parentItem() and isinstance(item.parentItem(), _NodeGraphicsItem):
            self.entity_selected.emit(item.parentItem().name)
        super().mouseDoubleClickEvent(event)

    def retranslate_ui(self, lang: str = "en") -> None:
        self._lang = lang
        self.filter_input.setPlaceholderText(get_text("graph_filter_placeholder", lang))
