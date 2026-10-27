"""Two-host conversational Audio Overview: script generation (live streaming) and edge-tts neural voice rendering."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from mutagen.id3 import CHAP, ID3, TALB, TIT2, TPE1, ID3NoHeaderError

from google import genai
from google.genai import types

from core.config import DEFAULT_DISCOVERY_MODEL
from core.document_loader import SourceDocument
from core.paths import get_app_root, get_cache_dir, SESSION_CACHE_DIR
from core.resilience import TaskCancelledError, call_with_exponential_backoff

PROJECT_ROOT = get_app_root()
AUDIO_BRIEFING_FILENAME = "audio_briefing.mp3"

SILENT_MP3_FRAME = b"\xff\xfb\x90\x64" + (b"\x00" * 413)
SILENT_MP3_BUFFER_200MS = SILENT_MP3_FRAME * 8
SILENT_MP3_BUFFER_280MS = SILENT_MP3_FRAME * 11


def build_prosody_ssml(text: str, speaker: str) -> str:
    """Format dialogue text into SSML with prosody pitch and rate tags per host persona."""
    is_host_b = "host b" in speaker.lower() or "sam" in speaker.lower() or speaker.lower().strip() == "b"
    rate = "+6%" if is_host_b else "+3%"
    pitch = "+3Hz" if is_host_b else "-2Hz"
    clean_line = html.escape(re.sub(r"\s+", " ", text).strip())
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        f'<prosody rate="{rate}" pitch="{pitch}">{clean_line}</prosody>'
        f'<break time="280ms"/>'
        f"</speak>"
    )


def safe_remove_file(filepath: Path | str, attempts: int = 3, delay: float = 0.15) -> bool:
    """Safely delete a file on Windows, retrying to handle transient lock/WinError 32 issues."""
    p = Path(filepath)
    if not p.exists():
        return True
    for attempt in range(attempts):
        try:
            p.unlink()
            return True
        except (PermissionError, OSError):
            if attempt < attempts - 1:
                time.sleep(delay)
    return not p.exists()

VOICE_MAP: Dict[str, Dict[str, str]] = {
    "en": {"A": "en-US-GuyNeural", "B": "en-US-AriaNeural"},
    "ko": {"A": "ko-KR-InJoonNeural", "B": "ko-KR-SunHiNeural"},
}

_CITATION_MARKER_RE = re.compile(r"\[\s*\d+(?:\s*,\s*\d+)*\s*\]")
_MARKDOWN_NOISE_RE = re.compile(r"[*_`#>]+")
_URL_RE = re.compile(r"https?://\S+")


@dataclass
class DialogueTurn:
    """Single conversational turn in the two-host audio overview."""

    speaker: str  # "Host A (Alex)" or "Host B (Sam)"
    role_tag: str
    text: str


@dataclass
class PodcastScript:
    """Structured two-host conversational script derived from grounded synthesis."""

    title: str
    model_used: str
    turns: List[DialogueTurn] = field(default_factory=list)
    raw_script: str = ""
    from_cache: bool = False


class AudioStudioGenerator:
    """Generates an engaging, deeply technical two-host podcast dialogue from research synthesis."""

    def __init__(self, client: genai.Client, model_name: str = DEFAULT_DISCOVERY_MODEL) -> None:
        self.client = client
        self.model_name = model_name

    def generate_podcast_script(
        self,
        topic_or_query: str,
        synthesis_markdown: str,
        documents: List[SourceDocument],
        focus_instructions: str = "",
        progress_callback: Optional[Callable[[str], None]] = None,
        chunk_callback: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        output_language: str = "en",
    ) -> PodcastScript:
        """Transform a grounded synthesis report and corpus metadata into a two-host script via live streaming."""
        if cancel_check and cancel_check():
            raise TaskCancelledError("Task aborted by user.")

        source_summaries = "\n".join(
            f"- [{doc.cite_id}] {doc.title} ({doc.source_type}): {doc.summary_snippet}"
            for doc in documents
            if doc.enabled
        )

        context_material = synthesis_markdown.strip()
        if not context_material and source_summaries:
            context_material = f"Active Corpus Overview:\n{source_summaries}"
        if not context_material:
            raise ValueError(
                "Cannot generate an Audio Overview without either a synthesis report or enabled corpus documents."
            )

        focus_clause = ""
        if focus_instructions.strip():
            focus_clause = f"\nListener Focus Directive: {focus_instructions.strip()}\n"

        language_rule = (
            "5. LANGUAGE: Write ALL spoken dialogue and the TITLE in natural, fluent, professional Korean (한국어) "
            "suitable for text-to-speech. Keep the speaker labels exactly as 'Host A (Alex):' and 'Host B (Sam):'. "
            "Do not include bracketed citation numbers in spoken text.\n"
            if output_language.lower().startswith("ko")
            else "5. LANGUAGE: Write all spoken dialogue in clear, natural English suitable for text-to-speech. "
            "Do not include bracketed citation numbers in spoken text.\n"
        )

        system_instruction = (
            "You are the Executive Producer of 'OmniResearch Deep Dive', an analytical two-host audio briefing.\n"
            "Hosts:\n"
            "- Host A (Alex): Lead Anchor & Systems Strategist. Structures the narrative, introduces empirical evidence, "
            "and connects high-level architecture to practical outcomes.\n"
            "- Host B (Sam): Investigative Analyst & Methodological Skeptic. Unpacks complex mechanisms, challenges "
            "assumptions, cites specific findings from the sources, and highlights edge cases.\n\n"
            "FORMATTING RULES:\n"
            "1. Begin with a single line: TITLE: <Compelling Episode Title>\n"
            "2. Format every speaking turn strictly on a new line starting with either:\n"
            "   Host A (Alex): <spoken dialogue>\n"
            "   Host B (Sam): <spoken dialogue>\n"
            "3. Keep the dialogue natural, sharp, and technically substantive—avoid generic filler clichés. "
            "Reference specific findings naturally in conversation.\n"
            "4. Produce between 12 and 20 substantive back-and-forth turns, strictly alternating Host A and Host B.\n"
            f"{language_rule}"
        )

        prompt = (
            f"Research Topic / Inquiry: {topic_or_query.strip() or 'Corpus Deep-Dive'}\n"
            f"{focus_clause}\n"
            f"Indexed Sources:\n{source_summaries or 'See synthesis report below.'}\n\n"
            f"Grounded Synthesis Material:\n{context_material}\n\n"
            "Write the complete two-host conversational script now."
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.6,
        )

        def _stream_script() -> str:
            accumulated: List[str] = []
            stream = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
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

        raw_text = call_with_exponential_backoff(
            _stream_script,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        ).strip()

        if not raw_text:
            raise RuntimeError("Model returned an empty podcast script response.")

        return self.build_script_from_raw(
            raw_text=raw_text,
            default_title=topic_or_query or "OmniResearch Audio Overview",
            model_used=self.model_name,
        )

    @classmethod
    def build_script_from_raw(
        cls,
        raw_text: str,
        default_title: str,
        model_used: str = DEFAULT_DISCOVERY_MODEL,
        from_cache: bool = False,
    ) -> PodcastScript:
        """Construct a PodcastScript instance from raw dialogue text."""
        title, turns = cls._parse_dialogue(raw_text, default_title=default_title)
        return PodcastScript(
            title=title,
            model_used=model_used,
            turns=turns,
            raw_script=raw_text,
            from_cache=from_cache,
        )

    @staticmethod
    def _parse_dialogue(raw_text: str, default_title: str) -> tuple[str, List[DialogueTurn]]:
        """Parse raw script lines into structured DialogueTurn items."""
        title = default_title.strip()
        turns: List[DialogueTurn] = []

        pattern = re.compile(
            r"^\s*(?:\*\*?)?(Host\s*A(?:\s*\(Alex\))?|Host\s*B(?:\s*\(Sam\))?|Alex|Sam)(?:\*\*?)?\s*:\s*(.+)$",
            re.IGNORECASE,
        )

        for line in raw_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.upper().startswith("TITLE:"):
                extracted_title = stripped[6:].strip().strip("*\"'")
                if extracted_title:
                    title = extracted_title
                continue

            match = pattern.match(stripped)
            if match:
                raw_speaker = match.group(1).strip()
                spoken = match.group(2).strip()
                if "b" in raw_speaker.lower() or "sam" in raw_speaker.lower():
                    speaker = "Host B (Sam)"
                    role_tag = "Investigative Skeptic"
                else:
                    speaker = "Host A (Alex)"
                    role_tag = "Lead Systems Anchor"
                turns.append(DialogueTurn(speaker=speaker, role_tag=role_tag, text=spoken))
            elif turns:
                turns[-1].text += f" {stripped}"

        if not turns:
            turns.append(
                DialogueTurn(
                    speaker="Host A (Alex)",
                    role_tag="Lead Systems Anchor",
                    text=raw_text,
                )
            )

        return title, turns


class NeuralVoiceSynthesizer:
    """Renders a two-host PodcastScript into a single MP3 using Microsoft Edge neural voices (edge-tts)."""

    def __init__(
        self,
        language: str = "en",
        output_dir: Path | str = SESSION_CACHE_DIR,
        concurrency: int = 3,
        per_segment_timeout: float = 60.0,
        max_attempts: int = 3,
    ) -> None:
        self.language = "ko" if str(language).lower().startswith("ko") else "en"
        self.output_dir = Path(output_dir)
        self.concurrency = max(1, concurrency)
        self.per_segment_timeout = per_segment_timeout
        self.max_attempts = max(1, max_attempts)
        self.last_run_reused: bool = False

    @property
    def output_path(self) -> Path:
        return self.output_dir / AUDIO_BRIEFING_FILENAME

    @property
    def _meta_path(self) -> Path:
        return self.output_dir / "audio_briefing.meta.json"

    @staticmethod
    def clean_spoken_text(text: str) -> str:
        """Strip citation markers, URLs and Markdown noise so the voice reads only natural speech."""
        cleaned = _CITATION_MARKER_RE.sub("", text or "")
        cleaned = _URL_RE.sub("", cleaned)
        cleaned = _MARKDOWN_NOISE_RE.sub("", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def voice_for(self, speaker: str) -> str:
        """Host A -> lead voice, Host B -> second voice (Sam/Host B/B markers select the second voice)."""
        lowered = speaker.lower()
        is_host_b = "host b" in lowered or "sam" in lowered or lowered.strip() == "b"
        return VOICE_MAP[self.language]["B" if is_host_b else "A"]

    def plan_segments(self, script: PodcastScript) -> List[tuple[str, str, str]]:
        """Return ordered (voice, spoken_text, speaker) segments for every non-empty dialogue turn."""
        segments: List[tuple[str, str, str]] = []
        for turn in script.turns:
            spoken = self.clean_spoken_text(turn.text)
            if spoken:
                segments.append((self.voice_for(turn.speaker), spoken, turn.speaker))
        return segments

    def fingerprint(self, script: PodcastScript) -> str:
        payload = json.dumps([(v, t) for (v, t, _) in self.plan_segments(script)], ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def synthesize_script(
        self,
        script: PodcastScript,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        force: bool = False,
    ) -> Path:
        """Synthesize every turn (via asyncio.run inside the calling worker thread) and write audio_briefing.mp3."""
        segments = self.plan_segments(script)
        if not segments:
            raise ValueError("The audio script contains no speakable dialogue.")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        fingerprint = self.fingerprint(script)
        self.last_run_reused = False

        if not force and self.output_path.exists() and self.output_path.stat().st_size > 1024:
            try:
                meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
                if meta.get("fingerprint") == fingerprint:
                    self.last_run_reused = True
                    if progress_callback:
                        progress_callback(len(segments), len(segments))
                    return self.output_path
            except (OSError, ValueError):
                pass

        audio_chunks = asyncio.run(self._synthesize_async(segments, progress_callback, cancel_check))

        # Stitch audio chunks with 280ms silent MP3 buffer to eliminate audio collision/click
        stitched_audio = bytearray()
        for i, chunk in enumerate(audio_chunks):
            if i > 0:
                stitched_audio.extend(SILENT_MP3_BUFFER_280MS)
            stitched_audio.extend(chunk)

        part_path = self.output_path.with_suffix(".mp3.part")
        part_path.write_bytes(bytes(stitched_audio))

        # Defense against Windows file locking (WinError 32)
        safe_remove_file(self.output_path)
        try:
            part_path.replace(self.output_path)
        except (PermissionError, OSError):
            safe_remove_file(self.output_path)
            part_path.replace(self.output_path)

        # Embed ID3 tags and CHAP chapter markers using mutagen
        try:
            try:
                tags = ID3(str(self.output_path))
            except ID3NoHeaderError:
                tags = ID3()

            tags.add(TIT2(encoding=3, text=script.title or "Grounded Research Briefing"))
            tags.add(TPE1(encoding=3, text="Host A (Alex) & Host B (Sam)"))
            tags.add(TALB(encoding=3, text="OmniResearch Studio"))

            # Calculate section timing from chunks and inject native CHAP frames
            silence_ms = 287
            total_chunks = len(audio_chunks)
            if total_chunks > 0:
                durations_ms = [int((len(chunk) / 6000.0) * 1000) for chunk in audio_chunks]
                total_duration_ms = sum(durations_ms) + (silence_ms * max(0, total_chunks - 1))

                ch1_title = "1. Technical Baseline & System Architecture"
                ch2_title = "2. Contested Claims & Empirical Anomalies"
                ch3_title = "3. Strategic Outlook & Synthesis Verdict"

                ch2_idx = max(1, total_chunks // 3)
                ch3_idx = max(2, (2 * total_chunks) // 3)

                for idx, (_, seg_text, _) in enumerate(segments):
                    t_lower = seg_text.lower()
                    if any(w in t_lower for w in ("contested", "anomaly", "discrepan", "contrarian")) and idx < ch3_idx:
                        ch2_idx = idx
                    elif any(w in t_lower for w in ("outlook", "verdict", "strategic", "conclusion")) and idx > ch2_idx:
                        ch3_idx = idx

                t_split1 = sum(durations_ms[:ch2_idx]) + (silence_ms * ch2_idx)
                t_split2 = sum(durations_ms[:ch3_idx]) + (silence_ms * ch3_idx)

                chapters_def = [
                    ("chp1", 0, t_split1, ch1_title),
                    ("chp2", t_split1, t_split2, ch2_title),
                    ("chp3", t_split2, total_duration_ms, ch3_title),
                ]

                for element_id, start_ms, end_ms, ch_title in chapters_def:
                    chap = CHAP(
                        element_id=element_id,
                        start_time=max(0, start_ms),
                        end_time=max(start_ms + 100, end_ms),
                        start_offset=0xFFFFFFFF,
                        end_offset=0xFFFFFFFF,
                        sub_frames=[TIT2(encoding=3, text=ch_title)],
                    )
                    tags.add(chap)

            tags.save(str(self.output_path))
        except Exception:
            pass

        self._meta_path.write_text(
            json.dumps({"fingerprint": fingerprint, "language": self.language, "segments": len(segments)}),
            encoding="utf-8",
        )
        return self.output_path

    async def _synthesize_async(
        self,
        segments: List[tuple[str, str, str]],
        progress_callback: Optional[Callable[[int, int], None]],
        cancel_check: Optional[Callable[[], bool]],
    ) -> List[bytes]:
        import edge_tts

        total = len(segments)
        results: List[Optional[bytes]] = [None] * total
        semaphore = asyncio.Semaphore(self.concurrency)
        done_count = 0

        async def _render_segment(index: int, voice: str, text: str, speaker: str) -> None:
            nonlocal done_count
            async with semaphore:
                last_error: Optional[BaseException] = None
                for attempt in range(1, self.max_attempts + 1):
                    if cancel_check and cancel_check():
                        raise TaskCancelledError("Task aborted by user.")
                    try:
                        results[index] = await asyncio.wait_for(
                            self._collect_audio(edge_tts, voice, text, cancel_check, speaker=speaker),
                            timeout=self.per_segment_timeout,
                        )
                        break
                    except TaskCancelledError:
                        raise
                    except Exception as exc:
                        last_error = exc
                        await asyncio.sleep(0.6 * attempt)
                else:
                    raise RuntimeError(f"Neural voice synthesis failed for segment {index + 1}: {last_error}")
                done_count += 1
                if progress_callback:
                    progress_callback(done_count, total)

        await asyncio.gather(*(_render_segment(i, v, t, s) for i, (v, t, s) in enumerate(segments)))
        return [chunk for chunk in results if chunk]

    @staticmethod
    async def _collect_audio(
        edge_tts_module: object,
        voice: str,
        text: str,
        cancel_check: Optional[Callable[[], bool]],
        speaker: str = "",
    ) -> bytes:
        is_host_b = "host b" in speaker.lower() or "sam" in speaker.lower() or speaker.lower().strip() == "b"
        rate = "+6%" if is_host_b else "+3%"
        pitch = "+3Hz" if is_host_b else "-2Hz"
        communicate = edge_tts_module.Communicate(text, voice, rate=rate, pitch=pitch)  # type: ignore[attr-defined]
        buffer = bytearray()
        async for message in communicate.stream():
            if cancel_check and cancel_check():
                raise TaskCancelledError("Task aborted by user.")
            if message.get("type") == "audio":
                buffer.extend(message["data"])
        if not buffer:
            raise RuntimeError("edge-tts returned no audio data.")
        return bytes(buffer)
