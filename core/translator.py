"""Markdown report translator using gemini-3.8-flash with live token streaming and strict citation preservation."""

from __future__ import annotations

import logging
import re
from typing import Callable, List, Optional

from google import genai
from google.genai import types

from core.config import DEFAULT_DISCOVERY_MODEL
from core.resilience import TaskCancelledError, call_with_exponential_backoff
from core.storm_discovery import STRICT_FORMATTING_RULE


logger = logging.getLogger("OmniResearch.Translator")

TRANSLATION_MODEL = DEFAULT_DISCOVERY_MODEL  # "gemini-3.8-flash"
DEFAULT_MAX_CHUNK_CHARS = 3500


def split_markdown_into_chunks(markdown_text: str, max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS) -> List[str]:
    """
    Split large Markdown reports into semantically coherent sections along heading
    and paragraph boundaries, guaranteeing individual requests remain well below
    gateway stream deadlines while preserving citation anchors and document structure.
    """
    text = markdown_text.strip()
    if not text or len(text) <= max_chunk_chars:
        return [text] if text else []

    # 1. Split on major Markdown headings (#, ##, ###)
    heading_re = re.compile(r'(?=\n\#{1,3}\s+)')
    raw_sections = heading_re.split(text)

    sections: List[str] = []
    for s in raw_sections:
        s_clean = s.strip()
        if not s_clean:
            continue
        # If an individual section still exceeds max_chunk_chars, split on paragraph breaks
        if len(s_clean) > max_chunk_chars:
            paras = s_clean.split("\n\n")
            p_chunk: List[str] = []
            p_len = 0
            for p in paras:
                p_str = p.strip()
                if not p_str:
                    continue
                if p_len + len(p_str) + 2 > max_chunk_chars and p_chunk:
                    sections.append("\n\n".join(p_chunk))
                    p_chunk = [p_str]
                    p_len = len(p_str)
                else:
                    p_chunk.append(p_str)
                    p_len += len(p_str) + 2
            if p_chunk:
                sections.append("\n\n".join(p_chunk))
        else:
            sections.append(s_clean)

    # 2. Merge small sections into coherent chunks up to max_chunk_chars
    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for s in sections:
        if cur_len + len(s) + 2 > max_chunk_chars and cur:
            chunks.append("\n\n".join(cur))
            cur = [s]
            cur_len = len(s)
        else:
            cur.append(s)
            cur_len += len(s) + 2
    if cur:
        chunks.append("\n\n".join(cur))

    return chunks


class MarkdownTranslator:
    """Translates Markdown research reports between English and Korean while preserving citations and structure."""

    def __init__(self, client: genai.Client, model_name: str = TRANSLATION_MODEL) -> None:
        self.client = client
        self.model_name = model_name

    def translate_markdown(
        self,
        markdown_text: str,
        target_lang: str = "ko",
        progress_callback: Optional[Callable[[str], None]] = None,
        chunk_callback: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    ) -> str:
        """
        Translate `markdown_text` into `target_lang` ('ko' or 'en') via chunked section streaming.
        Large documents are segmented into bounded sections so individual calls complete well within
        API gateway deadlines. Transient errors (504, 503, timeouts) are retried with exponential backoff.
        """
        if cancel_check and cancel_check():
            raise TaskCancelledError("Task aborted by user.")

        cleaned = markdown_text.strip()
        if not cleaned:
            return ""

        lang_label = "Korean (한국어)" if target_lang.lower().startswith("ko") else "English"

        system_instruction = (
            f"You are an expert technical translator for OmniResearch Studio.\n"
            f"Translate the provided research document into {lang_label}.\n\n"
            "STRICT FORMATTING & CITATION MANDATES:\n"
            "1. Preserve ALL Markdown structure verbatim: headings (#, ##, ###), bullet lists (-, *), numbered lists, "
            "tables, horizontal rules (---), code blocks, italic/bold spans, and hyperlinks.\n"
            "2. Preserve ALL bracketed citation markers and source tags EXACTLY as written without modification, "
            "such as `[1]`, `[2, 4]`, `[Doc: ...]`, `[WEB SWEEP: ...]`, or `[Systems & Technical Architect]`.\n"
            "3. Keep technical terms, model identifiers (e.g., `gemini-4-argon`, `gemini-3.8-flash`), and URLs accurate.\n"
            "4. Output ONLY the translated Markdown text without any introductory or concluding commentary.\n"
            f"5. {STRICT_FORMATTING_RULE}"
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.1,
        )

        # Split large documents into bounded sections
        chunks = split_markdown_into_chunks(cleaned, max_chunk_chars=max_chunk_chars)
        total_chunks = len(chunks)
        translated_chunks: List[str] = []

        for idx, chunk_text in enumerate(chunks, start=1):
            if cancel_check and cancel_check():
                raise TaskCancelledError("Task aborted by user.")

            if total_chunks > 1:
                section_msg = f"Translating report section {idx}/{total_chunks}..."
                if progress_callback is not None:
                    progress_callback(section_msg)

            def _stream_chunk(text_to_translate: str) -> str:
                accumulated: List[str] = []
                stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    contents=text_to_translate,
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
                return "".join(accumulated)

            try:
                translated_piece = call_with_exponential_backoff(
                    lambda t=chunk_text: _stream_chunk(t),
                    max_retries=4,
                    initial_wait=2.0,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                ).strip()
            except TaskCancelledError:
                raise
            except Exception as exc:
                # Resilient fallback: if an individual section fails after retries,
                # preserve the original section text and proceed rather than aborting everything.
                logger.error(
                    f"Failed to translate chunk {idx}/{total_chunks}: {exc}. Preserving source text for this section."
                )
                translated_piece = chunk_text
                if chunk_callback is not None:
                    chunk_callback(chunk_text)

            translated_chunks.append(translated_piece if translated_piece else chunk_text)

            # Separate multi-section streams with clean newlines
            if idx < total_chunks and chunk_callback is not None:
                chunk_callback("\n\n")

        full_translation = "\n\n".join(translated_chunks).strip()
        return full_translation if full_translation else cleaned
