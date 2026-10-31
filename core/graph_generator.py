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
    blocks = [m.group(1).strip() for m in pattern.finditer(markdown_text or "")]
    if blocks:
        return blocks

    # Fallback heuristic: synthesize a causal diagram from markdown causal arrows or failure sections
    fallback = extract_causal_fallback_mermaid(markdown_text)
    if fallback:
        return [fallback]
    return []


def extract_causal_fallback_mermaid(markdown_text: str) -> str:
    """Extract causal failure chains or arrow patterns from markdown if no explicit mermaid block exists."""
    if not markdown_text or not markdown_text.strip():
        return ""

    lines = markdown_text.splitlines()
    edges: List[Tuple[str, str, str]] = []
    node_labels: Dict[str, str] = {}

    arrow_re = re.compile(r"(?:^|\s*[-*]\s*)(.+?)\s*(?:-->|->|=>|leads to|causes)\s*(.+)", re.IGNORECASE)

    for line in lines:
        line_clean = line.strip()
        m = arrow_re.search(line_clean)
        if m:
            src_raw = re.sub(r"^[#*`\-–\d.\s]+", "", m.group(1)).strip(" *`\"'")
            tgt_raw = re.sub(r"^[#*`\-–\d.\s]+", "", m.group(2)).strip(" *`\"'")
            if src_raw and tgt_raw and len(src_raw) >= 3 and len(tgt_raw) >= 3:
                src_id = f"Node_{len(node_labels) + 1}"
                if src_raw not in node_labels.values():
                    node_labels[src_id] = src_raw[:60]
                else:
                    src_id = next(k for k, v in node_labels.items() if v == src_raw)

                tgt_id = f"Node_{len(node_labels) + 1}"
                if tgt_raw not in node_labels.values():
                    node_labels[tgt_id] = tgt_raw[:60]
                else:
                    tgt_id = next(k for k, v in node_labels.items() if v == tgt_raw)

                edges.append((src_id, tgt_id, "causes"))
                if len(edges) >= 6:
                    break

    if len(edges) >= 2:
        out_lines = ["graph TD"]
        for src_id, tgt_id, rel in edges:
            src_lbl = node_labels.get(src_id, src_id)
            tgt_lbl = node_labels.get(tgt_id, tgt_id)
            out_lines.append(f'  {src_id}["{src_lbl}"] -->|{rel}| {tgt_id}["{tgt_lbl}"]')
        return "\n".join(out_lines)

    return ""


MERMAID_CONTROL_TOKENS = {
    "end",
    "subgraph",
    "graph",
    "flowchart",
    "classdef",
    "class",
    "style",
    "click",
    "linkstyle",
    "direction",
    "sequencediagram",
    "statediagram",
    "classdiagram",
    "erdiagram",
    "gantt",
    "pie",
    "gitgraph",
    "journey",
    "mindmap",
    "timeline",
    "tb",
    "td",
    "lr",
    "rl",
    "bt",
}


def sanitize_node_label(label: str) -> str:
    """Sanitize raw Mermaid node label: convert <br/>, <br>, <br /> to newline, unescape html entities, and clean up whitespace."""
    if not label:
        return ""
    # 1. Replace <br>, <br/>, <br />, <BR>, <BR/> etc. with \n
    cleaned = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", label)
    # 2. HTML unescape
    cleaned = html.unescape(cleaned)
    # 3. Strip surrounding quotation marks often added in Mermaid syntax: ["..."]
    cleaned = cleaned.strip(" '\"")
    # 4. Normalize multiple consecutive spaces per line while preserving \n
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.split("\n")]
    # Strip empty lines from edges but preserve deliberate multi-line breaks
    return "\n".join(lines).strip()


