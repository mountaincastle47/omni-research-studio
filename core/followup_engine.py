"""Grounded follow-up Q&A engine: streams answers strictly grounded in the synthesis report, corpus, and chat history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

from google import genai
from google.genai import types

from core.document_loader import SourceDocument
from core.notebook_synthesis import ContextCacheStore
from core.resilience import TaskCancelledError, call_with_exponential_backoff
from core.security_filter import scrub_sensitive_patterns
from core.storm_discovery import STRICT_FORMATTING_RULE
from core.token_ledger import TokenLedger

FOLLOWUP_MODEL = "gemini-3.8-flash"
MAX_SOURCE_CHARS = 14000  # per-source context ceiling to keep multi-turn prompts bounded
MAX_HISTORY_TURNS = 12


@dataclass
class ChatTurn:
    """One chat message in the follow-up conversation."""

    role: str  # "user" or "assistant"
    text: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "text": self.text}


class FollowUpEngine:
    """Answers follow-up questions strictly from the completed report + active corpus with inline [N] citations."""

    def __init__(self, client: genai.Client, model_name: str = FOLLOWUP_MODEL) -> None:
        self.client = client
        self.model_name = model_name

    @staticmethod
    def build_context(synthesis_report: str, documents: Sequence[SourceDocument]) -> str:
        """Assemble the grounding context: numbered SOURCE blocks followed by the completed synthesis report."""
        blocks: List[str] = []
        for doc in documents:
            if not doc.enabled:
                continue
            content = doc.content if len(doc.content) <= MAX_SOURCE_CHARS else doc.content[:MAX_SOURCE_CHARS] + "\n[...truncated]"
            blocks.append(
                f"=== SOURCE [{doc.cite_id}] ===\n"
                f"Title: {doc.title}\n"
                f"Location/URI: {doc.path_or_uri}\n"
                f"Content:\n{content}\n"
                f"=== END SOURCE [{doc.cite_id}] ==="
            )
        sources_block = "\n\n".join(blocks) if blocks else "(no active sources)"
        report_block = synthesis_report.strip() or "(no synthesis report has been generated yet)"
        return f"ACTIVE SOURCES:\n\n{sources_block}\n\n---\nCOMPLETED GROUNDED SYNTHESIS REPORT:\n\n{report_block}"

    def build_system_instruction(self, synthesis_report: str, documents: Sequence[SourceDocument], answer_language: str) -> str:
        language_rule = (
            "Answer in natural, professional Korean (한국어). Keep technical designations in their original script and keep "
            "bracketed citation markers exactly as [N]."
            if answer_language.lower().startswith("ko")
            else "Answer in clear, rigorous English."
        )
        return (
            "You are the OmniResearch Studio Follow-Up Analyst.\n"
            "OPERATIONAL MANDATES:\n"
            "1. Strict Grounding: Answer the follow-up inquiry strictly grounded in the provided synthesis report and active corpus below, plus prior conversation turns.\n"
            "2. Mandatory Bracketed Citations: Whenever citing assertions, always insert bracketed citations [N] or [N:p.X] matching the primary sources. Never invent a source number that does not exist below.\n"
            "3. Zero Fabrication: If the corpus does not contain the answer, explicitly state that the evidence is absent rather than hallucinating.\n"
            "4. Be concise and direct; use short paragraphs or bullet points with bold lead-ins.\n"
            f"5. {language_rule}\n"
            f"6. {STRICT_FORMATTING_RULE}\n\n"
            f"{self.build_context(synthesis_report, documents)}"
        )

    @staticmethod
    def build_contents(question: str, history: Sequence[Dict[str, str]]) -> List[types.Content]:
        """Convert chat history + the new question into Gemini multi-turn `contents`."""
        trimmed = list(history)[-MAX_HISTORY_TURNS * 2 :]
        contents: List[types.Content] = []
        for entry in trimmed:
            role = "model" if entry.get("role") == "assistant" else "user"
            text = str(entry.get("text", "")).strip()
            if text:
                contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
        contents.append(types.Content(role="user", parts=[types.Part(text=question.strip())]))
        return contents

    def stream_answer(
        self,
        question: str,
        synthesis_report: str,
        documents: Sequence[SourceDocument],
        history: Sequence[Dict[str, str]] = (),
        answer_language: str = "en",
        chunk_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        """Stream a grounded answer token-by-token; returns the complete answer text."""
        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("Follow-up question cannot be empty.")
        if not synthesis_report.strip() and not any(d.enabled for d in documents):
            raise ValueError("Follow-up questions require a synthesis report or at least one enabled source.")
        if cancel_check and cancel_check():
            raise TaskCancelledError("Task aborted by user.")

        system_inst = self.build_system_instruction(synthesis_report, documents, answer_language)
        grounding_context = self.build_context(synthesis_report, documents)

        cached_content_name: Optional[str] = None
        if len(grounding_context) > 130000:
            cached_content_name = ContextCacheStore.get_instance().get_or_create_cache(
                client=self.client,
                model_name=self.model_name,
                unified_context=grounding_context,
            )

        if cached_content_name:
            config = types.GenerateContentConfig(
                cached_content=cached_content_name,
                system_instruction=system_inst,
                temperature=0.1,
            )
        else:
            config = types.GenerateContentConfig(
                system_instruction=system_inst,
                temperature=0.1,
            )
        cleaned_question, _ = scrub_sensitive_patterns(cleaned_question)
        contents = self.build_contents(cleaned_question, history)
        last_usage_metadata: Any = None

        def _stream() -> str:
            nonlocal last_usage_metadata
            parts: List[str] = []
            stream = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            for chunk in stream:
                if cancel_check and cancel_check():
                    raise TaskCancelledError("Task aborted by user.")
                piece = getattr(chunk, "text", None) or ""
                if piece:
                    parts.append(piece)
                    if chunk_callback is not None:
                        chunk_callback(piece)
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    last_usage_metadata = chunk.usage_metadata
            return "".join(parts)

        answer = call_with_exponential_backoff(
            _stream,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        ).strip()
        if not answer:
            raise RuntimeError("The model returned an empty follow-up answer.")

        try:
            if last_usage_metadata:
                TokenLedger.get_instance().record_usage(
                    model=self.model_name,
                    usage_metadata=last_usage_metadata,
                    session_id="followup",
                )
            else:
                TokenLedger.get_instance().record_manual(
                    model=self.model_name,
                    prompt_tokens=max(1, len(grounding_context) // 4),
                    candidate_tokens=max(1, len(answer) // 4),
                    cached_tokens=32768 if cached_content_name else 0,
                    session_id="followup",
                )
        except Exception:
            pass

        return answer

    # Alias for stream_answer
    stream_followup = stream_answer
