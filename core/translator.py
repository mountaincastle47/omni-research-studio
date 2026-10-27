"""Markdown report translator using gemini-3.8-flash with live token streaming and strict citation preservation."""

from __future__ import annotations

from typing import Callable, List, Optional

from google import genai
from google.genai import types

from core.config import DEFAULT_DISCOVERY_MODEL
from core.resilience import TaskCancelledError, call_with_exponential_backoff
from core.storm_discovery import STRICT_FORMATTING_RULE


TRANSLATION_MODEL = DEFAULT_DISCOVERY_MODEL  # "gemini-3.8-flash"


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
    ) -> str:
        """Translate `markdown_text` into `target_lang` ('ko' or 'en') via live token streaming."""
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

        def _stream_translation() -> str:
            accumulated: List[str] = []
            stream = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=cleaned,
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

        translated = call_with_exponential_backoff(
            _stream_translation,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        ).strip()

        return translated if translated else cleaned
