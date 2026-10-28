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

# Standard bilingual technical relation vocabulary
KG_RELATION_TRANSLATIONS: Dict[str, str] = {
    "developed_by": "개발됨",
    "developed by": "개발됨",
    "tested_at": "시험됨",
    "tested at": "시험됨",
    "failed_due_to": "실패 원인임",
    "failed due to": "실패 원인임",
    "superseded_by": "대체됨",
    "superseded by": "대체됨",
    "incorporates": "통합/적용함",
    "competes_with": "경쟁함",
    "competes with": "경쟁함",
    "procured_by": "도입/조달됨",
    "procured by": "도입/조달됨",
    "evaluated_by": "평가됨",
    "evaluated by": "평가됨",
    "evaluates": "평가함",
    "complies_with": "준수함",
    "complies with": "준수함",
    "operated_by": "운용됨",
    "operated by": "운용됨",
    "associated_with": "연관됨",
    "associated with": "연관됨",
    "identifies": "식별함",
    "identified_by": "식별됨",
    "precedes": "선행함",
    "causes": "원인임",
    "caused_by": "유발됨",
    "leads": "이끔",
    "leads_to": "초래함",
    "leads to": "초래함",
    "depends_on": "의존함",
    "depends on": "의존함",
    "defines": "정의함",
    "defined_by": "정의됨",
    "implements": "구현함",
    "implemented_by": "구현됨",
    "synthesizes": "종합함",
    "synthesizes_the": "종합함",
    "synthesizes the": "종합함",
    "enables": "가능하게 함",
    "requires": "필요로 함",
    "required_by": "요구됨",
    "triggers": "유발함",
    "triggered_by": "촉발됨",
    "validates": "검증함",
    "validated_by": "검증됨",
    "correlates_with": "상관관계 있음",
    "correlates with": "상관관계 있음",
    "regulates": "규제/조절함",
    "regulated_by": "규제됨",
    "influences": "영향을 미침",
    "influenced_by": "영향 받음",
    "connected_to": "연결됨",
    "connected to": "연결됨",
    "constrains": "제약함",
    "constrained_by": "제약됨",
    "inhibits": "억제함",
    "accelerates": "가속화함",
    "produces": "생성함",
    "produced_by": "생성됨",
    "derived_from": "유래됨",
    "part_of": "일부임",
    "part of": "일부임",
    "contains": "포함함",
    "contained_in": "포함됨",
    "subclass_of": "하위 분류임",
    "instance_of": "인스턴스임",
    "monitors": "모니터링함",
    "mitigates": "완화함",
    "escalates": "악화시킴",
    "results_in": "결과로 이어짐",
    "supports": "지원함",
    "supported_by": "지원받음",
    "replaces": "대체함",
    "improves": "개선함",
    "degrades": "저하시킴",
    "related_to": "관련됨",
    "related to": "관련됨",
}

KG_RELATION_REVERSE: Dict[str, str] = {v: k for k, v in KG_RELATION_TRANSLATIONS.items()}

DISALLOWED_START_WORDS = {
    "while", "hence", "therefore", "furthermore", "however", "although", "the", "a", "an",
    "this", "that", "these", "those", "when", "where", "because", "since", "instead",
    "during", "after", "before", "in", "on", "at", "by", "for", "with", "about",
    "against", "between", "into", "through", "above", "below", "to", "from",
    "up", "down", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "its", "their", "our", "my", "your", "his", "her",
    "fixed", "table", "figure", "section", "chapter", "source", "document",
}

_MONTHS_STR = "january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
_DATE_PATTERN = re.compile(
    rf"^(?:(?:\d{{1,4}}s?)|(?:(?:{_MONTHS_STR})\s+\d{{1,4}})|(?:\d{{1,2}}\s+(?:{_MONTHS_STR})(?:\s+\d{{2,4}})?)|(?:\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?)|(?:(?:early|mid|late)[-\s]\d{{4}}s?))$",
    re.IGNORECASE,
)
_MEASUREMENT_PATTERN = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:km|m|cm|mm|kg|g|lb|lbs|mph|km/h|knots|kw|mw|gw|ghz|mhz|hz|ms|s|sec|min|hr|hrs|%|percent|deg|c|f|k)$",
    re.IGNORECASE,
)


