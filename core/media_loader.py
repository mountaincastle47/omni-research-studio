"""YouTube & Local Audio Media Ingestion: Transcripts, faster-whisper, and timestamp grounding."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

YOUTUBE_URL_PATTERNS = [
    re.compile(r"https?://(?:www\.)?youtube\.com/watch\?(?:.*&)?v=([a-zA-Z0-9_-]{11})"),
    re.compile(r"https?://youtu\.be/([a-zA-Z0-9_-]{11})"),
    re.compile(r"https?://(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})"),
    re.compile(r"https?://(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})"),
]

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def is_youtube_url(text: str) -> bool:
    """Return True if the text contains or matches a valid YouTube URL."""
    clean = text.strip()
    return any(p.search(clean) is not None for p in YOUTUBE_URL_PATTERNS)


def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract the 11-character YouTube video ID from a URL."""
    for pattern in YOUTUBE_URL_PATTERNS:
        match = pattern.search(url.strip())
        if match:
            return match.group(1)
    return None


def format_seconds_to_timestamp(seconds: float | int) -> str:
    """Format total seconds into MM:SS or HH:MM:SS representation."""
    total_sec = max(0, int(round(seconds)))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_timestamp_to_seconds(ts_str: str) -> int:
    """Parse 'MM:SS' or 'HH:MM:SS' into integer seconds."""
    parts = ts_str.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1 and parts[0].isdigit():
            return int(parts[0])
    except ValueError:
        pass
    return 0


def build_youtube_timestamp_url(video_id: str, seconds: int) -> str:
    """Generate canonical youtu.be timestamp URL."""
    return f"https://youtu.be/{video_id}?t={max(0, int(seconds))}"


class MediaLoader:
    """Ingests YouTube video transcripts and local audio files using faster-whisper."""

    @staticmethod
    def fetch_youtube_metadata(video_id: str, timeout: float = 4.0) -> Dict[str, Any]:
        """Fetch video title and author via public YouTube oEmbed endpoint."""
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "title": data.get("title", f"YouTube Video {video_id}"),
                    "author": data.get("author_name", "YouTube Creator"),
                    "thumbnail": data.get("thumbnail_url", ""),
                }
        except Exception:
            pass
        return {
            "title": f"YouTube Video ({video_id})",
            "author": "YouTube",
            "thumbnail": "",
        }

    @staticmethod
    def fetch_youtube_transcript(
        video_id: str,
        preferred_languages: Sequence[str] = ("ko", "en", "en-US", "ja"),
    ) -> List[Dict[str, Any]]:
        """Retrieve timestamped transcript segments from youtube-transcript-api."""
        from youtube_transcript_api import YouTubeTranscriptApi

        try:
            # Preferred language sequence
            return YouTubeTranscriptApi.get_transcript(video_id, languages=preferred_languages)
        except Exception:
            # Fallback to any transcript or auto-generated transcript
            try:
                transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
                for tr in transcript_list:
                    return tr.fetch()
            except Exception as e:
                raise RuntimeError(f"Could not retrieve transcripts for YouTube video {video_id}: {e}") from e

    @classmethod
    def ingest_youtube_url(
        cls,
        url: str,
        preferred_languages: Sequence[str] = ("ko", "en", "en-US"),
    ) -> Dict[str, Any]:
        """Ingest a YouTube video into structured Markdown with <!--TIME:S--> anchors."""
        vid = extract_youtube_video_id(url)
        if not vid:
            raise ValueError(f"Invalid or unrecognized YouTube URL: {url}")

        meta = cls.fetch_youtube_metadata(vid)
        raw_segments = cls.fetch_youtube_transcript(vid, preferred_languages=preferred_languages)

        lines: List[str] = []
        lines.append(f"<!--PAGE_START:1-->\n# [YOUTUBE TRANSCRIPT] {meta['title']}\n")
        lines.append(f"*Creator: {meta['author']} | URL: https://youtu.be/{vid}*\n")

        total_duration = 0.0
        for seg in raw_segments:
            start_sec = float(seg.get("start", 0.0))
            duration = float(seg.get("duration", 0.0))
            text = str(seg.get("text", "")).strip()
            total_duration = max(total_duration, start_sec + duration)

            ts_label = format_seconds_to_timestamp(start_sec)
            sec_int = int(round(start_sec))
            lines.append(f"<!--TIME:{sec_int}-->[{ts_label}] {text}")

        content = "\n".join(lines).strip()
        return {
            "title": f"[YOUTUBE TRANSCRIPT] {meta['title']}",
            "video_id": vid,
            "url": f"https://youtu.be/{vid}",
            "content": content,
            "page_count": 1,
            "duration_seconds": total_duration,
            "segments_count": len(raw_segments),
            "source_type": "web_youtube",
            "metadata": {
                "video_id": vid,
                "author": meta["author"],
                "duration_seconds": total_duration,
                "url": f"https://youtu.be/{vid}",
            },
        }

    @classmethod
    def transcribe_local_audio(
        cls,
        file_path: str | Path,
        model_size: str = "tiny",
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Transcribe local audio file (.mp3, .wav, .m4a) using faster-whisper with INT8 CPU quantization.
        Formats transcript lines with <!--TIME:S--> anchors for timestamp citations.
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        from faster_whisper import WhisperModel

        if progress_callback:
            progress_callback(f"Loading Whisper model ({model_size}) on CPU (int8)...")

        # Load lightweight CPU quantized model
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

        if progress_callback:
            progress_callback(f"Transcribing audio media: {path.name}...")

        segments, info = model.transcribe(str(path), beam_size=1)

        lines: List[str] = []
        lines.append(f"<!--PAGE_START:1-->\n# [AUDIO TRANSCRIPT] {path.name}\n")
        lines.append(f"*Language detected: {info.language} (probability: {info.language_probability:.2f}) | Duration: {info.duration:.1f}s*\n")

        for segment in segments:
            ts_label = format_seconds_to_timestamp(segment.start)
            sec_int = int(round(segment.start))
            lines.append(f"<!--TIME:{sec_int}-->[{ts_label}] {segment.text.strip()}")

        content = "\n".join(lines).strip()
        return {
            "title": f"[AUDIO TRANSCRIPT] {path.name}",
            "file_path": str(path),
            "content": content,
            "page_count": 1,
            "duration_seconds": info.duration,
            "language": info.language,
            "source_type": "local_audio",
            "metadata": {
                "file_path": str(path),
                "duration_seconds": info.duration,
                "language": info.language,
                "file_size_bytes": path.stat().st_size,
            },
        }
