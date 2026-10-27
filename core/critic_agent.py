"""Epistemic entailment critic agent auditing borderline citations for logical support."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.config import ConfigManager
from core.document_loader import SourceDocument

CRITIC_MODEL = "gemini-3.8-flash"


@dataclass
class EntailmentVerdict:
    """Logical entailment evaluation between a report claim and cited source excerpt."""

    cite_id: int
    page_num: Optional[int]
    claim_sentence: str
    source_excerpt: str
    entails: bool
    confidence: float
    critique: str


class CriticAgent:
    """Audits citations scoring in the borderline Jaccard overlap range (0.05 - 0.35)."""

    def __init__(self, config_manager: Optional[ConfigManager] = None) -> None:
        self.config_manager = config_manager or ConfigManager()

    def identify_borderline_citations(
        self,
        report_markdown: str,
        documents: Sequence[SourceDocument],
        lower_bound: float = 0.05,
        upper_bound: float = 0.35,
    ) -> List[Dict[str, Any]]:
        """Scan report text for citation sentences falling in the suspect overlap range."""
        from core.notebook_synthesis import (
            check_semantic_alignment,
            extract_page_chunk_from_content,
        )

        doc_map = {d.cite_id: d for d in documents if d.enabled}
        results: List[Dict[str, Any]] = []

        # Split text into sentences
        sentence_pattern = re.compile(r"([^.!?\n]+(?:\[[0-9:p\.,\s]+\])[^.!?\n]*[.!?]?)")
        cite_token_pattern = re.compile(r"\[([0-9:p\.,\s]+)\]")

        for match in sentence_pattern.finditer(report_markdown or ""):
            sentence = match.group(0).strip()
            for cite_match in cite_token_pattern.finditer(sentence):
                raw_group = cite_match.group(1)
                for token in raw_group.split(","):
                    t = token.strip()
                    cid = None
                    p_num = None
                    if ":p." in t:
                        p_parts = t.split(":p.")
                        if p_parts[0].isdigit():
                            cid = int(p_parts[0])
                        if len(p_parts) > 1 and p_parts[1].isdigit():
                            p_num = int(p_parts[1])
                    elif t.isdigit():
                        cid = int(t)

                    if cid is not None and cid in doc_map:
                        doc = doc_map[cid]
                        overlap, _ = check_semantic_alignment(sentence, doc.content, page_num=p_num)
                        if lower_bound <= overlap <= upper_bound:
                            excerpt = extract_page_chunk_from_content(doc.content, p_num)
                            results.append(
                                {
                                    "cite_id": cid,
                                    "page_num": p_num,
                                    "sentence": sentence,
                                    "source_excerpt": excerpt[:800],
                                    "overlap": overlap,
                                }
                            )

        return results

    def evaluate_entailment_sync(
        self,
        claim_sentence: str,
        source_excerpt: str,
        cite_id: int,
        page_num: Optional[int] = None,
    ) -> EntailmentVerdict:
        """Evaluate logical entailment between claim and source excerpt."""
        prompt = (
            "You are an elite research critic verifying factual accuracy and source entailment.\n"
            "Evaluate if the CLAIM is logically supported, directly stated, or reasonably entailed by the SOURCE EXCERPT.\n\n"
            f"CLAIM:\n\"{claim_sentence}\"\n\n"
            f"SOURCE EXCERPT:\n\"{source_excerpt}\"\n\n"
            "Output strictly valid JSON with no conversational text:\n"
            '{"entails": bool, "confidence": float, "critique": "brief explanation (max 30 words)"}'
        )

        api_key = self.config_manager.get_api_key()
        if not api_key:
            return self._heuristic_fallback(claim_sentence, source_excerpt, cite_id, page_num)

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=CRITIC_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            raw_text = response.text or ""
            return self.parse_critic_json(raw_text, cite_id, page_num, claim_sentence, source_excerpt)
        except Exception:
            return self._heuristic_fallback(claim_sentence, source_excerpt, cite_id, page_num)

    def parse_critic_json(
        self,
        json_str: str,
        cite_id: int,
        page_num: Optional[int],
        claim_sentence: str,
        source_excerpt: str,
    ) -> EntailmentVerdict:
        """Parse structured model critique output."""
        cleaned = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", json_str.strip()).strip()
        try:
            data = json.loads(cleaned)
            return EntailmentVerdict(
                cite_id=cite_id,
                page_num=page_num,
                claim_sentence=claim_sentence,
                source_excerpt=source_excerpt,
                entails=bool(data.get("entails", True)),
                confidence=float(data.get("confidence", 0.8)),
                critique=str(data.get("critique", "Evaluated by epistemic critic.")),
            )
        except Exception:
            return self._heuristic_fallback(claim_sentence, source_excerpt, cite_id, page_num)

    def _heuristic_fallback(
        self,
        claim_sentence: str,
        source_excerpt: str,
        cite_id: int,
        page_num: Optional[int],
    ) -> EntailmentVerdict:
        """Deterministic heuristic fallback when API is unavailable."""
        from core.notebook_synthesis import check_semantic_alignment

        overlap, is_aligned = check_semantic_alignment(claim_sentence, source_excerpt, page_num=page_num)
        entails = is_aligned or overlap >= 0.12
        critique = "Lexical verification aligned." if entails else "Weak semantic lexical grounding detected."
        return EntailmentVerdict(
            cite_id=cite_id,
            page_num=page_num,
            claim_sentence=claim_sentence,
            source_excerpt=source_excerpt,
            entails=entails,
            confidence=round(max(0.5, min(0.99, overlap * 2.5)), 2),
            critique=critique,
        )
