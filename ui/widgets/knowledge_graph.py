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
    QGraphicsRectItem,
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
from core.knowledge_graph import (
    ENTITY_CATEGORIES,
    KG_RELATION_TRANSLATIONS,
    KnowledgeGraphEngine,
    localize_kg_relation,
)


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
        self.original_name = name
        self.name = name
        self.entity_name = name
        self.category = category
        self.color_hex = color_hex
        self.citations = citations
        self.description = description
        self.radius = radius
        self.parent_widget = parent_widget

        self.setBrush(QBrush(QColor(color_hex)))
        self.setPen(QPen(QColor("#0F172A"), 2.0))
        self.setZValue(3.0)  # Node circle at Z=3.0
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setAcceptHoverEvents(True)

        cite_str = f" | Citations: {', '.join(f'[{c}]' for c in citations)}" if citations else ""
        desc_str = f"\n{description}" if description else ""
        self.setToolTip(f"[{category}] {name}{cite_str}{desc_str}")

        # Label underneath with strict Z-value 4.0
        self.label_item = QGraphicsSimpleTextItem(name)
        self.label_item.node_item = self
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        self.label_item.setFont(font)
        self.label_item.setBrush(QBrush(QColor("#F1F5F9")))
        self.label_item.setZValue(4.0)  # Node text label at Z=4.0
        self.label_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._update_label_pos()

    def _update_label_pos(self) -> None:
        if hasattr(self, "label_item") and self.label_item:
            bounds = self.label_item.boundingRect()
            p = self.pos()
            self.label_item.setPos(p.x() - bounds.width() / 2.0, p.y() + self.radius + 4.0)

    def setPos(self, *args) -> None:
        super().setPos(*args)
        self._update_label_pos()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and hasattr(self, "label_item") and self.label_item:
            if isinstance(value, QPointF):
                bounds = self.label_item.boundingRect()
                self.label_item.setPos(value.x() - bounds.width() / 2.0, value.y() + self.radius + 4.0)
        return super().itemChange(change, value)

    def setOpacity(self, opacity: float) -> None:
        super().setOpacity(opacity)
        if hasattr(self, "label_item") and self.label_item:
            self.label_item.setOpacity(opacity)

    def setScale(self, scale: float) -> None:
        super().setScale(scale)
        if hasattr(self, "label_item") and self.label_item:
            self.label_item.setScale(scale)

    def update_label(self, new_name: str) -> None:
        """Update node name and reposition label underneath without changing node coordinates."""
        self.prepareGeometryChange()
        self.name = new_name
        self.entity_name = new_name
        self.label_item.setText(new_name)
        self._update_label_pos()
        cite_str = f" | Citations: {', '.join(f'[{c}]' for c in self.citations)}" if self.citations else ""
        desc_str = f"\n{self.description}" if self.description else ""
        self.setToolTip(f"[{self.category}] {new_name}{cite_str}{desc_str}")
        self.update()

    def mousePressEvent(self, event: Any) -> None:
        if self.parent_widget:
            self.parent_widget._on_node_clicked(self.node_id)
        try:
            super().mousePressEvent(event)
        except Exception:
            pass

    def mouseDoubleClickEvent(self, event: Any) -> None:
        if hasattr(event, "accept"):
            event.accept()
        self.setSelected(True)
        if self.parent_widget:
            self.parent_widget._on_node_double_clicked(self.entity_name)
        elif hasattr(self.scene(), "node_double_clicked"):
            self.scene().node_double_clicked.emit(self.entity_name)