def is_valid_mermaid_node(node_id: str, label: str = "") -> bool:
    """Return True if node_id and label represent valid semantic nodes rather than control tokens."""
    if not node_id or not node_id.strip():
        return False
    clean_id = node_id.strip().lower()
    clean_lbl = label.strip().lower() if label else ""
    if clean_id in MERMAID_CONTROL_TOKENS:
        return False
    if clean_lbl in MERMAID_CONTROL_TOKENS:
        return False
    return True


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

    # Node pattern supporting ["..."], [...], ("..."), (...), {"..."}, {...} without stripping closing ]
    NODE_PART = r'([a-zA-Z0-9_-]+)(?:\["(.*?)"\]|\[(.*?)\]|\("(.*?)"\)|\((.*?)\)|\{"(.*?)"\}|\{(.*?)\})?'
    edge_pattern = re.compile(
        rf'{NODE_PART}\s*(-+>|---|==>|-.->)\s*(?:\|([^|]+)\|)?\s*{NODE_PART}'
    )
    node_only_pattern = re.compile(
        rf'^\s*{NODE_PART}\s*$'
    )

    for raw_line in lines:
        line = raw_line.strip()
        lower_line = line.lower()
        if (
            not line
            or line.startswith("%%")
            or lower_line.startswith("graph")
            or lower_line.startswith("flowchart")
            or lower_line.startswith("subgraph")
            or lower_line == "end"
            or lower_line.startswith("classdef")
            or lower_line.startswith("class ")
            or lower_line.startswith("style")
            or lower_line.startswith("click")
            or lower_line.startswith("linkstyle")
            or lower_line.startswith("direction")
        ):
            continue

        matched_edge = False
        for m in edge_pattern.finditer(line):
            matched_edge = True
            g = m.groups()
            src_id = g[0].strip()
            src_label = sanitize_node_label(next((x.strip() for x in g[1:7] if x is not None), src_id) or src_id)
            edge_type = g[7]
            edge_label = (g[8] or "").strip()
            tgt_id = g[9].strip()
            tgt_label = sanitize_node_label(next((x.strip() for x in g[10:16] if x is not None), tgt_id) or tgt_id)

            if not is_valid_mermaid_node(src_id, src_label) or not is_valid_mermaid_node(tgt_id, tgt_label):
                continue

            if src_id not in graph.nodes:
                graph.nodes[src_id] = MermaidNode(src_id, src_label)
            elif src_label != src_id and graph.nodes[src_id].label == src_id:
                graph.nodes[src_id].label = src_label

            if tgt_id not in graph.nodes:
                graph.nodes[tgt_id] = MermaidNode(tgt_id, tgt_label)
            elif tgt_label != tgt_id and graph.nodes[tgt_id].label == tgt_id:
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
                g = m_node.groups()
                n_id = g[0].strip()
                n_lbl = sanitize_node_label(next((x.strip() for x in g[1:7] if x is not None), n_id) or n_id)
                if is_valid_mermaid_node(n_id, n_lbl):
                    if n_id not in graph.nodes:
                        graph.nodes[n_id] = MermaidNode(n_id, n_lbl)

    return graph


