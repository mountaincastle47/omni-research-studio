"""Test suite verifying Knowledge Graph node double-click search and Causal Graph unified navigation."""

import os
import unittest
from PyQt6.QtCore import QPointF, Qt, QEvent
from PyQt6.QtWidgets import QApplication, QGraphicsSceneMouseEvent

# Ensure QApplication is initialized for headless test
app = QApplication.instance() or QApplication([])

from ui.widgets.knowledge_graph import KnowledgeGraphWidget, _KGNodeItem, KnowledgeGraphView
from ui.graph_viewer import CausalGraphWidget, CausalGraphView
from ui.search_drawer import SearchDockWidget
from core.knowledge_graph import KnowledgeGraphEngine


class MockEvent:
    def __init__(self):
        self.accepted = False
    def accept(self):
        self.accepted = True


class TestKnowledgeGraphDoubleClickAndCausalNav(unittest.TestCase):
    def setUp(self):
        self.engine = KnowledgeGraphEngine()
        self.engine.add_entity("Quantum Computing", "Concept", "A field of computing.")
        self.engine.add_entity("Superconductivity", "Concept", "Zero electrical resistance.")
        self.engine.add_relation("Quantum Computing", "Superconductivity", "utilizes")

    def test_kg_node_double_click_emission(self):
        widget = KnowledgeGraphWidget(engine=self.engine)
        emitted_entities = []
        widget.entity_selected.connect(lambda name: emitted_entities.append(name))

        node_item = widget._node_items.get("quantum computing")
        self.assertIsNotNone(node_item, "Node item should exist in scene")

        # Simulate first click (mouse press)
        press_event = MockEvent()
        node_item.mousePressEvent(press_event)
        self.assertEqual(widget._selected_node, "quantum computing")

        # Simulate double click
        dbl_event = MockEvent()
        node_item.mouseDoubleClickEvent(dbl_event)
        self.assertTrue(dbl_event.accepted)
        self.assertEqual(len(emitted_entities), 1)
        self.assertEqual(emitted_entities[0], "Quantum Computing")
        self.assertEqual(widget._selected_node, "quantum computing")

    def test_search_dock_forwarding(self):
        dock = SearchDockWidget()
        self.assertIsNotNone(dock.search_input)
        dock.search_input.setText("Quantum Computing")
        self.assertEqual(dock.drawer.search_input.text(), "Quantum Computing")
        dock.perform_search()
        self.assertTrue(hasattr(dock, "_run_search"))

    def test_causal_graph_navigation(self):
        causal_widget = CausalGraphWidget()
        self.assertIsInstance(causal_widget.view, CausalGraphView)
        self.assertEqual(causal_widget.view.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(causal_widget.view.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertEqual(causal_widget.view.dragMode(), causal_widget.view.DragMode.ScrollHandDrag)

        # Test zoom in / out / reset
        initial_transform = causal_widget.view.transform()
        causal_widget._on_zoom_in()
        self.assertGreater(causal_widget.view.transform().m11(), initial_transform.m11())

        causal_widget._on_zoom_out()
        causal_widget._on_zoom_reset()


if __name__ == "__main__":
    unittest.main()
