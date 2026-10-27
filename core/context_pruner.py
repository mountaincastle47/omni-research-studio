"""Hybrid BM25 context window pruner and re-ranker for mega-corpora."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from rank_bm25 import BM25Okapi

from core.document_loader import SourceDocument

DEFAULT_MAX_CONTEXT_THRESHOLD = 64_000
DEFAULT_TARGET_PRUNED_TOKENS = 20_000
DEFAULT_CHUNK_WORD_SIZE = 400
DEFAULT_CHUNK_OVERLAP = 80


@dataclass
class PrunedChunk:
    """A semantic slice of a source document tagged with provenance metadata."""

    doc_id: int
    title: str
    page_num: int
    chunk_index: int
    text: str
    tokens: int
    score: float = 0.0


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase lexical words for BM25 ranking."""
    return re.findall(r"\b[A-Za-z0-9_\uac00-\ud7a3]+\b", text.lower())


class ContextPruner:
    """Slices mega-corpora into semantic chunks and prioritizes top-k density excerpts via BM25."""

    def __init__(
        self,
        max_context_threshold: int = DEFAULT_MAX_CONTEXT_THRESHOLD,
        target_pruned_tokens: int = DEFAULT_TARGET_PRUNED_TOKENS,
        chunk_word_size: int = DEFAULT_CHUNK_WORD_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        self.max_context_threshold = max_context_threshold
        self.target_pruned_tokens = target_pruned_tokens
        self.chunk_word_size = chunk_word_size
        self.chunk_overlap = chunk_overlap

    def slice_document(
        self,
        doc: SourceDocument,
        chunk_word_size: Optional[int] = None,
        overlap: Optional[int] = None,
    ) -> List[PrunedChunk]:
        """Slice a source document into overlapping word chunks preserving page anchors."""
        sz = chunk_word_size or self.chunk_word_size
        ov = overlap or self.chunk_overlap
        content = doc.content or ""
        if not content.strip():
            return []

        # Split content into pages if <!--PAGE_START:N--> boundaries exist
        page_pattern = re.compile(r"<!--PAGE_START:(\d+)-->")
        parts = page_pattern.split(content)

        chunks: List[PrunedChunk] = []
        chunk_counter = 0

        if len(parts) > 1:
            # First element is pre-page text (usually empty or page 1)
            first_text = parts[0].strip()
            if first_text:
                self._slice_page_text(
                    doc=doc,
                    page_num=1,
                    text=first_text,
                    sz=sz,
                    ov=ov,
                    chunks=chunks,
                    counter_start=chunk_counter,
                )
                chunk_counter = len(chunks)

            # Following pairs are (page_num_str, page_content)
            for i in range(1, len(parts), 2):
                p_num = int(parts[i]) if parts[i].isdigit() else 1
                p_text = parts[i + 1] if (i + 1 < len(parts)) else ""
                self._slice_page_text(
                    doc=doc,
                    page_num=p_num,
                    text=p_text,
                    sz=sz,
                    ov=ov,
                    chunks=chunks,
                    counter_start=chunk_counter,
                )
                chunk_counter = len(chunks)
        else:
            self._slice_page_text(
                doc=doc,
                page_num=1,
                text=content,
                sz=sz,
                ov=ov,
                chunks=chunks,
                counter_start=0,
            )

        return chunks

    def _slice_page_text(
        self,
        doc: SourceDocument,
        page_num: int,
        text: str,
        sz: int,
        ov: int,
        chunks: List[PrunedChunk],
        counter_start: int,
    ) -> None:
        words = text.split()
        if not words:
            return

        step = max(1, sz - ov)
        for i in range(0, len(words), step):
            sub_words = words[i : i + sz]
            chunk_str = " ".join(sub_words).strip()
            if not chunk_str:
                continue
            est_tokens = max(1, len(chunk_str) // 4)
            chunks.append(
                PrunedChunk(
                    doc_id=doc.cite_id,
                    title=doc.title,
                    page_num=page_num,
                    chunk_index=counter_start + len(chunks),
                    text=chunk_str,
                    tokens=est_tokens,
                )
            )
            if i + sz >= len(words):
                break

    def prune(
        self,
        query: str,
        documents: Sequence[SourceDocument],
        mode: str = "Auto",
        threshold_override: Optional[int] = None,
        target_tokens: Optional[int] = None,
        top_k: int = 50,
    ) -> Tuple[List[SourceDocument], bool, Dict[str, Any]]:
        """Evaluate active corpus token volume and execute BM25 reduction if exceeding threshold."""
        enabled_docs = [d for d in documents if d.enabled]
        if not enabled_docs:
            return [], False, {"status": "empty"}

        mode_clean = str(mode).strip().lower()
        if mode_clean == "off":
            return list(enabled_docs), False, {"status": "off", "mode": mode}

        total_corpus_tokens = sum(doc.estimated_tokens for doc in enabled_docs)

        # Determine threshold
        if mode_clean == "64k":
            threshold = 64_000
        elif mode_clean == "128k":
            threshold = 128_000
        else:
            threshold = threshold_override or self.max_context_threshold

        if total_corpus_tokens <= threshold:
            return (
                list(enabled_docs),
                False,
                {
                    "status": "below_threshold",
                    "total_tokens": total_corpus_tokens,
                    "threshold": threshold,
                    "mode": mode,
                },
            )

        # Slice all enabled documents into candidate chunks
        all_chunks: List[PrunedChunk] = []
        for doc in enabled_docs:
            all_chunks.extend(self.slice_document(doc))

        if not all_chunks:
            return list(enabled_docs), False, {"status": "no_chunks"}

        # Tokenize corpus for BM25
        tokenized_corpus = [_tokenize(c.text) for c in all_chunks]
        tokenized_query = _tokenize(query)

        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(tokenized_query)

        for chunk, score in zip(all_chunks, scores):
            chunk.score = float(score)

        # Sort descending by BM25 relevance score
        ranked_chunks = sorted(all_chunks, key=lambda c: c.score, reverse=True)

        budget = target_tokens or self.target_pruned_tokens
        selected_chunks: List[PrunedChunk] = []
        accumulated_tokens = 0

        for chunk in ranked_chunks[: max(10, top_k)]:
            if accumulated_tokens + chunk.tokens > budget and len(selected_chunks) >= 10:
                break
            selected_chunks.append(chunk)
            accumulated_tokens += chunk.tokens

        # Fallback if no chunks scored above 0: take top slices anyway
        if not selected_chunks:
            selected_chunks = ranked_chunks[:min(len(ranked_chunks), top_k)]
            accumulated_tokens = sum(c.tokens for c in selected_chunks)

        # Reassemble prioritized chunks into synthetic SourceDocument instances per original cite_id
        reconstructed_docs: List[SourceDocument] = []
        doc_map = {d.cite_id: d for d in enabled_docs}

        # Group selected chunks by doc_id
        chunks_by_doc: Dict[int, List[PrunedChunk]] = {}
        for c in selected_chunks:
            chunks_by_doc.setdefault(c.doc_id, []).append(c)

        for cite_id, doc_chunks in chunks_by_doc.items():
            orig = doc_map.get(cite_id)
            if orig is None:
                continue

            # Sort chunks by page_num, then chunk_index for reading coherence
            doc_chunks.sort(key=lambda x: (x.page_num, x.chunk_index))

            # Reconstruct content with page boundary tags
            built_content_parts = []
            cur_page = -1
            for ch in doc_chunks:
                if ch.page_num != cur_page:
                    built_content_parts.append(f"\n<!--PAGE_START:{ch.page_num}-->\n")
                    cur_page = ch.page_num
                built_content_parts.append(f"...\n{ch.text}\n...")

            pruned_content = "\n".join(built_content_parts).strip()
            pruned_doc = SourceDocument(
                cite_id=orig.cite_id,
                title=orig.title,
                path_or_uri=orig.path_or_uri,
                content=pruned_content,
                source_type=orig.source_type,
                page_count=orig.page_count,
                metadata=dict(orig.metadata),
                enabled=True,
            )
            reconstructed_docs.append(pruned_doc)

        telemetry = {
            "status": "pruned",
            "original_tokens": total_corpus_tokens,
            "pruned_tokens": accumulated_tokens,
            "chunks_selected": len(selected_chunks),
            "total_chunks": len(all_chunks),
            "threshold": threshold,
            "mode": mode,
        }
        return reconstructed_docs, True, telemetry
