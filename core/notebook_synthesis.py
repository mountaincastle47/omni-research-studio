"""Zero-temperature grounded synthesis combining local files and OmniSweep web discovery with live token streaming."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from google import genai
from google.genai import types

from core.config import DEFAULT_SYNTHESIS_MODEL
from core.context_pruner import ContextPruner
from core.critic_agent import CriticAgent, EntailmentVerdict
from core.document_loader import SourceDocument
from core.local_llm_client import LocalLLMClient, is_local_model
from core.resilience import TaskCancelledError, call_with_exponential_backoff
from core.security_filter import scrub_sensitive_patterns
from core.storm_discovery import OUTPUT_LANGUAGE_CONSTRAINT, STRICT_FORMATTING_RULE
from core.token_ledger import TokenLedger

EPISTEMIC_FRICTION_MANDATE = (
    "EPISTEMIC FRICTION & CONTRADICTION MANDATE:\n"
    "- Actively identify empirical discrepancies between official manufacturer/state claims and contrarian/skeptic trial logs or third-party telemetry.\n"
    "- SOURCE AUTHORITY HIERARCHY RULE: Primary empirical data and telemetry ([PRIMARY/EMPIRICAL]) take precedence over secondary reporting ([SECONDARY/SCHOLARLY]). If tertiary commentary ([TERTIARY/COMMENTARY]) contradicts primary trial logs or telemetry, highlight the discrepancy explicitly in the Contested Claims & Empirical Anomalies Matrix.\n"
    "- NEVER smooth over conflicting data into a generic consensus.\n"
    "- If conflicting figures, dates, failure rates, or doctrine assessments exist, construct a dedicated Markdown table titled '## Contested Claims & Empirical Anomalies':\n"
    "  | Parameter / Event | Official / Baseline Claim | Empirical / Contrarian Finding | Technical Divergence Root Cause |\n"
    "- Every cell in this table must be grounded with specific [N:p.X] or [N] citations."
)

STOP_WORDS: Set[str] = {
    "the", "and", "is", "in", "to", "of", "a", "an", "that", "this", "it", "for",
    "on", "with", "as", "by", "at", "from", "are", "be", "or", "was", "were",
    "which", "but", "not", "have", "has", "had", "they", "we", "you", "i", "he",
    "she", "its", "their", "our", "been", "also", "into", "more", "can", "will",
    "이", "그", "저", "것", "수", "등", "및", "에", "를", "을", "은", "는", "가", "이",
    "으로", "로", "에서", "와", "과", "도", "하다", "있다", "되다",
}


def extract_content_tokens(text: str) -> Set[str]:
    """Tokenize and normalize content words, filtering stop words and short symbols."""
    raw_words = re.findall(r"[\w\uac00-\ud7a3]{3,}", text.lower())
    tokens: Set[str] = set()
    for w in raw_words:
        stem = re.sub(r"(ing|ed|ly|es|s|ment|tion|able)$", "", w)
        if len(stem) >= 3 and stem not in STOP_WORDS:
            tokens.add(stem)
    return tokens


def extract_page_chunk_from_content(content: str, page_num: Optional[int]) -> str:
    """Extract page X text if `<!--PAGE_START:X-->` markers are present; otherwise returns content."""
    if not page_num:
        return content
    marker = f"<!--PAGE_START:{page_num}-->"
    if marker not in content:
        return content
    start = content.index(marker) + len(marker)
    m = re.search(r"<!--PAGE_START:\d+-->", content[start:])
    end = start + m.start() if m else len(content)
    return content[start:end].strip()


def check_semantic_alignment(
    claim_sentence: str,
    source_content: str,
    page_num: Optional[int] = None,
    threshold: float = 0.12,
) -> Tuple[float, bool]:
    """
    Compute lexical token overlap between a claim sentence and the source excerpt.
    Returns (overlap_ratio, is_aligned).
    """
    source_chunk = extract_page_chunk_from_content(source_content, page_num)
    claim_tokens = extract_content_tokens(claim_sentence)
    if not claim_tokens:
        return 1.0, True
    source_tokens = extract_content_tokens(source_chunk)
    if not source_tokens:
        return 0.0, False
    intersection = claim_tokens.intersection(source_tokens)
    overlap = len(intersection) / len(claim_tokens)
    is_aligned = overlap >= threshold or len(intersection) >= 2
    return overlap, is_aligned


def create_semantic_anchor_builder(
    documents: List[SourceDocument],
    critic_verdicts: Optional[Dict[Tuple[int, Optional[int]], Any]] = None,
) -> Callable[[str, Optional[str], str], str]:
    """
    Return an anchor_builder callback for `markdown_to_html` that audits semantic alignment
    between the cited claim and the referenced source page, styling verified claims in blue,
    suspect claims in warning amber, and refuted claims in red.
    """
    doc_map: Dict[int, SourceDocument] = {doc.cite_id: doc for doc in documents}

    def _anchor_builder(doc_id: str, page: Optional[str] = None, context_claim: str = "") -> str:
        try:
            cid = int(doc_id)
            doc = doc_map.get(cid)
        except ValueError:
            doc = None

        is_time = str(page).startswith("time:") if page else False
        if is_time:
            t_val = page[5:]
            page_int = None
            label = f"[{doc_id}:{t_val}]"
            href = f"cite:{doc_id}:time:{t_val}"
        else:
            page_int = int(page) if (page and page.isdigit()) else None
            label = f"[{doc_id}:p.{page}]" if page else f"[{doc_id}]"
            href = f"cite:{doc_id}:{page}" if page else f"cite:{doc_id}"

        if doc is None:
            return (
                f'<a href="{href}" class="citation-anchor cite-suspect" '
                f'style="color: #d29922; font-weight: bold; text-decoration: none; '
                f'background: rgba(210, 153, 34, 0.15); padding: 1px 5px; border-radius: 3px;" '
                f'title="Warning: Source [{doc_id}] not found in active corpus">{label}</a>'
            )

        doc_title = (doc.title or "Untitled").replace('"', '&quot;')
        excerpt = (doc.summary_snippet if hasattr(doc, "summary_snippet") else doc.content[:150]).replace("\n", " ").replace('"', '&quot;').strip()

        # Check Critic Agent verdict first if present
        if critic_verdicts:
            verdict = critic_verdicts.get((cid, page_int))
            if verdict is None and page_int is not None:
                verdict = critic_verdicts.get((cid, None))
            if verdict is not None:
                critique_safe = str(getattr(verdict, "critique", "Critique evaluated")).replace('"', '&quot;')
                if getattr(verdict, "entails", True):
                    hover_title = f"출처: [{doc_id}] {doc_title} | [비평 검증됨: 논리적 뒷받침 확인 - {critique_safe}] | 발췌: {excerpt}"
                    return (
                        f'<a href="{href}" class="citation-anchor cite-verified" '
                        f'style="color: #58a6ff; font-weight: bold; text-decoration: none; '
                        f'background: rgba(56, 139, 253, 0.15); padding: 1px 5px; border-radius: 3px;" '
                        f'title="{hover_title}">{label}</a>'
                    )
                else:
                    hover_title = f"출처: [{doc_id}] {doc_title} | [비평 반박 경고: {critique_safe}] | 발췌: {excerpt}"
                    return (
                        f'<a href="{href}" class="citation-anchor cite-refuted" '
                        f'style="color: #f85149; font-weight: bold; text-decoration: none; '
                        f'background: rgba(248, 81, 73, 0.2); padding: 1px 5px; border-radius: 3px; border: 1px solid rgba(248, 81, 73, 0.4);" '
                        f'title="{hover_title}">{label}</a>'
                    )

        score, is_aligned = check_semantic_alignment(context_claim, doc.content, page_num=page_int)
        hover_title = f"출처: [{doc_id}] {doc_title} | 발췌: {excerpt}"

        if is_aligned:
            return (
                f'<a href="{href}" class="citation-anchor cite-verified" '
                f'style="color: #58a6ff; font-weight: bold; text-decoration: none; '
                f'background: rgba(56, 139, 253, 0.15); padding: 1px 5px; border-radius: 3px;" '
                f'title="{hover_title}">{label}</a>'
            )
        else:
            return (
                f'<a href="{href}" class="citation-anchor cite-suspect" '
                f'style="color: #d29922; font-weight: bold; text-decoration: none; '
                f'background: rgba(210, 153, 34, 0.15); padding: 1px 5px; border-radius: 3px;" '
                f'title="{hover_title} (경고: 텍스트 일치율 {int(score * 100)}%)">{label}</a>'
            )

    return _anchor_builder


def sanitize_unclosed_markdown(md_text: str) -> str:
    """Ensure unclosed code blocks and broken table rows in markdown are safely closed."""
    if not md_text:
        return ""

    sanitized = md_text

    # 1. Close unclosed code fences
    fences = re.findall(r"```", sanitized)
    if len(fences) % 2 != 0:
        sanitized = sanitized.rstrip() + "\n```\n"

    # 2. Repair dangling/unclosed markdown table rows
    lines = sanitized.splitlines()
    if lines:
        last_line = lines[-1].strip()
        if last_line.startswith("|") and not last_line.endswith("|"):
            lines[-1] = last_line + " |"
            sanitized = "\n".join(lines) + "\n"

    return sanitized


@dataclass
class CachedCorpusEntry:
    """Tracks active Google GenAI explicit cached content metadata."""

    cache_name: str
    corpus_hash: str
    model: str
    created_at: float
    ttl_seconds: float = 300.0


class ContextCacheStore:
    """Thread-safe cache directory for Google GenAI explicit context caching (>32,768 tokens)."""

    _instance: Optional[ContextCacheStore] = None

    def __init__(self) -> None:
        self._entries: Dict[str, CachedCorpusEntry] = {}

    @classmethod
    def get_instance(cls) -> ContextCacheStore:
        if cls._instance is None:
            cls._instance = ContextCacheStore()
        return cls._instance

    def get_cached_name(self, corpus_hash: str, model: str) -> Optional[str]:
        entry = self._entries.get(corpus_hash)
        if entry:
            if (time.time() - entry.created_at) < entry.ttl_seconds and entry.model == model:
                return entry.cache_name
            self._entries.pop(corpus_hash, None)
        return None

    def put_cache(self, corpus_hash: str, model: str, cache_name: str, ttl_seconds: float = 300.0) -> None:
        self._entries[corpus_hash] = CachedCorpusEntry(
            cache_name=cache_name,
            corpus_hash=corpus_hash,
            model=model,
            created_at=time.time(),
            ttl_seconds=ttl_seconds,
        )

    def get_or_create_cache(
        self,
        client: genai.Client,
        model_name: str,
        unified_context: str,
        ttl_seconds: int = 300,
    ) -> Optional[str]:
        """Create or return existing cached content name if corpus is sufficiently large."""
        corpus_hash = hashlib.sha256(unified_context.encode("utf-8")).hexdigest()
        cached_name = self.get_cached_name(corpus_hash, model_name)
        if cached_name:
            return cached_name

        try:
            cache_obj = client.caches.create(
                model=model_name,
                config=types.CreateCachedContentConfig(
                    contents=[unified_context],
                    ttl=f"{ttl_seconds}s",
                    display_name=f"omni_cache_{corpus_hash[:8]}",
                ),
            )
            if cache_obj and hasattr(cache_obj, "name") and cache_obj.name:
                self.put_cache(corpus_hash, model_name, cache_obj.name, float(ttl_seconds))
                return cache_obj.name
        except Exception:
            # Fall back cleanly to inline context if caching is unsupported or quota exceeded
            pass
        return None


@dataclass
class CitationMatch:
    """Represents a citation marker referenced in the synthesized output."""

    cite_id: int
    title: str
    source_type: str
    path_or_uri: str
    excerpt: str
    occurrences: int = 1


@dataclass
class SynthesisResult:
    """Contains the synthesized markdown report and extracted citation mappings."""

    query: str
    model_used: str
    markdown_report: str
    citations_used: List[CitationMatch] = field(default_factory=list)
    total_sources_provided: int = 0
    from_cache: bool = False
    critic_verdicts: Dict[Tuple[int, Optional[int]], Any] = field(default_factory=dict)
    was_pruned: bool = False
    pruner_telemetry: Dict[str, Any] = field(default_factory=dict)


class NotebookSynthesizer:
    """Performs strict zero-temperature grounded synthesis with bracketed citations and live streaming."""

    def __init__(
        self,
        client: Optional[genai.Client] = None,
        model_name: str = DEFAULT_SYNTHESIS_MODEL,
        compression_mode: str = "Auto",
    ) -> None:
        self.client = client
        self.model_name = model_name
        self.compression_mode = compression_mode

    def synthesize(
        self,
        query: str,
        documents: List[SourceDocument],
        progress_callback: Optional[Callable[[str], None]] = None,
        chunk_callback: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        compression_mode: Optional[str] = None,
    ) -> SynthesisResult:
        """Synthesize an authoritative report strictly grounded in the supplied documents using live token streaming."""
        cleaned_query = query.strip()
        if not cleaned_query:
            raise ValueError("Synthesis query cannot be empty.")

        active_docs = [doc for doc in documents if doc.enabled]
        if not active_docs:
            raise ValueError(
                "No enabled sources in the corpus. Upload local files or run OmniSweep Web Discovery first."
            )

        if cancel_check and cancel_check():
            raise TaskCancelledError("Task aborted by user.")

        # Phase 8: Hybrid BM25 Context Pruner
        active_mode = compression_mode or getattr(self, "compression_mode", "Auto")
        pruner = ContextPruner()
        pruned_docs, was_pruned, pruner_telemetry = pruner.prune(
            cleaned_query, active_docs, mode=active_mode
        )
        if was_pruned:
            if progress_callback:
                orig_tok = pruner_telemetry.get("original_tokens", 0)
                prun_tok = pruner_telemetry.get("pruned_tokens", 0)
                chunks_sel = pruner_telemetry.get("chunks_selected", 0)
                progress_callback(
                    f"Context Pruned: BM25 reduced corpus from {orig_tok:,} to {prun_tok:,} tokens ({chunks_sel} chunks)."
                )
            docs_for_context = pruned_docs
        else:
            docs_for_context = active_docs

        context_blocks: List[str] = []
        doc_map: Dict[int, SourceDocument] = {doc.cite_id: doc for doc in active_docs}

        for doc in docs_for_context:
            grounding_links_info = ""
            links = doc.metadata.get("grounding_links")
            if isinstance(links, list) and links:
                formatted_links = "\n".join(
                    f"  * {item.get('title', 'Web Source')}: {item.get('uri', '')}"
                    for item in links
                    if isinstance(item, dict) and item.get("uri")
                )
                if formatted_links:
                    grounding_links_info = f"\nVerified Web Grounding Links:\n{formatted_links}\n"

            block = (
                f"=== SOURCE [{doc.cite_id}] ===\n"
                f"Title: {doc.title}\n"
                f"Type: {doc.source_type}\n"
                f"Location/URI: {doc.path_or_uri}\n"
                f"{grounding_links_info}"
                f"Content:\n{doc.content}\n"
                f"=== END SOURCE [{doc.cite_id}] ==="
            )
            context_blocks.append(block)

        unified_context = "\n\n".join(context_blocks)

        system_instruction = (
            "You are the OmniResearch Studio Grounded Synthesis Engine.\n"
            "OPERATIONAL MANDATES:\n"
            "1. Strict Grounding: Base your entire synthesis exclusively on the provided SOURCE blocks.\n"
            "2. Mandatory Bracketed Citations: Every factual claim, metric, technical mechanism, or argument "
            "MUST include inline bracketed citation markers corresponding to the source ID, such as [1], [2:p.5], or [1, 3].\n"
            "3. Zero Fabrication: If the provided sources do not contain enough evidence to answer a specific aspect "
            "of the user's query, state explicitly what is missing from the current corpus rather than speculating.\n"
            "4. Structural Clarity: Organize the synthesis with executive precision using Markdown headings, "
            "comparative tables where appropriate, synthesis across conflicting perspectives, and a concluding summary.\n"
            f"5. {EPISTEMIC_FRICTION_MANDATE}\n\n"
            f"6. {STRICT_FORMATTING_RULE}\n\n"
            "7. CAUSAL & ARGUMENT GRAPH MANDATE:\n"
            "Generate a structured causal failure or argument dependency diagram using Mermaid syntax inside a dedicated block:\n"
            "```mermaid\n"
            "graph TD\n"
            '  A["Root Mechanism / Primary Cause"] -->|leads to| B["Intermediate Consequence"]\n'
            '  B --> C["Observed Empirical Outcome / Failure Mode"]\n'
            "```\n"
            "Focus the graph on structural trade-offs, engineering failure chains, or institutional decision trees with labeled edges.\n\n"
            "8. TEMPORAL SEQUENCE & CHRONOLOGY MANDATE:\n"
            "Include a dedicated chronological milestone table titled:\n"
            "## Temporal Sequence & Chronology:\n"
            "| Date / Period | Milestone / Event | Empirical Outcome | Primary Citation |\n"
            "Every row must capture empirical progression grounded with [N] or [N:p.X] citations.\n\n"
            f"{OUTPUT_LANGUAGE_CONSTRAINT}"
        )

        # Evaluate context token scale for explicit context caching (> 32,768 tokens)
        estimated_corpus_tokens = sum(doc.estimated_tokens for doc in docs_for_context)
        cached_content_name: Optional[str] = None
        if not is_local_model(self.model_name) and self.client is not None and estimated_corpus_tokens > 32768:
            cached_content_name = ContextCacheStore.get_instance().get_or_create_cache(
                client=self.client,
                model_name=self.model_name,
                unified_context=unified_context,
            )

        if cached_content_name:
            prompt = (
                f"USER SYNTHESIS QUERY:\n{cleaned_query}\n\n"
                f"{EPISTEMIC_FRICTION_MANDATE}\n\n"
                f"{OUTPUT_LANGUAGE_CONSTRAINT}\n\n"
                f"{STRICT_FORMATTING_RULE}\n\n"
                "Generate a comprehensive, strictly grounded synthesis report in clear, rigorous academic ENGLISH "
                "with inline bracketed citations [N] or [N:p.X] mapping directly to the numbered sources in the cached corpus."
            )
            config = types.GenerateContentConfig(
                cached_content=cached_content_name,
                system_instruction=system_instruction,
                temperature=0.0,
            )
        else:
            prompt = (
                f"UNIFIED SOURCE CORPUS ({len(docs_for_context)} Active Sources):\n\n"
                f"{unified_context}\n\n"
                f"---\n"
                f"USER SYNTHESIS QUERY:\n{cleaned_query}\n\n"
                f"{EPISTEMIC_FRICTION_MANDATE}\n\n"
                f"{OUTPUT_LANGUAGE_CONSTRAINT}\n\n"
                f"{STRICT_FORMATTING_RULE}\n\n"
                "Generate a comprehensive, strictly grounded synthesis report in clear, rigorous academic ENGLISH "
                "with inline bracketed citations [N] or [N:p.X] mapping directly to the numbered sources above."
            )
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0,
            )

        # Pre-flight sensitive token scrubber hook
        prompt, redact_count = scrub_sensitive_patterns(prompt)
        if redact_count > 0 and progress_callback:
            progress_callback(f"Security: {redact_count} sensitive tokens masked prior to API dispatch.")

        full_chunks: List[str] = []
        max_continuations = 3
        continuation_idx = 0
        hit_max_tokens = False
        last_usage_metadata: Any = None

        if is_local_model(self.model_name):
            local_client = LocalLLMClient()
            messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ]
            accumulated: List[str] = []
            for piece in local_client.stream_chat(self.model_name, messages=messages, temperature=0.0):
                if cancel_check and cancel_check():
                    raise TaskCancelledError("Task aborted by user.")
                accumulated.append(piece)
                if chunk_callback is not None:
                    chunk_callback(piece)
            full_chunks.append("".join(accumulated))
        else:
            def _stream_generation(prompt_contents: str) -> tuple[str, bool]:
                nonlocal hit_max_tokens, last_usage_metadata
                accumulated: List[str] = []
                hit_max_tokens = False
                stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    contents=prompt_contents,
                    config=config,
                )
                for chunk in stream:
                    if cancel_check and cancel_check():
                        raise TaskCancelledError("Task aborted by user.")
                    piece = getattr(chunk, "text", None) or ""
                    if piece:
                        accumulated.append(piece)
                        if chunk_callback is not None:
                            chunk_callback(piece)
                    if hasattr(chunk, "candidates") and chunk.candidates:
                        cand = chunk.candidates[0]
                        if hasattr(cand, "finish_reason") and cand.finish_reason:
                            if "MAX_TOKENS" in str(cand.finish_reason).upper():
                                hit_max_tokens = True
                    if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                        last_usage_metadata = chunk.usage_metadata
                return "".join(accumulated), hit_max_tokens

            part_text, hit_max_tokens = call_with_exponential_backoff(
                lambda: _stream_generation(prompt),
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            full_chunks.append(part_text)

            while hit_max_tokens and continuation_idx < max_continuations:
                if cancel_check and cancel_check():
                    raise TaskCancelledError("Task aborted by user.")
                continuation_idx += 1
                if progress_callback:
                    progress_callback(
                        f"Output token limit reached. Resuming stream continuation {continuation_idx}/{max_continuations}..."
                    )
                combined_so_far = "".join(full_chunks)
                trailing_snippet = combined_so_far[-600:] if len(combined_so_far) > 600 else combined_so_far
                continuation_prompt = (
                    f"Continue the synthesis report seamlessly from exactly where it was cut off. "
                    f"Do not repeat any preceding text. Pick up precisely from this trailing context:\n\n"
                    f'"""\n{trailing_snippet}\n"""\n\n'
                    f"Maintain rigorous grounding with [N] or [N:p.X] citations.\n"
                    f"{EPISTEMIC_FRICTION_MANDATE}\n"
                    f"{OUTPUT_LANGUAGE_CONSTRAINT}\n"
                    f"{STRICT_FORMATTING_RULE}"
                )
                continuation_prompt, _ = scrub_sensitive_patterns(continuation_prompt)
                part_text, hit_max_tokens = call_with_exponential_backoff(
                    lambda: _stream_generation(continuation_prompt),
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )
                full_chunks.append(part_text)

        report_text = sanitize_unclosed_markdown("".join(full_chunks)).strip()

        if not report_text:
            report_text = "Synthesis completed, but no text was generated by the model."

        # Record exact billing telemetry to TokenLedger
        try:
            if last_usage_metadata:
                TokenLedger.get_instance().record_usage(
                    model=self.model_name,
                    usage_metadata=last_usage_metadata,
                    session_id="synthesis",
                )
            else:
                TokenLedger.get_instance().record_manual(
                    model=self.model_name,
                    prompt_tokens=max(1, len(prompt) // 4),
                    candidate_tokens=max(1, len(report_text) // 4),
                    cached_tokens=32768 if cached_content_name else 0,
                    session_id="synthesis",
                )
        except Exception:
            pass

        citations_used = self.extract_citations_for_documents(report_text, active_docs)

        # Phase 8: Epistemic Entailment Critic Agent for borderline citations
        critic_verdicts: Dict[Tuple[int, Optional[int]], Any] = {}
        try:
            critic = CriticAgent()
            borderlines = critic.identify_borderline_citations(report_text, active_docs)
            for item in borderlines[:5]:
                verdict = critic.evaluate_entailment_sync(
                    item["sentence"], item["source_excerpt"], item["cite_id"], item["page_num"]
                )
                critic_verdicts[(item["cite_id"], item["page_num"])] = verdict
        except Exception:
            critic_verdicts = {}

        return SynthesisResult(
            query=cleaned_query,
            model_used=self.model_name,
            markdown_report=report_text,
            citations_used=citations_used,
            total_sources_provided=len(active_docs),
            critic_verdicts=critic_verdicts,
            was_pruned=was_pruned,
            pruner_telemetry=pruner_telemetry,
        )

    @classmethod
    def extract_citations_for_documents(
        cls,
        report_text: str,
        documents: List[SourceDocument],
    ) -> List[CitationMatch]:
        """Extract bracketed citation matches against a list of SourceDocuments."""
        doc_map = {doc.cite_id: doc for doc in documents}
        return cls._extract_citation_matches(report_text, doc_map)

    @staticmethod
    def _extract_citation_matches(
        report_text: str,
        doc_map: Dict[int, SourceDocument],
    ) -> List[CitationMatch]:
        """Parse bracketed citation markers (e.g., [1], [2:p.5], [1, 4]) and count occurrences."""
        counts: Dict[int, int] = {}
        bracket_groups = re.findall(r"\[([0-9:p\.,\s]+)\]", report_text)
        for group in bracket_groups:
            for token in group.split(","):
                token_str = token.strip()
                if ":p." in token_str:
                    token_str = token_str.split(":p.")[0].strip()
                if token_str.isdigit():
                    cid = int(token_str)
                    if cid in doc_map:
                        counts[cid] = counts.get(cid, 0) + 1

        matches: List[CitationMatch] = []
        for cid in sorted(counts.keys()):
            doc = doc_map[cid]
            snippet = getattr(doc, "summary_snippet", doc.content[:160])
            matches.append(
                CitationMatch(
                    cite_id=cid,
                    title=doc.title,
                    source_type=doc.source_type,
                    path_or_uri=doc.path_or_uri,
                    excerpt=snippet,
                    occurrences=counts[cid],
                )
            )
        return matches
