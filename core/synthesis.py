"""Accelerated Synthesis Engine with fast JSON parsing, persistent connection reuse, and cooperative cancellation."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import orjson

    def fast_json_loads(data: Union[str, bytes]) -> Any:
        """High-speed zero-copy JSON parsing using orjson."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        return orjson.loads(data)

    def fast_json_dumps(obj: Any, **kwargs) -> str:
        """High-speed JSON serialization using orjson."""
        return orjson.dumps(obj).decode("utf-8")

except ImportError:
    try:
        import ujson

        def fast_json_loads(data: Union[str, bytes]) -> Any:
            return ujson.loads(data)

        def fast_json_dumps(obj: Any, **kwargs) -> str:
            return ujson.dumps(obj, **kwargs)

    except ImportError:
        import json

        def fast_json_loads(data: Union[str, bytes]) -> Any:
            return json.loads(data)

        def fast_json_dumps(obj: Any, **kwargs) -> str:
            return json.dumps(obj, **kwargs)

# Re-export core synthesis symbols from notebook_synthesis
from core.notebook_synthesis import (
    CitationMatch,
    DEFAULT_SYNTHESIS_MODEL,
    NotebookSynthesizer,
    SynthesisResult,
)

CitationRef = CitationMatch

logger = logging.getLogger("OmniSynthesis")

MAX_GAP_ITERATIONS: int = 2

COMMON_CAUSAL_TRANSLATIONS: Dict[str, str] = {
    # English to Korean
    "causes": "유발함",
    "causes/triggers": "유발/촉발",
    "triggers": "촉발함",
    "leads to": "이어짐",
    "mitigates": "완화함",
    "degrades": "저하시킴",
    "improves": "개선함",
    "utilizes": "활용함",
    "connected to": "연결됨",
    "connected_to": "연결됨",
    "requires": "필요로 함",
    "produces": "생산함",
    "inhibits": "억제함",
    "controls": "제어함",
    "impacts": "영향을 미침",
    "depends on": "의존함",
    "verifies": "검증함",
    "contradicts": "상충함",
    "fails": "실패함",
    "results in": "결과 초래",
    "blocks": "차단함",
    "accelerates": "가속화함",
    # Korean to English
    "유발함": "causes",
    "유발/촉발": "causes/triggers",
    "촉발함": "triggers",
    "이어짐": "leads to",
    "완화함": "mitigates",
    "저하시킴": "degrades",
    "개선함": "improves",
    "활용함": "utilizes",
    "연결됨": "connected to",
    "필요로 함": "requires",
    "생산함": "produces",
    "억제함": "inhibits",
    "제어함": "controls",
    "영향을 미침": "impacts",
    "의존함": "depends on",
    "검증함": "verifies",
    "상충함": "contradicts",
    "실패함": "fails",
    "결과 초래": "results in",
    "차단함": "blocks",
    "가속화함": "accelerates",
}


def build_localized_graph_mappings(
    original_markdown: str,
    translated_markdown: str,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Extract and construct bilateral node/relation translation mappings between original and translated markdown.
    Returns (map_en_to_ko, map_ko_to_en).
    """
    en_to_ko: Dict[str, str] = dict(COMMON_CAUSAL_TRANSLATIONS)
    ko_to_en: Dict[str, str] = {v: k for k, v in COMMON_CAUSAL_TRANSLATIONS.items()}

    try:
        from core.knowledge_graph import KG_RELATION_TRANSLATIONS
        en_to_ko.update(KG_RELATION_TRANSLATIONS)
        for k, v in KG_RELATION_TRANSLATIONS.items():
            ko_to_en[v] = k
    except Exception:
        pass

    import re
    # Extract paired bold entities **Term** between original and translated markdown
    o_bolds = re.findall(r"\*\*([A-Za-z0-9\s_-]{3,40})\*\*", original_markdown or "")
    t_bolds = re.findall(r"\*\*([^\*\n]{3,40})\*\*", translated_markdown or "")
    if len(o_bolds) == len(t_bolds) and o_bolds:
        for ob, tb in zip(o_bolds, t_bolds):
            ob_clean = ob.strip()
            tb_clean = tb.strip()
            if ob_clean and tb_clean:
                en_to_ko[ob_clean] = tb_clean
                en_to_ko[ob_clean.lower()] = tb_clean
                ko_to_en[tb_clean] = ob_clean
                ko_to_en[tb_clean.lower()] = ob_clean

    from core.graph_generator import extract_mermaid_blocks, parse_mermaid_code
    orig_blocks = extract_mermaid_blocks(original_markdown or "")
    trans_blocks = extract_mermaid_blocks(translated_markdown or "")

    if orig_blocks and trans_blocks:
        orig_g = parse_mermaid_code(orig_blocks[0])
        trans_g = parse_mermaid_code(trans_blocks[0])

        orig_nodes = list(orig_g.nodes.values())
        trans_nodes = list(trans_g.nodes.values())

        # Match by node_id if same IDs were kept
        for o_node in orig_nodes:
            if o_node.node_id in trans_g.nodes:
                t_node = trans_g.nodes[o_node.node_id]
                en_to_ko[o_node.label] = t_node.label
                en_to_ko[o_node.node_id] = t_node.label
                ko_to_en[t_node.label] = o_node.label
                ko_to_en[t_node.node_id] = o_node.label

        # If IDs differ or are indexed, match by sequential topology position
        if len(orig_nodes) == len(trans_nodes):
            for o_node, t_node in zip(orig_nodes, trans_nodes):
                en_to_ko[o_node.label] = t_node.label
                en_to_ko[o_node.node_id] = t_node.label
                ko_to_en[t_node.label] = o_node.label
                ko_to_en[t_node.node_id] = o_node.label

        # Match edges
        if len(orig_g.edges) == len(trans_g.edges):
            for o_e, t_e in zip(orig_g.edges, trans_g.edges):
                if o_e.label and t_e.label:
                    en_to_ko[o_e.label] = t_e.label
                    ko_to_en[t_e.label] = o_e.label

    return en_to_ko, ko_to_en


class CancellableSynthesisEngine:
    """Thread-safe cancellable synthesis orchestrator with active client socket teardown."""

    def __init__(self, synthesizer: Optional[NotebookSynthesizer] = None) -> None:
        self.synthesizer = synthesizer
        self.stop_requested = threading.Event()
        self.active_client: Any = getattr(synthesizer, "client", None) if synthesizer else None

    def request_stop(self) -> None:
        """Immediately signal stop and tear down active network sockets."""
        self.stop_requested.set()
        if hasattr(self, "active_client") and self.active_client:
            try:
                self.active_client.close()
            except Exception:
                pass

    def is_stopped(self) -> bool:
        return self.stop_requested.is_set()


__all__ = [
    "MAX_GAP_ITERATIONS",
    "CitationRef",
    "DEFAULT_SYNTHESIS_MODEL",
    "NotebookSynthesizer",
    "SynthesisResult",
    "CancellableSynthesisEngine",
    "COMMON_CAUSAL_TRANSLATIONS",
    "build_localized_graph_mappings",
    "fast_json_loads",
    "fast_json_dumps",
]