def render_mermaid_to_svg(
    mermaid_code: str,
    width: int = 860,
    node_width: int = 240,
    node_height: int = 72,
) -> str:
    """
    Generate clean, standalone vector SVG from Mermaid diagram definition.
    Renders top-down (TD) or left-to-right (LR) topology with clickable anchor tags
    and spacious node separation (minimum 140px horizontal and 90px vertical).
    """
    graph = parse_mermaid_code(mermaid_code)
    if not graph.nodes:
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            'version="1.1" width="600" height="120" viewBox="0 0 600 120">\n'
            '<rect width="100%" height="100%" fill="#0B0F19"/>\n'
            '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#94A3B8" font-size="14">\n'
            'No valid Mermaid causal graph nodes detected in synthesis report.\n'
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

    # Calculate layout positions with generous separation
    h_sep = 150
    v_sep = 100
    max_layer_count = max(len(l) for l in layers) if layers else 1

    if not is_horizontal:
        actual_width = max(width, max_layer_count * (node_width + h_sep) + 120)
        svg_height = max(400, len(layers) * (node_height + v_sep) + 120)
    else:
        actual_width = max(width, len(layers) * (node_width + h_sep) + 120)
        svg_height = max(400, max_layer_count * (node_height + v_sep) + 120)

    for layer_idx, layer_nodes in enumerate(layers):
        count = len(layer_nodes)
        for node_idx, n_id in enumerate(layer_nodes):
            if not is_horizontal:
                total_w = count * node_width + (count - 1) * h_sep
                start_x = (actual_width - total_w) // 2
                x = start_x + node_idx * (node_width + h_sep)
                y = 60 + layer_idx * (node_height + v_sep)
            else:
                total_h = count * node_height + (count - 1) * v_sep
                start_y = (svg_height - total_h) // 2
                x = 60 + layer_idx * (node_width + h_sep)
                y = start_y + node_idx * (node_height + v_sep)
            node_coords[n_id] = (x, y)

    # Build SVG XML elements
    svg_parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="{actual_width}" height="{svg_height}" viewBox="0 0 {actual_width} {svg_height}">',
        '<defs>',
        '  <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">',
        '    <polygon points="0 0, 10 3.5, 0 7" fill="#38BDF8"/>',
        '  </marker>',
        '  <filter id="dropshadow" x="-10%" y="-10%" width="120%" height="120%">',
        '    <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000000" flood-opacity="0.5"/>',
        '  </filter>',
        '</defs>',
        '<rect width="100%" height="100%" fill="#0B0F19" rx="8"/>',
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
                f'<path d="M {start_x} {start_y} L {end_x} {end_y}" '
                f'stroke="#38BDF8" stroke-width="2" fill="none" opacity="0.85" {marker}/>'
            )

            if edge.label:
                lbl_escaped = html.escape(edge.label)
                svg_parts.append(
                    f'<rect x="{mid_x - 40}" y="{mid_y - 10}" width="80" height="20" fill="#0F172A" rx="4" opacity="0.95" stroke="#334155" stroke-width="1"/>'
                    f'<text x="{mid_x}" y="{mid_y + 4}" fill="#94A3B8" font-size="10" font-family="-apple-system, sans-serif" text-anchor="middle">{lbl_escaped}</text>'
                )

    # Draw Nodes
    for n_id, (nx, ny) in node_coords.items():
        node = graph.nodes[n_id]
        clean_lbl = sanitize_node_label(node.label or n_id)
        raw_lines = clean_lbl.split("\n")
        lines_wrap: List[str] = []
        for rline in raw_lines:
            words = rline.split()
            cur_line = ""
            for w in words:
                if not cur_line:
                    cur_line = w
                elif len(cur_line) + len(w) + 1 <= 28:
                    cur_line += " " + w
                else:
                    lines_wrap.append(cur_line)
                    cur_line = w
            if cur_line:
                lines_wrap.append(cur_line)

        if not lines_wrap:
            lines_wrap = [clean_lbl]

        this_node_h = max(node_height, len(lines_wrap) * 20 + 28)
        svg_parts.append(f'<a xlink:href="node:{n_id}" target="_top" style="cursor: pointer;">')
        svg_parts.append(
            f'<rect x="{nx}" y="{ny}" width="{node_width}" height="{this_node_h}" '
            f'rx="10" fill="#0F172A" stroke="#38BDF8" stroke-width="2" filter="url(#dropshadow)"/>'
        )

        start_text_y = ny + (this_node_h - len(lines_wrap) * 18) // 2 + 12
        for line_idx, line_txt in enumerate(lines_wrap):
            esc_txt = html.escape(line_txt)
            fill_col = "#F8FAFC" if line_idx == 0 else "#94A3B8"
            f_size = "11" if len(lines_wrap) > 2 else ("12" if len(lines_wrap) == 1 else "11")
            svg_parts.append(
                f'<text x="{nx + node_width // 2}" y="{start_text_y + line_idx * 18}" '
                f'fill="{fill_col}" font-size="{f_size}" font-weight="600" font-family="-apple-system, sans-serif" text-anchor="middle">{esc_txt}</text>'
            )
        svg_parts.append('</a>')

    svg_parts.append('</svg>')
    return "\n".join(svg_parts)


