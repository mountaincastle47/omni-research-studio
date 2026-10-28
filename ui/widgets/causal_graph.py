"""Alias module exposing CausalGraphWidget and related items for backwards compatibility."""
from ui.graph_viewer import (
    CausalGraphWidget,
    CausalGraphView,
    _CausalNodeGraphicsItem,
    _CausalEdgeGraphicsItem,
    _CausalEdgeBadgeItem,
    _CausalEdgeLabelGraphicsItem,
)

__all__ = [
    "CausalGraphWidget",
    "CausalGraphView",
    "_CausalNodeGraphicsItem",
    "_CausalEdgeGraphicsItem",
    "_CausalEdgeBadgeItem",
    "_CausalEdgeLabelGraphicsItem",
]

