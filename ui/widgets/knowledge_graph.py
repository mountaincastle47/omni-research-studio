"""Interactive Knowledge Graph Widget with OpenGL Acceleration, Force-Directed Clustering, and Viewport Zoom/Pan."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QFileDialog,
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
    translate_kg_entity_name,
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

    def setVisible(self, visible: bool) -> None:
        super().setVisible(visible)
        if hasattr(self, "label_item") and self.label_item:
            self.label_item.setVisible(visible)

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

    def hoverEnterEvent(self, event: Any) -> None:
        self.setPen(QPen(QColor("#38BDF8"), 3.0))
        if self.parent_widget:
            self.parent_widget._highlight_node_connections(self.node_id, hover=True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: Any) -> None:
        if self.parent_widget and self.parent_widget._selected_node == self.node_id:
            self.setPen(QPen(QColor("#38BDF8"), 2.5))
        else:
            self.setPen(QPen(QColor("#0F172A"), 2.0))
        if self.parent_widget:
            self.parent_widget._unhighlight_node_connections(self.node_id)
        super().hoverLeaveEvent(event)

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
    """Directed edge line with midpoint label badge, fat hit-test shape, and dynamic hover/selection reveal."""

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
        parent_widget: Optional[KnowledgeGraphWidget] = None,
    ) -> None:
        super().__init__(x1, y1, x2, y2)
        self.source_id = source_id
        self.target_id = target_id
        self.original_relation = relation
        self.relation = relation
        self.premise = premise
        self._lang = lang
        self.parent_widget = parent_widget
        self._badge_visible = False
        self.source_node: Optional[_KGNodeItem] = None
        self.target_node: Optional[_KGNodeItem] = None

        self.setPen(QPen(QColor("#334155"), 1.8))
        self.setZValue(1.0)  # Connection lines at Z=1.0
        self.setAcceptHoverEvents(True)

        self.badge_bg: Optional[QGraphicsRectItem] = None
        self.label_item: Optional[QGraphicsSimpleTextItem] = None

        display_text = localize_kg_relation(relation, lang) if relation else ""
        if display_text:
            self.badge_bg = QGraphicsRectItem()
            self.badge_bg.setZValue(2.0)  # Edge label badge at Z=2.0
            self.badge_bg.setBrush(QBrush(QColor("#070A10")))  # Perfectly opaque canvas background
            self.badge_bg.setPen(QPen(QColor("#334155"), 1.2))
            self.badge_bg.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.badge_bg.setVisible(False)  # Hidden by default to eliminate visual clutter

            self.label_item = QGraphicsSimpleTextItem(display_text)
            self.label_item.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            self.label_item.setBrush(QBrush(QColor("#CBD5E1")))
            self.label_item.setZValue(2.5)  # Edge label text at Z=2.5
            self.label_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.label_item.setVisible(False)  # Hidden by default

            self._update_badge_geometry(x1, y1, x2, y2, display_text)

    def shape(self) -> QPainterPath:
        """Provide generous 12px hit box around edge line for smooth hover and interaction."""
        path = super().shape()
        stroker = QPainterPathStroker()
        stroker.setWidth(12.0)
        return stroker.createStroke(path)

    def show_badge(self, visible: bool) -> None:
        """Toggle edge badge visibility dynamically on hover or node selection."""
        self._badge_visible = visible
        if self.badge_bg:
            self.badge_bg.setVisible(visible)
        if self.label_item:
            self.label_item.setVisible(visible)

    def hoverEnterEvent(self, event: Any) -> None:
        self.setPen(QPen(QColor("#38BDF8"), 2.4))
        self.show_badge(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: Any) -> None:
        # If either end is selected in parent_widget, keep highlighted and visible
        if self.parent_widget and self.parent_widget._selected_node in (self.source_id, self.target_id):
            self.setPen(QPen(QColor("#38BDF8"), 2.2))
            self.show_badge(True)
        else:
            self.setPen(QPen(QColor("#334155"), 1.8))
            self.show_badge(False)
        super().hoverLeaveEvent(event)

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
        self.show_badge(self._badge_visible)
        self.update()

    def setLine(self, *args) -> None:
        super().setLine(*args)
        line = self.line()
        display_text = localize_kg_relation(self.relation, self._lang)
        self._update_badge_geometry(line.x1(), line.y1(), line.x2(), line.y2(), display_text)
        self.show_badge(self._badge_visible)

    def setVisible(self, visible: bool) -> None:
        super().setVisible(visible)
        if not visible:
            if self.badge_bg:
                self.badge_bg.setVisible(False)
            if self.label_item:
                self.label_item.setVisible(False)
        else:
            if self._badge_visible:
                if self.badge_bg:
                    self.badge_bg.setVisible(True)
                if self.label_item:
                    self.label_item.setVisible(True)

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
        self.active_categories: Set[str] = {
            "Organization", "Program", "Key Figure", "Standard", "Material", "Concept"
        }
        self.category_buttons: Dict[str, QPushButton] = {}

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

        self.btn_export_png = QPushButton("Export PNG" if self._lang == "en" else "PNG 내보내기", self)
        self.btn_export_png.setToolTip(get_text("tooltip_export_png", self._lang))
        self.btn_export_png.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #F1F5F9; border: 1px solid #334155; "
            "border-radius: 6px; padding: 6px 12px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.btn_export_png.clicked.connect(self._on_export_png)
        top_strip.addWidget(self.btn_export_png)

        self.btn_export_svg = QPushButton("Export SVG" if self._lang == "en" else "SVG 내보내기", self)
        self.btn_export_svg.setToolTip(get_text("tooltip_export_svg", self._lang))
        self.btn_export_svg.setStyleSheet(
            "QPushButton { background-color: #1E293B; color: #F1F5F9; border: 1px solid #334155; "
            "border-radius: 6px; padding: 6px 12px; font-size: 11px; font-weight: 600; } "
            "QPushButton:hover { background-color: #334155; }"
        )
        self.btn_export_svg.clicked.connect(self._on_export_svg)
        top_strip.addWidget(self.btn_export_svg)
        self.btn_export = self.btn_export_svg

        layout.addLayout(top_strip)

        # Scene and OpenGL Viewport
        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QBrush(QColor("#070A10")))

        self.view = KnowledgeGraphView(self.scene, self)
        layout.addWidget(self.view, stretch=1)

        # Bottom Legend Bar with Interactive Category Filter Toggles
        legend_frame = QFrame(self)
        legend_frame.setStyleSheet("QFrame { background-color: #0B0E14; border: 1px solid #1E293B; border-radius: 4px; padding: 4px; }")
        legend_layout = QHBoxLayout(legend_frame)
        legend_layout.setContentsMargins(6, 3, 6, 3)
        legend_layout.setSpacing(8)

        cat_key_map = {
            "Organization": "organization",
            "Program": "program",
            "Key Figure": "key_figure",
            "Standard": "standard",
            "Material": "material",
            "Concept": "concept",
        }

        for cat, col in ENTITY_CATEGORIES.items():
            k = cat_key_map.get(cat, cat.lower())
            btn = QPushButton(f"● {get_text(f'category_{k}', self._lang)}", legend_frame)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setToolTip(get_text(f"tooltip_toggle_category_{k}", self._lang))
            btn.setStyleSheet(self._get_category_button_style(col))
            btn.toggled.connect(lambda checked, c=cat: self._on_category_toggled(c, checked))
            self.category_buttons[cat] = btn
            legend_layout.addWidget(btn)

        legend_layout.addStretch(1)
        self.lbl_hint = QLabel(
            "Tip: Click category to toggle | Click node to inspect | Double-click to search corpus"
            if self._lang == "en"
            else "팁: 범주 클릭하여 켜기/끄기 | 노드 클릭하여 연결 강조 | 더블클릭하여 검색",
            legend_frame,
        )
        self.lbl_hint.setStyleSheet("color: #64748B; font-size: 10px; font-style: italic;")
        legend_layout.addWidget(self.lbl_hint)

        layout.addWidget(legend_frame)

    @staticmethod
    def _get_category_button_style(color_hex: str) -> str:
        return (
            f"QPushButton {{"
            f"  background-color: #0B0F19; color: #475569; border: 1px solid #1E293B; "
            f"  border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 500;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: #131B2E; color: #94A3B8; border-color: #334155;"
            f"}}"
            f"QPushButton:checked {{"
            f"  background-color: #131D2E; color: {color_hex}; border: 1.5px solid {color_hex}; "
            f"  font-weight: 700;"
            f"}}"
            f"QPushButton:checked:hover {{"
            f"  background-color: #1E293B; border-color: {color_hex};"
            f"}}"
        )

    def _on_category_toggled(self, category: str, checked: bool) -> None:
        if checked:
            self.active_categories.add(category)
        else:
            self.active_categories.discard(category)
        self.apply_category_filter()

    def apply_category_filter(self) -> None:
        """Filter visible nodes and connected edges based on active category toggles."""
        for node in self._node_items.values():
            node.setVisible(node.category in self.active_categories)
        for edge in self._edge_items:
            src = edge.source_node or self._node_items.get(edge.source_id.lower()) or self._node_items.get(edge.source_id)
            tgt = edge.target_node or self._node_items.get(edge.target_id.lower()) or self._node_items.get(edge.target_id)
            edge_visible = bool(src and src.isVisible() and tgt and tgt.isVisible())
            edge.setVisible(edge_visible)

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
                parent_widget=self,
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

        for edge in self._edge_items:
            edge.source_node = self._node_items.get(edge.source_id.lower()) or self._node_items.get(edge.source_id)
            edge.target_node = self._node_items.get(edge.target_id.lower()) or self._node_items.get(edge.target_id)

        self.apply_category_filter()
        self.enforce_node_collision_boundaries()
        self.auto_layout_fit()

    def enforce_node_collision_boundaries(self) -> None:
        """Enforce rigid physical collision boundaries between all node items in the scene."""
        items = list(self._node_items.values())
        if len(items) < 2:
            return
        circle_radius = 24.0
        padding = 15.0
        for _ in range(35):
            collision_found = False
            for a in range(len(items)):
                item_a = items[a]
                pos_a = item_a.pos()
                w_a = item_a.label_item.boundingRect().width() if item_a.label_item else len(item_a.name) * 8.5
                r_a = max(circle_radius, w_a / 2.0) + padding
                for b in range(a + 1, len(items)):
                    item_b = items[b]
                    pos_b = item_b.pos()
                    w_b = item_b.label_item.boundingRect().width() if item_b.label_item else len(item_b.name) * 8.5
                    r_b = max(circle_radius, w_b / 2.0) + padding
                    min_dist = r_a + r_b + 30.0
                    dx = pos_a.x() - pos_b.x()
                    dy = pos_a.y() - pos_b.y()
                    dist = math.hypot(dx, dy)
                    if dist < min_dist:
                        collision_found = True
                        if dist < 0.01:
                            dx, dy, dist = 1.0, 0.0, 1.0
                        overlap = min_dist - dist
                        ux = dx / dist
                        uy = dy / dist
                        item_a.setPos(pos_a.x() + ux * (overlap / 2.0), pos_a.y() + uy * (overlap / 2.0))
                        item_b.setPos(pos_b.x() - ux * (overlap / 2.0), pos_b.y() - uy * (overlap / 2.0))
                        pos_a = item_a.pos()
            if not collision_found:
                break

    def set_documents(self, documents: Optional[List[Any]] = None) -> None:
        """Populate or update graph entities based on document metadata."""
        if not documents:
            return
        for doc in documents:
            title = getattr(doc, "title", "") or f"Doc {getattr(doc, 'doc_id', '')}"
            cite_id = getattr(doc, "doc_id", None)
            self.engine.add_entity(title, category="Concept", cite_id=cite_id)
        if self.engine.graph.number_of_nodes() > 0:
            layout_data = self.engine.compute_layout_data(min_repulsion=280.0)
            self.load_precomputed_layout(layout_data)

    def auto_layout(self) -> None:
        """Re-cluster coordinates and fit scene to viewport without dropping state."""
        # 1. If self.engine has nodes, compute directly
        if self.engine and self.engine.graph.number_of_nodes() > 0:
            layout_data = self.engine.compute_layout_data(min_repulsion=280.0)
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
            layout_data = self.engine.compute_layout_data(min_repulsion=280.0)
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
            layout_data = self.engine.compute_layout_data(min_repulsion=280.0)
            self.load_precomputed_layout(layout_data)
            return

        # 4. If genuinely empty, show placeholder
        self._show_empty_placeholder()

    def auto_layout_fit(self) -> None:
        """Fit scene to viewport with 80px margins and clamp scale to readable bounds."""
        rect = self.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80)
        if rect.isValid() and not rect.isEmpty():
            self.scene.setSceneRect(rect)
            self.view.resetTransform()
            self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            current_scale = self.view.transform().m11()
            if current_scale < 0.65:
                self.view.resetTransform()
                self.view.scale(0.65, 0.65)
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

    def _highlight_node_connections(self, node_id: str, hover: bool = False) -> None:
        """Dynamically reveal edge badges for connections to the hovered node."""
        norm = node_id.lower()
        target_id = next(
            (nid for nid in self._node_items if nid == node_id or nid.lower() == norm or getattr(self._node_items[nid], "original_name", "").lower() == norm),
            node_id
        )
        for edge in self._edge_items:
            is_connected = edge.source_id in (target_id, node_id, norm) or edge.target_id in (target_id, node_id, norm)
            if is_connected:
                edge.setOpacity(1.0)
                edge.setPen(QPen(QColor("#38BDF8"), 2.4))
                edge.show_badge(True)
            elif not self._selected_node:
                edge.setOpacity(0.35)

    def _unhighlight_node_connections(self, node_id: str) -> None:
        """Revert hover highlight; restore active selection if node is selected."""
        if self._selected_node:
            self._select_node(self._selected_node)
        else:
            self._reset_selection()

    def _select_node(self, node_id: str) -> None:
        """Select node and highlight its connected edges and neighbors, revealing their badges."""
        norm = node_id.lower()
        target_id = next(
            (nid for nid in self._node_items if nid == node_id or nid.lower() == norm or getattr(self._node_items[nid], "original_name", "").lower() == norm),
            node_id
        )
        self._selected_node = target_id
        connected_neighbors: Set[str] = {target_id, node_id, norm}

        for edge in self._edge_items:
            is_connected = edge.source_id in (target_id, node_id, norm) or edge.target_id in (target_id, node_id, norm)
            if is_connected:
                edge.setOpacity(1.0)
                edge.setPen(QPen(QColor("#38BDF8"), 2.5))
                edge.show_badge(True)
                connected_neighbors.add(edge.source_id)
                connected_neighbors.add(edge.target_id)
            else:
                edge.setOpacity(0.15)
                edge.setPen(QPen(QColor("#334155"), 1.2))
                edge.show_badge(False)

        for nid, item in self._node_items.items():
            if nid in connected_neighbors or item.node_id in connected_neighbors:
                item.setOpacity(1.0)
                item.setScale(1.15 if (nid == target_id or nid == node_id) else 1.05)
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
            if item.name == entity_name or nid == entity_name or getattr(item, "original_name", "") == entity_name:
                self._select_node(nid)
                item.setSelected(True)
                break
        self.entity_selected.emit(entity_name)

    def _reset_selection(self) -> None:
        self._selected_node = None
        for edge in self._edge_items:
            edge.setOpacity(1.0)
            edge.setPen(QPen(QColor("#334155"), 1.8))
            edge.show_badge(False)
        for item in self._node_items.values():
            item.setOpacity(1.0)
            item.setScale(1.0)
            item.setPen(QPen(QColor("#0F172A"), 2.0))

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
        if hasattr(self, "btn_export_png"):
            self.btn_export_png.setText(get_text("btn_export_png", lang))
            self.btn_export_png.setToolTip(get_text("tooltip_export_png", lang))
        if hasattr(self, "btn_export_svg"):
            self.btn_export_svg.setText(get_text("btn_export_svg", lang))
            self.btn_export_svg.setToolTip(get_text("tooltip_export_svg", lang))
        if hasattr(self, "btn_export"):
            self.btn_export.setText(get_text("btn_export_svg", lang))
            self.btn_export.setToolTip(get_text("tooltip_export_svg", lang))

        cat_key_map = {
            "Organization": "organization",
            "Program": "program",
            "Key Figure": "key_figure",
            "Standard": "standard",
            "Material": "material",
            "Concept": "concept",
        }
        for cat, btn in getattr(self, "category_buttons", {}).items():
            k = cat_key_map.get(cat, cat.lower())
            btn.setText(f"● {get_text(f'category_{k}', lang)}")
            btn.setToolTip(get_text(f"tooltip_toggle_category_{k}", lang))

        if hasattr(self, "lbl_hint"):
            self.lbl_hint.setText(
                "Tip: Click category to toggle | Click node to inspect | Double-click to search corpus"
                if lang == "en"
                else "팁: 범주 클릭하여 켜기/끄기 | 노드 클릭하여 연결 강조 | 더블클릭하여 검색"
            )

    def _on_export_png(self) -> None:
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Knowledge Graph" if self._lang == "en" else "지식 그래프 저장",
            "knowledge_graph.png",
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
            "Save Knowledge Graph" if self._lang == "en" else "지식 그래프 저장",
            "knowledge_graph.svg",
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
        """Export knowledge graph to standard-compliant scalable vector SVG 1.1 with positive (0,0) origin and accurate coordinate scaling."""
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
            generator.setTitle("Knowledge Graph")
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
                raw_bytes = target.read_bytes()
                if raw_bytes.startswith(b'\xef\xbb\xbf'):
                    raw_bytes = raw_bytes[3:]
                svg_txt = raw_bytes.decode("utf-8", errors="replace")
                normalized_svg = normalize_svg_xml(svg_txt, w, h)
                target.write_bytes(normalized_svg.encode("utf-8"))
        except Exception as ex:
            xml_fallback = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'version="1.1" width="{w}px" height="{h}px" viewBox="0 0 {w} {h}">\n'
                f'<rect width="100%" height="100%" fill="#0d1117"/>\n'
                '<text x="50%" y="50%" fill="#94A3B8" font-size="16" font-family="sans-serif" text-anchor="middle">Knowledge Graph</text>\n'
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

        # 2. Update entity node names (translate to Korean if ko, or restore original English if en)
        for nid, node in self._node_items.items():
            if lang_code == "en":
                orig = getattr(node, "original_name", "") or nid
                node.update_label(orig)
            else:
                orig = getattr(node, "original_name", "") or node.name or nid
                new_label = None
                if label_map:
                    new_label = (
                        label_map.get(nid)
                        or label_map.get(orig)
                        or label_map.get(node.name)
                        or label_map.get(orig.lower())
                    )
                if not new_label:
                    new_label = translate_kg_entity_name(orig, lang=lang_code)
                if new_label and new_label != node.name:
                    node.update_label(new_label)