def normalize_svg_xml(svg_text: str, width: int, height: int) -> str:
    """Normalize SVG string to strict W3C SVG 1.1 specification with positive (0,0) origin and valid XML."""
    if not svg_text:
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'version="1.1" width="{width}px" height="{height}px" viewBox="0 0 {width} {height}">\n'
            f'<rect width="100%" height="100%" fill="#0d1117"/>\n'
            '</svg>'
        )

    # 1. Strip BOM, XML prolog, DOCTYPE, and illegal XML control characters
    clean_svg = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', svg_text, flags=re.DOTALL)
    clean_svg = re.sub(r'<!DOCTYPE[^>]*>\s*', '', clean_svg, flags=re.DOTALL)
    clean_svg = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', clean_svg)

    # 2. Extract and rewrite <svg ...> root tag
    svg_tag_match = re.search(r'<svg\b([^>]*)>', clean_svg, flags=re.IGNORECASE)
    if not svg_tag_match:
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'version="1.1" width="{width}px" height="{height}px" viewBox="0 0 {width} {height}">\n'
            f'<rect width="100%" height="100%" fill="#0d1117"/>\n'
            '</svg>'
        )

    attrs = svg_tag_match.group(1)

    # Strip legacy/conflicting attributes
    attrs = re.sub(r'\bversion="[^"]*"', '', attrs)
    attrs = re.sub(r'\bbaseProfile="[^"]*"', '', attrs)
    attrs = re.sub(r'\bwidth="[^"]*"', '', attrs)
    attrs = re.sub(r'\bheight="[^"]*"', '', attrs)
    attrs = re.sub(r'\bviewBox="[^"]*"', '', attrs)
    attrs = re.sub(r'\bxmlns="[^"]*"', '', attrs)
    attrs = re.sub(r'\bxmlns:xlink="[^"]*"', '', attrs)

    attrs = " ".join(attrs.split())

    new_svg_tag = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'version="1.1" '
        f'width="{width}px" height="{height}px" '
        f'viewBox="0 0 {width} {height}"'
    )
    if attrs:
        new_svg_tag += f' {attrs}'
    new_svg_tag += '>'

    clean_svg = clean_svg[:svg_tag_match.start()] + new_svg_tag + clean_svg[svg_tag_match.end():]

    # 3. Sanitize text tags: convert raw <br> or <br/> into <tspan> elements with explicit x and dy
    def _fix_text_tag(match: re.Match) -> str:
        tag_open = match.group(1)
        content = match.group(2)
        tag_close = match.group(3)

        if re.search(r'<\s*br\s*/?\s*>', content, flags=re.IGNORECASE):
            x_match = re.search(r'\bx="([^"]+)"', tag_open)
            x_val = x_match.group(1) if x_match else "0"
            lines = re.split(r'<\s*br\s*/?\s*>', content, flags=re.IGNORECASE)
            tspan_parts = []
            for idx, line in enumerate(lines):
                line_clean = line.strip()
                if not line_clean:
                    continue
                dy = "0" if idx == 0 else "1.2em"
                tspan_parts.append(f'<tspan x="{x_val}" dy="{dy}">{line_clean}</tspan>')
            return f'{tag_open}{"".join(tspan_parts)}{tag_close}'
        return f'{tag_open}{content}{tag_close}'

    clean_svg = re.sub(r'(<text\b[^>]*>)(.*?)(</text>)', _fix_text_tag, clean_svg, flags=re.DOTALL | re.IGNORECASE)
    # Strip any stray <br> tags outside text elements
    clean_svg = re.sub(r'<\s*br\s*/?\s*>', '', clean_svg, flags=re.IGNORECASE)

    # 4. Standardize numeric character references into standard named XML entities
    clean_svg = re.sub(r'&#38;|&#x26;', '&amp;', clean_svg, flags=re.IGNORECASE)
    clean_svg = re.sub(r'&#60;|&#x3c;', '&lt;', clean_svg, flags=re.IGNORECASE)
    clean_svg = re.sub(r'&#62;|&#x3e;', '&gt;', clean_svg, flags=re.IGNORECASE)
    clean_svg = re.sub(r'&#34;|&#x22;', '&quot;', clean_svg, flags=re.IGNORECASE)
    clean_svg = re.sub(r'&#39;|&#x27;', '&apos;', clean_svg, flags=re.IGNORECASE)

    # 5. Strictly escape ALL bare ampersands across the entire SVG document (both in text and attributes)
    clean_svg = re.sub(r'&(?!(?:amp|lt|gt|quot|apos);)', '&amp;', clean_svg)

    final_svg = f'<?xml version="1.0" encoding="utf-8"?>\n{clean_svg.strip()}'

    # 6. Strict XML validation via ElementTree
    try:
        import xml.etree.ElementTree as ET
        ET.fromstring(final_svg)
    except Exception:
        # Programmatic correction: ensure standard XML structure
        try:
            # If a trailing closing tag was missing or mismatched, attempt closing </svg>
            if not final_svg.rstrip().endswith('</svg>'):
                final_svg += '\n</svg>'
            ET.fromstring(final_svg)
        except Exception:
            return (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'version="1.1" width="{width}px" height="{height}px" viewBox="0 0 {width} {height}">\n'
                f'<rect width="100%" height="100%" fill="#0d1117"/>\n'
                '<text x="50%" y="50%" fill="#94A3B8" font-size="16" font-family="sans-serif" text-anchor="middle">Graph Visual</text>\n'
                '</svg>'
            )

    return final_svg
