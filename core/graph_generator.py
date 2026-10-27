"""Visual Causal & Argument Graph Mapping: Mermaid syntax parser and standalone SVG renderer."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class MermaidNode:
    """Represents a node in a Mermaid diagram."""

    node_id: str
    label: str
    shape: str = "box"  # "box", "rounded", "circle"


@dataclass
class MermaidEdge:
    """Represents a directed or undirected connection between two nodes."""

    source_id: str
    target_id: str
    label: str = ""
    arrow: bool = True


@dataclass
class ParsedMermaidGraph:
    """Structured representation of a parsed Mermaid diagram."""

    direction: str = "TD"  # "TD", "TB", "LR"
    nodes: Dict[str, MermaidNode] = field(default_factory=dict)
    edges: List[MermaidEdge] = field(default_factory=list)


def extract_mermaid_blocks(markdown_text: str) -> List[str]:
    """Extract all ```mermaid blocks from a Markdown text."""
    pattern = re.compile(r"```mermaid\s*([\s\S]*?)\s*```", re.IGNORECASE)
    return [m.group(1).strip() for m in pattern.finditer(markdown_text or "")]


def parse_mermaid_code(code: str) -> ParsedMermaidGraph:
    """Parse graph TD / LR Mermaid diagram definitions into structured nodes and edges."""
    lines = code.strip().splitlines()
    graph = ParsedMermaidGraph()

    # Detect direction
    first_line = lines[0].strip() if lines else ""
    if "graph" in first_line or "flowchart" in first_line:
        parts = first_line.split()
        if len(parts) >= 2:
            graph.direction = parts[1].upper()

    edge_pattern = re.compile(
        r"([a-zA-Z0-9_-]+)(?:\[\"?([^\"]*?)\"?\]|\(\"?([^\"]*?)\"?\))?\s*(-+>|---|==>|-.->)\s*(?:\|([^|]+)\|)?\s*([a-zA-Z0-9_-]+)(?:\[\"?([^\"]*?)\"?\]|\(\"?([^\"]*?)\"?\))?"
    )

    node_only_pattern = re.compile(
        r"([a-zA-Z0-9_-]+)(?:\[\"?([^\"]*?)\"?\]|\(\"?([^\"]*?)\"?\))"
    )

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("%%") or line.startswith("graph") or line.startswith("flowchart"):
            continue

        matched_edge = False
        for m in edge_pattern.finditer(line):
            matched_edge = True
            src_id = m.group(1).strip()
            src_label = (m.group(2) or m.group(3) or src_id).strip()
            edge_type = m.group(4)
            edge_label = (m.group(5) or "").strip()
            tgt_id = m.group(6).strip()
            tgt_label = (m.group(7) or m.group(8) or tgt_id).strip()

            if src_id not in graph.nodes:
                graph.nodes[src_id] = MermaidNode(src_id, src_label)
            elif src_label != src_id:
                graph.nodes[src_id].label = src_label

            if tgt_id not in graph.nodes:
                graph.nodes[tgt_id] = MermaidNode(tgt_id, tgt_label)
            elif tgt_label != tgt_id:
                graph.nodes[tgt_id].label = tgt_label

            graph.edges.append(
                MermaidEdge(
                    source_id=src_id,
                    target_id=tgt_id,
                    label=edge_label,
                    arrow=">" in edge_type,
                )
            )

        if not matched_edge:
            m_node = node_only_pattern.match(line)
            if m_node:
                n_id = m_node.group(1).strip()
                n_lbl = (m_node.group(2) or m_node.group(3) or n_id).strip()
                if n_id not in graph.nodes:
                    graph.nodes[n_id] = MermaidNode(n_id, n_lbl)

    return graph


def render_mermaid_to_svg(
    mermaid_code: str,
    width: int = 860,
    node_width: int = 190,
    node_height: int = 56,
) -> str:
    """
    Generate clean, standalone vector SVG from Mermaid diagram definition.
    Renders top-down (TD) or left-to-right (LR) topology with clickable anchor tags.
    """
    graph = parse_mermaid_code(mermaid_code)
    if not graph.nodes:
        return (
            '<svg xmlns="http://www.w3.org/2005/svg" width="600" height="120">'
            '<rect width="100%" height="100%" fill="#0B0F19"/>'
            '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#94A3B8" font-size="14">'
            'No valid Mermaid causal graph nodes detected in synthesis report.'
            '</text></svg>'
        )

    node_list = list(graph.nodes.values())
    node_coords: Dict[str, Tuple[int, int]] = {}

    is_horizontal = graph.direction in ("LR", "RL")

    # Simple topological layer assignment
    in_degree: Dict[str, int] = {n.node_id: 0 for n in node_list}
    children_map: Dict[str, List[str]] = {n.node_id: [] for n in node_list}
    for e in graph.edges:
        if e.target_id in in_degree:
            in_degree[e.target_id] += 1
        if e.source_id in children_map:
            children_map[e.source_id].append(e.target_id)

    layers: List[List[str]] = []
    current_layer = [n_id for n_id, deg in in_degree.items() if deg == 0]
    if not current_layer:
        current_layer = [node_list[0].node_id]

    visited = set(current_layer)
    layers.append(current_layer)

    while True:
        next_layer: List[str] = []
        for n_id in layers[-1]:
            for ch in children_map.get(n_id, []):
                if ch not in visited:
                    visited.add(ch)
                    next_layer.append(ch)
        if not next_layer:
            break
        layers.append(next_layer)

    # Append any unvisited nodes to the last layer
    remaining = [n.node_id for n in node_list if n.node_id not in visited]
    if remaining:
        layers.append(remaining)

    # Calculate layout positions
    svg_height = max(400, len(layers) * 120 + 80) if not is_horizontal else max(400, max(len(l) for l in layers) * 100 + 80)
    actual_width = max(width, max(len(l) for l in layers) * (node_width + 40) + 80) if not is_horizontal else max(width, len(layers) * (node_width + 80) + 80)

    for layer_idx, layer_nodes in enumerate(layers):
        count = len(layer_nodes)
        for node_idx, n_id in enumerate(layer_nodes):
            if not is_horizontal:
                x = int((actual_width / (count + 1)) * (node_idx + 1) - (node_width / 2))
                y = 50 + layer_idx * 110
            else:
                x = 50 + layer_idx * (node_width + 80)
                y = int((svg_height / (count + 1)) * (node_idx + 1) - (node_height / 2))
            node_coords[n_id] = (x, y)

    # Build SVG XML elements
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2005/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{actual_width}" height="{svg_height}" viewBox="0 0 {actual_width} {svg_height}">',
        '<defs>',
        '  <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">',
        '    <polygon points="0 0, 10 3.5, 0 7" fill="#38BDF8"/>',
        '  </marker>',
        '  <filter id="dropshadow" x="-10%" y="-10%" width="120%" height="120%">',
        '    <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000000" flood-opacity="0.5"/>',
        '  </filter>',
        '</defs>',
        f'<rect width="100%" height="100%" fill="#0B0F19" rx="8"/>',
    ]

    # Draw Edges
    for edge in graph.edges:
        if edge.source_id in node_coords and edge.target_id in node_coords:
            sx, sy = node_coords[edge.source_id]
            tx, ty = node_coords[edge.target_id]

            if not is_horizontal:
                start_x, start_y = sx + node_width // 2, sy + node_height
                end_x, end_y = tx + node_width // 2, ty
            else:
                start_x, start_y = sx + node_width, sy + node_height // 2
                end_x, end_y = tx, ty + node_height // 2

            marker = 'marker-end="url(#arrowhead)"' if edge.arrow else ""
            mid_x, mid_y = (start_x + end_x) // 2, (start_y + end_y) // 2

            svg_parts.append(
                f'<path d="M {start_x} {start_y} Q {mid_x} {start_y + 15} {end_x} {end_y}" '
                f'stroke="#38BDF8" stroke-width="2" fill="none" opacity="0.85" {marker}/>'
            )

            if edge.label:
                lbl_escaped = html.escape(edge.label)
                svg_parts.append(
                    f'<rect x="{mid_x - 35}" y="{mid_y - 10}" width="70" height="18" fill="#0F172A" rx="4" opacity="0.9"/>'
                    f'<text x="{mid_x}" y="{mid_y + 3}" fill="#94A3B8" font-size="10" font-family="-apple-system, sans-serif" text-anchor="middle">{lbl_escaped}</text>'
                )

    # Draw Nodes
    for n_id, (nx, ny) in node_coords.items():
        node = graph.nodes[n_id]
        label_escaped = html.escape(node.label or n_id)
        if len(label_escaped) > 28:
            label_lines = [label_escaped[:26] + "-", label_escaped[26:52]]
        else:
            label_lines = [label_escaped]

        svg_parts.append(f'<a xlink:href="node:{n_id}" target="_top" style="cursor: pointer;">')
        svg_parts.append(
            f'<rect x="{nx}" y="{ny}" width="{node_width}" height="{node_height}" '
            f'rx="8" fill="#1E293B" stroke="#38BDF8" stroke-width="1.8" filter="url(#dropshadow)"/>'
        )

        if len(label_lines) == 1:
            svg_parts.append(
                f'<text x="{nx + node_width // 2}" y="{ny + node_height // 2 + 5}" '
                f'fill="#F8FAFC" font-size="12" font-weight="600" font-family="-apple-system, sans-serif" text-anchor="middle">{label_lines[0]}</text>'
            )
        else:
            svg_parts.append(
                f'<text x="{nx + node_width // 2}" y="{ny + 22}" '
                f'fill="#F8FAFC" font-size="11" font-weight="600" font-family="-apple-system, sans-serif" text-anchor="middle">{label_lines[0]}</text>'
                f'<text x="{nx + node_width // 2}" y="{ny + 40}" '
                f'fill="#94A3B8" font-size="11" font-family="-apple-system, sans-serif" text-anchor="middle">{label_lines[1]}</text>'
            )
        svg_parts.append('</a>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)