class _KGEdgeItem(QGraphicsLineItem):
    """Directed edge line with midpoint label badge and interactive dimming."""

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
        lang: str = "en",
    ) -> None:
        super().__init__(x1, y1, x2, y2)
        self.source_id = source_id
        self.target_id = target_id
        self.original_relation = relation
        self.relation = relation
        self.premise = premise
        self._lang = lang

        self.setPen(QPen(QColor("#334155"), 1.8))
        self.setZValue(1.0)  # Connection lines at Z=1.0

        self.badge_bg: Optional[QGraphicsRectItem] = None
        self.label_item: Optional[QGraphicsSimpleTextItem] = None

        display_text = localize_kg_relation(relation, lang) if relation else ""
        if display_text:
            self.badge_bg = QGraphicsRectItem()
            self.badge_bg.setZValue(2.0)  # Edge label badge at Z=2.0
            self.badge_bg.setBrush(QBrush(QColor("#070A10")))  # Perfectly opaque canvas background
            self.badge_bg.setPen(QPen(QColor("#334155"), 1.2))
            self.badge_bg.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

            self.label_item = QGraphicsSimpleTextItem(display_text)
            self.label_item.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            self.label_item.setBrush(QBrush(QColor("#CBD5E1")))
            self.label_item.setZValue(2.5)  # Edge label text at Z=2.5
            self.label_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

            self._update_badge_geometry(x1, y1, x2, y2, display_text)

    def _update_badge_geometry(self, x1: float, y1: float, x2: float, y2: float, text: str) -> None:
        if not self.label_item or not self.badge_bg or not text:
            return
        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0

        if dist > 1.0:
            ux = dx / dist
            uy = dy / dist
            # Perpendicular vector pointing generally upwards (opposite positive y)
            px = -uy
            py = ux
            if py > 0 or (py == 0 and px > 0):
                px = -px
                py = -py
            offset_dist = 12.0
            pos_x = mid_x + px * offset_dist
            pos_y = mid_y + py * offset_dist
        else:
            pos_x = mid_x
            pos_y = mid_y

        self.label_item.setText(text)
        bounds = self.label_item.boundingRect()
        self.label_item.setPos(pos_x - bounds.width() / 2.0, pos_y - bounds.height() / 2.0)

        badge_rect = QRectF(
            pos_x - bounds.width() / 2.0 - 5.0,
            pos_y - bounds.height() / 2.0 - 3.0,
            bounds.width() + 10.0,
            bounds.height() + 6.0,
        )
        self.badge_bg.setRect(badge_rect)

    def update_relation(self, new_relation: str, lang: Optional[str] = None) -> None:
        """Update relation badge text and reposition badge at midpoint."""
        self.prepareGeometryChange()
        self.relation = new_relation
        if lang:
            self._lang = lang
        display_text = localize_kg_relation(new_relation, self._lang)
        line = self.line()
        self._update_badge_geometry(line.x1(), line.y1(), line.x2(), line.y2(), display_text)
        self.update()

    def setLine(self, *args) -> None:
        super().setLine(*args)
        line = self.line()
        display_text = localize_kg_relation(self.relation, self._lang)
        self._update_badge_geometry(line.x1(), line.y1(), line.x2(), line.y2(), display_text)

    def setOpacity(self, opacity: float) -> None:
        super().setOpacity(opacity)
        if self.badge_bg:
            self.badge_bg.setOpacity(opacity)
        if self.label_item:
            self.label_item.setOpacity(opacity)


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
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            zoom_in = event.angleDelta().y() > 0
            factor = 1.15 if zoom_in else (1.0 / 1.15)
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        item = self.itemAt(event.pos())
        if isinstance(item, _KGNodeItem):
            item.mouseDoubleClickEvent(event)
            event.accept()
            return
        elif hasattr(item, "node_item") and isinstance(item.node_item, _KGNodeItem):
            item.node_item.mouseDoubleClickEvent(event)
            event.accept()
            return
        elif item and item.parentItem() and isinstance(item.parentItem(), _KGNodeItem):
            item.parentItem().mouseDoubleClickEvent(event)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


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
        self._cached_layout_data: Optional[Dict[str, Any]] = None

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
        self.filter_input.setToolTip(get_text("tooltip_filter_entities", self._lang))
        self.filter_input.setStyleSheet(
            "QLineEdit { background-color: #0F172A; color: #F1F5F9; border: 1px solid #1E293B; "
            "border-radius: 6px; padding: 6px 12px; font-size: 11px; }"
        )
        self.filter_input.textChanged.connect(self._on_filter_changed)
        top_strip.addWidget(self.filter_input, stretch=1)

        self.btn_relayout = QPushButton("Auto Layout" if self._lang == "en" else "자동 배치", self)
        self.btn_relayout.setToolTip(get_text("tooltip_auto_layout", self._lang))
        self.btn_relayout.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #38BDF8; border: 1px solid #334155; "
            "border-radius: 6px; padding: 6px 12px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.btn_relayout.clicked.connect(self.auto_layout)
        top_strip.addWidget(self.btn_relayout)

        self.btn_zoom_in = QPushButton("➕", self)
        self.btn_zoom_in.setToolTip(get_text("tooltip_zoom_in", self._lang))
        self.btn_zoom_in.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #F1F5F9; border: 1px solid #334155; "
            "border-radius: 6px; padding: 6px 10px; font-size: 11px; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.btn_zoom_in.clicked.connect(lambda: self.view.scale(1.2, 1.2))
        top_strip.addWidget(self.btn_zoom_in)

        self.btn_zoom_out = QPushButton("➖", self)
        self.btn_zoom_out.setToolTip(get_text("tooltip_zoom_out", self._lang))
        self.btn_zoom_out.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #F1F5F9; border: 1px solid #334155; "
            "border-radius: 6px; padding: 6px 10px; font-size: 11px; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.btn_zoom_out.clicked.connect(lambda: self.view.scale(1.0 / 1.2, 1.0 / 1.2))
        top_strip.addWidget(self.btn_zoom_out)

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

        self._cached_layout_data = layout_data
        # Synchronize entities into self.engine so re-layout preserves them
        for n in layout_data.get("nodes", []):
            nid = n.get("id") or n.get("name")
            if nid and nid not in self.engine.graph:
                self.engine.add_entity(
                    name=n.get("name", nid),
                    category=n.get("category", "Concept"),
                    description=n.get("description", ""),
                )
        for e in layout_data.get("edges", []):
            src = e.get("source")
            tgt = e.get("target")
            if src and tgt:
                self.engine.add_relation(
                    source_name=src,
                    target_name=tgt,
                    relation=e.get("relation", "connected_to"),
                    premise=e.get("premise", ""),
                )

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
                lang=self._lang,
            )
            self.scene.addItem(edge_item)
            if edge_item.badge_bg:
                self.scene.addItem(edge_item.badge_bg)
            if edge_item.label_item:
                self.scene.addItem(edge_item.label_item)
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
            self.scene.addItem(node_item)
            if node_item.label_item:
                self.scene.addItem(node_item.label_item)
            self._node_items[nid] = node_item

        self.auto_layout_fit()

    def auto_layout(self) -> None:
        """Re-cluster coordinates and fit scene to viewport without dropping state."""
        # 1. If self.engine has nodes, compute directly
        if self.engine and self.engine.graph.number_of_nodes() > 0:
            layout_data = self.engine.compute_layout_data(min_repulsion=120.0)
            self.load_precomputed_layout(layout_data)
            return

        # 2. If cached layout data is available, populate engine and re-cluster
        if self._cached_layout_data and self._cached_layout_data.get("nodes"):
            for n in self._cached_layout_data["nodes"]:
                nid = n.get("id") or n.get("name")
                if nid:
                    self.engine.add_entity(
                        name=n.get("name", nid),
                        category=n.get("category", "Concept"),
                        description=n.get("description", ""),
                    )
            for e in self._cached_layout_data.get("edges", []):
                src = e.get("source")
                tgt = e.get("target")
                if src and tgt:
                    self.engine.add_relation(
                        source_name=src,
                        target_name=tgt,
                        relation=e.get("relation", "connected_to"),
                        premise=e.get("premise", ""),
                    )
            layout_data = self.engine.compute_layout_data(min_repulsion=120.0)
            self.load_precomputed_layout(layout_data)
            return

        # 3. If scene already has node items, populate engine and re-cluster
        if self._node_items:
            for nid, item in self._node_items.items():
                self.engine.add_entity(
                    name=item.name,
                    category=item.category,
                    description=item.description,
                )
            for edge in self._edge_items:
                self.engine.add_relation(
                    source_name=edge.source_id,
                    target_name=edge.target_id,
                    relation=edge.relation,
                    premise=edge.premise,
                )
            layout_data = self.engine.compute_layout_data(min_repulsion=120.0)
            self.load_precomputed_layout(layout_data)
            return

        # 4. If genuinely empty, show placeholder
        self._show_empty_placeholder()

    def auto_layout_fit(self) -> None:
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

    def _select_node(self, node_id: str) -> None:
        """Select node and highlight its connected edges and neighbors."""
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

    def _on_node_clicked(self, node_id: str) -> None:
        """Highlight connected edges and neighbor nodes; dim unrelated items."""
        if self._selected_node == node_id:
            # Toggle off
            self._selected_node = None
            self._reset_selection()
            return
        self._select_node(node_id)

    def _on_node_double_clicked(self, entity_name: str) -> None:
        """Keep node selected and emit entity_selected for FTS5 corpus search."""
        for nid, item in self._node_items.items():
            if item.name == entity_name or nid == entity_name:
                self._select_node(nid)
                item.setSelected(True)
                break
        self.entity_selected.emit(entity_name)

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
            self._on_node_double_clicked(item.name)
        elif item and item.parentItem() and isinstance(item.parentItem(), _KGNodeItem):
            self._on_node_double_clicked(item.parentItem().name)
        super().mouseDoubleClickEvent(event)

    def retranslate_ui(self, lang: str = "en") -> None:
        self._lang = lang
        self.filter_input.setPlaceholderText(get_text("graph_filter_placeholder", lang))
        self.filter_input.setToolTip(get_text("tooltip_filter_entities", lang))
        self.btn_relayout.setText("Auto Layout" if lang == "en" else "자동 배치")
        self.btn_relayout.setToolTip(get_text("tooltip_auto_layout", lang))
        self.btn_zoom_in.setToolTip(get_text("tooltip_zoom_in", lang))
        self.btn_zoom_out.setToolTip(get_text("tooltip_zoom_out", lang))

    def update_language(self, lang_code: str, label_map: Optional[Dict[str, str]] = None) -> None:
        """Dynamically update node and edge labels to requested language without moving positions or resetting zoom/pan."""
        self._lang = lang_code
        self.retranslate_ui(lang_code)

        # 1. Update edge relations (translate standard snake_case tokens to Korean if ko, or English if en)
        for edge in self._edge_items:
            rel = edge.relation or getattr(edge, "original_relation", "")
            mapped_rel = label_map.get(rel) if label_map else None
            target_rel = mapped_rel or rel
            edge.update_relation(target_rel, lang=lang_code)

        # 2. Update entity node names if mappings exist, or restore original English names
        for nid, node in self._node_items.items():
            if lang_code == "en":
                orig = getattr(node, "original_name", "") or nid
                node.update_label(orig)
            elif label_map:
                new_label = (
                    label_map.get(nid)
                    or label_map.get(node.name)
                    or label_map.get(getattr(node, "entity_name", ""))
                    or label_map.get(getattr(node, "original_name", ""))
                )
                if new_label:
                    node.update_label(new_label)