def sanitize_and_validate_entity(name: str) -> Optional[str]:
    """Validate and clean candidate entity name, strictly filtering out dates, fragments, and stopwords."""
    if not name:
        return None
    clean = name.strip().strip("\"'“”‘’`*#_[]():;,.")
    if len(clean) < 2:
        return None
    # 1. Reject standalone years/dates
    if _DATE_PATTERN.match(clean) or re.match(r"^(?:19|20)\d{2}(?:s)?$", clean):
        return None
    # 2. Reject pure numbers or measurements
    if clean.isdigit() or _MEASUREMENT_PATTERN.match(clean):
        return None
    # 3. Check for sentence starter words or transitions
    tokens = clean.split()
    if not tokens:
        return None
    first_token_lower = tokens[0].lower()
    if first_token_lower in DISALLOWED_START_WORDS:
        # If it starts with an article, strip it if remainder is valid
        if len(tokens) >= 2 and first_token_lower in ("the", "a", "an"):
            candidate = " ".join(tokens[1:]).strip()
            if len(candidate) >= 3 and not candidate.lower().startswith(tuple(DISALLOWED_START_WORDS)):
                return candidate
        return None
    # 4. Reject common non-entity phrases
    lower_full = clean.lower()
    if any(phrase in lower_full for phrase in [
        "the following", "in order to", "according to", "as shown", "table of", "based on",
        "for example", "et al", "figure ", "section ", "chapter ", "page "
    ]):
        return None
    return clean


def infer_semantic_relation(src_category: str, dst_category: str) -> str:
    """Infer typed domain predicate from entity categories, strictly avoiding 'associated_with'."""
    pair = (src_category, dst_category)
    cat_rules = {
        ("Program", "Organization"): "developed_by",
        ("Program", "Standard"): "implements",
        ("Program", "Material"): "incorporates",
        ("Organization", "Program"): "procured_by",
        ("Key Figure", "Program"): "developed_by",
        ("Program", "Key Figure"): "led_by",
        ("Standard", "Program"): "regulates",
        ("Material", "Program"): "incorporates",
        ("Concept", "Program"): "enables",
        ("Program", "Concept"): "implements",
        ("Organization", "Standard"): "defines",
        ("Concept", "Concept"): "influences",
        ("Program", "Program"): "competes_with",
        ("Organization", "Organization"): "collaborates_with",
    }
    return cat_rules.get(pair, "enables")


def localize_kg_relation(relation: str, lang: str = "en") -> str:
    """Return localized relation label (e.g. Korean for 'ko', English for 'en')."""
    if not relation:
        return ""
    clean = relation.strip()
    norm_key = clean.lower().replace("-", "_").replace(" ", "_")
    if lang == "ko":
        return KG_RELATION_TRANSLATIONS.get(norm_key) or KG_RELATION_TRANSLATIONS.get(clean.lower()) or clean.replace("_", " ")
    else:
        return KG_RELATION_REVERSE.get(clean) or clean.replace("_", " ")


