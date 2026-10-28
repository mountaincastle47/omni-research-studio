"""Cross-Corpus Entity-Relationship Knowledge Graph:
Extracts structured entities and technical relationships across research documents,
and constructs an interactive directed networkx graph.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from core.config import ConfigManager, DEFAULT_SYNTHESIS_MODEL
from core.document_loader import SourceDocument
from core.local_llm_client import is_local_model
from core.synthesis import fast_json_loads

logger = logging.getLogger("OmniKnowledgeGraph")

ENTITY_CATEGORIES = {
    "Organization": "#38BDF8",     # Cyan
    "Program": "#4ADE80",          # Emerald
    "Key Figure": "#F472B6",       # Pink
    "Standard": "#FBBF24",         # Amber
    "Material": "#A78BFA",         # Purple
    "Concept": "#94A3B8",          # Slate
}

ENTITY_EXTRACTION_PROMPT = """You are an Expert Technical Knowledge Graph Extractor.
Extract the key technical entities and their explicit relationships from the document excerpt below.
Categorize each entity strictly into one of:
- Organization (e.g., NASA, DARPA, Lockheed Martin, TSMC, OpenAI)
- Program (e.g., Apollo, Starship, F-35, GPT-4, ITER)
- Key Figure (e.g., von Braun, Oppenheimer, Elon Musk, Jensen Huang)
- Standard (e.g., IEEE-802.11, MIL-STD-810H, ISO-9001, DO-178C)
- Material (e.g., Inconel 718, Silicon Carbide, Gallium Nitride, Carbon Fiber)
- Concept (e.g., Quantum Entanglement, Thermal Throttling, Zero-Knowledge Proof)

Format output strictly as valid JSON matching this schema:
{{
  "entities": [
    {{"name": "NASA", "category": "Organization", "description": "United States civilian space agency"}},
    {{"name": "Artemis", "category": "Program", "description": "Lunar exploration initiative"}}
  ],
  "relations": [
    {{
      "source": "NASA",
      "target": "Artemis",
      "relation": "leads",
      "premise": "NASA directs the multinational Artemis lunar program"
    }}
  ]
}}

Document excerpt (Citation ID: [{cite_id}]):
\"\"\"
{text}
\"\"\"
"""


def clean_and_parse_json(raw_text: str) -> Dict[str, Any]:
    """Clean and parse JSON from LLM output with markdown code fence stripping and regex fallback."""
    if not raw_text or not raw_text.strip():
        return {}

    text = raw_text.strip()

    # 1. Strip markdown code fences ```json ... ``` or ``` ... ```
    match_fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match_fence:
        text = match_fence.group(1).strip()

    # 2. Try direct fast_json_loads
    try:
        data = fast_json_loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 3. Find outermost JSON object {...}
    match_braces = re.search(r"(\{[\s\S]*\})", text)
    if match_braces:
        try:
            data = fast_json_loads(match_braces.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 4. Fallback regex extraction for entities and relations
    entities: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []

    ent_pattern = re.compile(
        r'\{[^{}]*?"name"\s*:\s*"([^"]+)"[^{}]*?"category"\s*:\s*"([^"]+)"(?:[^{}]*?"description"\s*:\s*"([^"]*)")?[^{}]*?\}',
        re.DOTALL,
    )
    for m in ent_pattern.finditer(raw_text):
        entities.append({
            "name": m.group(1).strip(),
            "category": m.group(2).strip(),
            "description": (m.group(3) or "").strip(),
        })

    rel_pattern = re.compile(
        r'\{[^{}]*?"source"\s*:\s*"([^"]+)"[^{}]*?"target"\s*:\s*"([^"]+)"[^{}]*?"relation"\s*:\s*"([^"]+)"(?:[^{}]*?"premise"\s*:\s*"([^"]*)")?[^{}]*?\}',
        re.DOTALL,
    )
    for m in rel_pattern.finditer(raw_text):
        relations.append({
            "source": m.group(1).strip(),
            "target": m.group(2).strip(),
            "relation": m.group(3).strip(),
            "premise": (m.group(4) or "").strip(),
        })

    if entities or relations:
        return {"entities": entities, "relations": relations}

    return {}


class KnowledgeGraphEngine:
    """Manages directed networkx knowledge graph of cross-corpus entities and relationships."""

    def __init__(self, config_manager: Optional[ConfigManager] = None) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.graph = nx.DiGraph()

    def clear(self) -> None:
        """Reset the knowledge graph."""
        self.graph.clear()

    def add_entity(
        self,
        name: str,
        category: str = "Concept",
        description: str = "",
        cite_id: Optional[int] = None,
    ) -> str:
        """Add or update an entity node in the graph."""
        clean_name = name.strip()
        node_id = clean_name.lower()
        if not node_id:
            return ""

        if self.graph.has_node(node_id):
            node_data = self.graph.nodes[node_id]
            if cite_id is not None and cite_id not in node_data.get("citations", []):
                node_data.setdefault("citations", []).append(cite_id)
            if description and not node_data.get("description"):
                node_data["description"] = description
        else:
            cat = category if category in ENTITY_CATEGORIES else "Concept"
            self.graph.add_node(
                node_id,
                name=clean_name,
                category=cat,
                color=ENTITY_CATEGORIES.get(cat, "#94A3B8"),
                description=description,
                citations=[cite_id] if cite_id is not None else [],
            )
        return node_id

    def add_relation(
        self,
        source_name: str,
        target_name: str,
        relation: str,
        premise: str = "",
        cite_id: Optional[int] = None,
    ) -> bool:
        """Add a directed relationship between two entities."""
        src_id = self.add_entity(source_name, cite_id=cite_id)
        dst_id = self.add_entity(target_name, cite_id=cite_id)

        if not src_id or not dst_id or src_id == dst_id:
            return False

        self.graph.add_edge(
            src_id,
            dst_id,
            relation=relation.strip() or "related_to",
            premise=premise.strip(),
            cite_id=cite_id,
        )
        return True

    def extract_from_text(
        self,
        text: str,
        cite_id: int = 1,
        model_name: str = DEFAULT_SYNTHESIS_MODEL,
        use_llm: bool = True,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extract entities and relations using LLM, with deterministic regex fallback."""
        if not text or not text.strip():
            return [], []

        if not use_llm:
            return self._heuristic_extract(text, cite_id=cite_id)

        api_key = self.config_manager.get_api_key()
        if api_key and not is_local_model(model_name):
            try:
                from google.genai import types

                client = self.config_manager.create_client(api_key=api_key)
                sample_text = text[:4000]
                prompt = ENTITY_EXTRACTION_PROMPT.format(text=sample_text, cite_id=cite_id)

                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        response_mime_type="application/json",
                        http_options=types.HttpOptions(timeout=15000.0),
                    ),
                )
                raw_json = getattr(response, "text", "") or "{}"
                data = clean_and_parse_json(raw_json)
                entities = data.get("entities", [])
                relations = data.get("relations", [])

                if entities:
                    for e in entities:
                        self.add_entity(
                            name=e.get("name", ""),
                            category=e.get("category", "Concept"),
                            description=e.get("description", ""),
                            cite_id=cite_id,
                        )
                    for r in relations:
                        self.add_relation(
                            source_name=r.get("source", ""),
                            target_name=r.get("target", ""),
                            relation=r.get("relation", "connected_to"),
                            premise=r.get("premise", ""),
                            cite_id=cite_id,
                        )
                    return entities, relations

            except Exception as exc:
                logger.warning(f"LLM entity extraction failed: {exc}. Using heuristic fallback.")

        # Heuristic Rule-Based Fallback Extractor
        return self._heuristic_extract(text, cite_id=cite_id)

    def _heuristic_extract(self, text: str, cite_id: int = 1) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Fast regex heuristic extraction of common organizations, standards, and technical terms."""
        entities: List[Dict[str, Any]] = []
        relations: List[Dict[str, Any]] = []

        # 1. Known technical standards pattern (e.g. ISO-9001, IEEE 802.11, MIL-STD-810)
        std_matches = set(re.findall(r"\b(?:ISO|IEEE|MIL-STD|DO|RFC|ECMA|ANSI|NIST)[-\s][\dA-Z.-]+\b", text))
        for m in std_matches:
            self.add_entity(m, category="Standard", description="Technical standard specification", cite_id=cite_id)
            entities.append({"name": m, "category": "Standard"})

        # 2. Capitalized multi-word organization / program phrases
        cap_phrases = set(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b", text))
        for p in list(cap_phrases)[:12]:
            if any(stop in p.lower() for stop in ["this is", "the following", "in order", "furthermore", "according to", "based on", "table of"]):
                continue
            cat = "Organization" if any(w in p for w in ["Lab", "Institute", "Corp", "Inc", "Agency", "Group", "Dept", "Force", "Consortium"]) else "Program"
            self.add_entity(p, category=cat, description=f"Entity identified in document [{cite_id}]", cite_id=cite_id)
            entities.append({"name": p, "category": cat})

        # 3. Bold technical concepts in synthesis or notes: **Term**
        bold_terms = set(re.findall(r"\*\*([A-Za-z0-9\s_-]{3,35})\*\*", text))
        for b in list(bold_terms)[:10]:
            clean_b = b.strip()
            if clean_b and not any(e["name"].lower() == clean_b.lower() for e in entities):
                self.add_entity(clean_b, category="Concept", description=f"Technical concept emphasized in [{cite_id}]", cite_id=cite_id)
                entities.append({"name": clean_b, "category": "Concept"})

        # Relate pairs if multiple entities found
        ent_names = [e["name"] for e in entities]
        for i in range(len(ent_names) - 1):
            src = ent_names[i]
            dst = ent_names[i + 1]
            self.add_relation(src, dst, relation="associated_with", premise=f"Co-occurred in [{cite_id}]", cite_id=cite_id)
            relations.append({"source": src, "target": dst, "relation": "associated_with"})

        return entities, relations

    def build_from_documents(self, documents: List[SourceDocument], use_llm: bool = False) -> None:
        """Batch construct knowledge graph from a list of corpus documents."""
        self.clear()
        for doc in documents:
            if getattr(doc, "enabled", True) and doc.content:
                self.extract_from_text(doc.content, cite_id=getattr(doc, "cite_id", 1), use_llm=use_llm)

    def build_from_synthesis(self, report_markdown: str, use_llm: bool = False) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extract and add entities directly from synthesis report markdown."""
        return self.extract_from_text(report_markdown, cite_id=1, use_llm=use_llm)

    def get_nodes_data(self) -> List[Dict[str, Any]]:
        """Return all node metadata for UI rendering."""
        nodes: List[Dict[str, Any]] = []
        for node_id, data in self.graph.nodes(data=True):
            nodes.append({
                "id": node_id,
                "name": data.get("name", node_id),
                "category": data.get("category", "Concept"),
                "color": data.get("color", "#94A3B8"),
                "description": data.get("description", ""),
                "citations": data.get("citations", []),
                "degree": self.graph.degree(node_id),
            })
        return nodes

    def get_edges_data(self) -> List[Dict[str, Any]]:
        """Return all edge metadata for UI rendering."""
        edges: List[Dict[str, Any]] = []
        for u, v, data in self.graph.edges(data=True):
            edges.append({
                "source": u,
                "target": v,
                "relation": data.get("relation", "related_to"),
                "premise": data.get("premise", ""),
                "cite_id": data.get("cite_id"),
            })
        return edges

    def to_dict(self) -> Dict[str, Any]:
        """Serialize knowledge graph to dictionary for persistence."""
        return {
            "nodes": self.get_nodes_data(),
            "edges": self.get_edges_data(),
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Load knowledge graph from serialized dictionary."""
        self.clear()
        for n in data.get("nodes", []):
            self.add_entity(
                name=n.get("name", n.get("id", "")),
                category=n.get("category", "Concept"),
                description=n.get("description", ""),
                cite_id=(n.get("citations", [None]) or [None])[0],
            )
        for e in data.get("edges", []):
            self.add_relation(
                source_name=e.get("source", ""),
                target_name=e.get("target", ""),
                relation=e.get("relation", "related_to"),
                premise=e.get("premise", ""),
                cite_id=e.get("cite_id"),
            )

    def compute_layout_data(self, min_repulsion: float = 120.0) -> Dict[str, Any]:
        """Compute force-directed clustered layout coordinates entirely in background thread.
        Clusters nodes by category with minimum 120px node repulsion to eliminate hairballs."""
        import math

        categories = ["Organization", "Program", "Key Figure", "Standard", "Material", "Concept"]
        if self.graph.number_of_nodes() == 0:
            return {"nodes": [], "edges": []}

        cat_nodes: Dict[str, List[str]] = {c: [] for c in categories}
        all_nodes_data = {}
        for nid, data in self.graph.nodes(data=True):
            cat = data.get("category", "Concept")
            if cat not in cat_nodes:
                cat = "Concept"
            cat_nodes[cat].append(nid)
            all_nodes_data[nid] = data

        pos: Dict[str, List[float]] = {}
        r_cluster = 320.0
        for i, cat in enumerate(categories):
            ang = i * (2.0 * math.pi / len(categories))
            cx = r_cluster * math.cos(ang)
            cy = r_cluster * math.sin(ang)
            c_list = cat_nodes[cat]
            if not c_list:
                continue
            if len(c_list) == 1:
                pos[c_list[0]] = [cx, cy]
            else:
                for j, nid in enumerate(c_list):
                    lang = j * (2.0 * math.pi / len(c_list))
                    r_local = max(80.0, len(c_list) * 25.0)
                    pos[nid] = [cx + r_local * math.cos(lang), cy + r_local * math.sin(lang)]

        # Force-directed relaxation (repulsion + edge attraction)
        node_keys = list(pos.keys())
        for _ in range(40):
            # Repulsion
            for a in range(len(node_keys)):
                u = node_keys[a]
                for b in range(a + 1, len(node_keys)):
                    v = node_keys[b]
                    dx = pos[u][0] - pos[v][0]
                    dy = pos[u][1] - pos[v][1]
                    dist = math.hypot(dx, dy)
                    if dist < min_repulsion:
                        d = max(dist, 1.0)
                        ov = (min_repulsion - dist) / d * 0.5
                        pos[u][0] += dx * ov
                        pos[u][1] += dy * ov
                        pos[v][0] -= dx * ov
                        pos[v][1] -= dy * ov

            # Edge spring attraction
            for u, v in self.graph.edges():
                if u in pos and v in pos:
                    dx = pos[v][0] - pos[u][0]
                    dy = pos[v][1] - pos[u][1]
                    dist = math.hypot(dx, dy)
                    if dist > 180.0:
                        pull = (dist - 180.0) * 0.04
                        pull_x = (dx / max(dist, 1.0)) * pull
                        pull_y = (dy / max(dist, 1.0)) * pull
                        pos[u][0] += pull_x
                        pos[u][1] += pull_y
                        pos[v][0] -= pull_x
                        pos[v][1] -= pull_y

        # Build output structure
        out_nodes: List[Dict[str, Any]] = []
        for nid, (x, y) in pos.items():
            d = all_nodes_data.get(nid, {})
            cat = d.get("category", "Concept")
            out_nodes.append({
                "id": nid,
                "name": d.get("name", nid),
                "category": cat,
                "color": d.get("color", ENTITY_CATEGORIES.get(cat, "#94A3B8")),
                "description": d.get("description", ""),
                "citations": d.get("citations", []),
                "degree": self.graph.degree(nid),
                "x": round(x, 1),
                "y": round(y, 1),
            })

        out_edges: List[Dict[str, Any]] = []
        for u, v, data in self.graph.edges(data=True):
            if u in pos and v in pos:
                out_edges.append({
                    "source": u,
                    "target": v,
                    "relation": data.get("relation", "related_to"),
                    "premise": data.get("premise", ""),
                    "cite_id": data.get("cite_id"),
                    "x1": round(pos[u][0], 1),
                    "y1": round(pos[u][1], 1),
                    "x2": round(pos[v][0], 1),
                    "y2": round(pos[v][1], 1),
                })

        return {"nodes": out_nodes, "edges": out_edges}