ENTITY_EXTRACTION_PROMPT = """You are an Expert Technical Knowledge Graph Extractor.
Extract the key technical entities and their explicit relationships from the document excerpt below.

STRICT CATEGORIES (Choose strictly from these 6):
- Organization (e.g., NASA, DARPA, Lockheed Martin, TSMC, OpenAI)
- Program (e.g., Apollo, Starship, F-35, GPT-4, ITER)
- Key Figure (e.g., von Braun, Oppenheimer, Elon Musk, Jensen Huang)
- Standard (e.g., IEEE-802.11, MIL-STD-810H, ISO-9001, DO-178C)
- Material (e.g., Inconel 718, Silicon Carbide, Gallium Nitride, Carbon Fiber)
- Concept (e.g., Quantum Entanglement, Thermal Throttling, Zero-Knowledge Proof)

CRITICAL NEGATIVE EXTRACTION RULES:
- NEVER extract standalone dates, years, or decades (e.g., "1981", "October 1967", "1990s") as entity nodes. Chronology belongs in the timeline table, NOT as entities.
- NEVER extract sentence fragments, clauses, or transition phrases (e.g., "While West Germany", "The Fixed", "Hence Germany", "Furthermore").
- NEVER extract pure numbers, percentages, or measurements (e.g., "500 km", "120 mm", "30%").
- STRICTLY FORBID generic fallback relations: DO NOT use "associated_with", "connected_to", or "related_to".
- You MUST use specific, typed domain predicates such as:
  `developed_by`, `tested_at`, `failed_due_to`, `superseded_by`, `incorporates`, `competes_with`, `procured_by`, `enables`, `causes`, `mitigates`, `depends_on`, `regulates`, `implements`, `evaluates`.

Format output strictly as valid JSON matching this schema:
{{
  "entities": [
    {{"name": "NASA", "category": "Organization", "description": "United States civilian space agency"}},
    {{"name": "Artemis", "category": "Program", "description": "Lunar exploration initiative"}}
  ],
  "relations": [
    {{
      "source": "Artemis",
      "target": "NASA",
      "relation": "developed_by",
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
        """Add or update an entity node in the graph with strict validation."""
        clean_name = sanitize_and_validate_entity(name)
        if not clean_name:
            return ""
        node_id = clean_name.lower()

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
        """Add a directed relationship between two entities, upgrading generic placeholder verbs."""
        src_id = self.add_entity(source_name, cite_id=cite_id)
        dst_id = self.add_entity(target_name, cite_id=cite_id)

        if not src_id or not dst_id or src_id == dst_id:
            return False

        clean_rel = (relation or "").strip().lower().replace(" ", "_").replace("-", "_")
        if not clean_rel or clean_rel in ("associated_with", "connected_to", "related_to", "unknown", ""):
            src_cat = self.graph.nodes[src_id].get("category", "Concept")
            dst_cat = self.graph.nodes[dst_id].get("category", "Concept")
            clean_rel = infer_semantic_relation(src_cat, dst_cat)

        self.graph.add_edge(
            src_id,
            dst_id,
            relation=clean_rel,
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
                raw_entities = data.get("entities", [])
                raw_relations = data.get("relations", [])

                valid_entities: List[Dict[str, Any]] = []
                for e in raw_entities:
                    c_name = sanitize_and_validate_entity(e.get("name", ""))
                    if c_name:
                        self.add_entity(
                            name=c_name,
                            category=e.get("category", "Concept"),
                            description=e.get("description", ""),
                            cite_id=cite_id,
                        )
                        valid_entities.append({
                            "name": c_name,
                            "category": e.get("category", "Concept"),
                            "description": e.get("description", ""),
                        })

                valid_relations: List[Dict[str, Any]] = []
                for r in raw_relations:
                    src = sanitize_and_validate_entity(r.get("source", ""))
                    tgt = sanitize_and_validate_entity(r.get("target", ""))
                    if src and tgt and src != tgt:
                        rel = (r.get("relation") or "").strip().lower().replace(" ", "_")
                        if not rel or rel in ("associated_with", "connected_to", "related_to"):
                            src_cat = self.graph.nodes.get(src.lower(), {}).get("category", "Concept")
                            dst_cat = self.graph.nodes.get(tgt.lower(), {}).get("category", "Concept")
                            rel = infer_semantic_relation(src_cat, dst_cat)
                        self.add_relation(
                            source_name=src,
                            target_name=tgt,
                            relation=rel,
                            premise=r.get("premise", ""),
                            cite_id=cite_id,
                        )
                        valid_relations.append({
                            "source": src,
                            "target": tgt,
                            "relation": rel,
                            "premise": r.get("premise", ""),
                        })

                if valid_entities:
                    return valid_entities, valid_relations

            except Exception as exc:
                logger.warning(f"LLM entity extraction failed: {exc}. Using heuristic fallback.")

        # Heuristic Rule-Based Fallback Extractor
        return self._heuristic_extract(text, cite_id=cite_id)

    def _heuristic_extract(self, text: str, cite_id: int = 1) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Fast regex heuristic extraction of domain organizations, programs, standards, and concepts."""
        entities: List[Dict[str, Any]] = []
        relations: List[Dict[str, Any]] = []
        seen_names: Set[str] = set()

        # 1. Technical standards specifications (e.g. ISO-9001, IEEE 802.11, MIL-STD-810)
        std_matches = set(re.findall(r"\b(?:ISO|IEEE|MIL-STD|DO|RFC|ECMA|ANSI|NIST)[-\s][\dA-Z.-]+\b", text))
        for m in std_matches:
            c_name = sanitize_and_validate_entity(m)
            if c_name and c_name.lower() not in seen_names:
                seen_names.add(c_name.lower())
                self.add_entity(c_name, category="Standard", description="Technical standard specification", cite_id=cite_id)
                entities.append({"name": c_name, "category": "Standard"})

        # 2. Capitalized multi-word organization / program phrases
        cap_phrases = set(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b", text))
        for p in list(cap_phrases)[:15]:
            c_name = sanitize_and_validate_entity(p)
            if c_name and c_name.lower() not in seen_names:
                seen_names.add(c_name.lower())
                cat = "Organization" if any(w in c_name for w in ["Lab", "Institute", "Corp", "Inc", "Agency", "Group", "Dept", "Force", "Consortium", "Office", "Bureau"]) else "Program"
                self.add_entity(c_name, category=cat, description=f"Entity identified in document [{cite_id}]", cite_id=cite_id)
                entities.append({"name": c_name, "category": cat})

        # 3. Bold technical concepts in synthesis or notes: **Term**
        bold_terms = set(re.findall(r"\*\*([A-Za-z0-9\s_-]{3,35})\*\*", text))
        for b in list(bold_terms)[:12]:
            c_name = sanitize_and_validate_entity(b)
            if c_name and c_name.lower() not in seen_names:
                seen_names.add(c_name.lower())
                self.add_entity(c_name, category="Concept", description=f"Technical concept emphasized in [{cite_id}]", cite_id=cite_id)
                entities.append({"name": c_name, "category": "Concept"})

        # 4. Form typed relationships between discovered entities (strictly no 'associated_with')
        for i in range(len(entities) - 1):
            src_obj = entities[i]
            dst_obj = entities[i + 1]
            src_name = src_obj["name"]
            dst_name = dst_obj["name"]
            inferred_rel = infer_semantic_relation(src_obj.get("category", "Concept"), dst_obj.get("category", "Concept"))
            self.add_relation(src_name, dst_name, relation=inferred_rel, premise=f"Grounded co-occurrence in [{cite_id}]", cite_id=cite_id)
            relations.append({"source": src_name, "target": dst_name, "relation": inferred_rel})

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
                "relation": data.get("relation", "enables"),
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
                relation=e.get("relation", "enables"),
                premise=e.get("premise", ""),
                cite_id=e.get("cite_id"),
            )

    def compute_layout_data(self, min_repulsion: float = 140.0) -> Dict[str, Any]:
        """Compute force-directed clustered layout coordinates with semantic category clustering and >= 140px separation."""
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
        r_cluster = 360.0
        active_cats = [c for c in categories if cat_nodes[c]]
        n_active = max(1, len(active_cats))

        # Initial category anchor assignment
        cat_anchors: Dict[str, Tuple[float, float]] = {}
        for idx, cat in enumerate(active_cats):
            ang = idx * (2.0 * math.pi / n_active)
            cat_anchors[cat] = (r_cluster * math.cos(ang), r_cluster * math.sin(ang))

        # Deterministic distributed placement within cluster anchors
        for cat, c_list in cat_nodes.items():
            if not c_list:
                continue
            cx, cy = cat_anchors.get(cat, (0.0, 0.0))
            if len(c_list) == 1:
                pos[c_list[0]] = [cx, cy]
            else:
                for j, nid in enumerate(c_list):
                    # Pseudo-random deterministic offset to prevent rigid circular locking
                    hash_val = abs(hash(nid))
                    j_ang = (j * (2.0 * math.pi / len(c_list))) + ((hash_val % 31) / 100.0)
                    r_local = max(100.0, min(240.0, 50.0 + len(c_list) * 20.0))
                    pos[nid] = [cx + r_local * math.cos(j_ang), cy + r_local * math.sin(j_ang)]

        # Force-directed relaxation (repulsion + category cohesion + edge spring attraction)
        node_keys = list(pos.keys())
        repulse_bound = max(140.0, min_repulsion)

        for _ in range(50):
            # 1. Repulsion between all node pairs
            for a in range(len(node_keys)):
                u = node_keys[a]
                for b in range(a + 1, len(node_keys)):
                    v = node_keys[b]
                    dx = pos[u][0] - pos[v][0]
                    dy = pos[u][1] - pos[v][1]
                    dist = math.hypot(dx, dy)
                    if dist < repulse_bound:
                        d = max(dist, 1.0)
                        push = (repulse_bound - dist) / d * 0.55
                        pos[u][0] += dx * push
                        pos[u][1] += dy * push
                        pos[v][0] -= dx * push
                        pos[v][1] -= dy * push

            # 2. Cohesion toward category anchor
            for nid, p in pos.items():
                cat = all_nodes_data.get(nid, {}).get("category", "Concept")
                if cat in cat_anchors:
                    ax, ay = cat_anchors[cat]
                    pos[nid][0] += (ax - p[0]) * 0.03
                    pos[nid][1] += (ay - p[1]) * 0.03

            # 3. Edge spring attraction (ideal distance ~160px)
            for u, v in self.graph.edges():
                if u in pos and v in pos:
                    dx = pos[v][0] - pos[u][0]
                    dy = pos[v][1] - pos[u][1]
                    dist = math.hypot(dx, dy)
                    if dist > 160.0:
                        pull = (dist - 160.0) * 0.045
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
                    "relation": data.get("relation", "enables"),
                    "premise": data.get("premise", ""),
                    "cite_id": data.get("cite_id"),
                    "x1": round(pos[u][0], 1),
                    "y1": round(pos[u][1], 1),
                    "x2": round(pos[v][0], 1),
                    "y2": round(pos[v][1], 1),
                })

        return {"nodes": out_nodes, "edges": out_edges}


__all__ = [
    "ENTITY_CATEGORIES",
    "KG_RELATION_TRANSLATIONS",
    "KG_RELATION_REVERSE",
    "KnowledgeGraphEngine",
    "localize_kg_relation",
    "clean_and_parse_json",
    "sanitize_and_validate_entity",
    "infer_semantic_relation",
]


