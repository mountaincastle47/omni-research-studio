"""Global thread-safe execution cache manager for zero-token duplicate query protection."""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Dict, List, Optional


class CacheManager:
    """Thread-safe SHA-256 execution cache across Discovery, Synthesis, Audio, and Translation."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._discovery_cache: Dict[str, Dict[str, Any]] = {}
        self._synthesis_cache: Dict[str, str] = {}
        self._audio_cache: Dict[str, str] = {}
        self._translation_cache: Dict[str, str] = {}

    @staticmethod
    def compute_hash(payload: Any) -> str:
        """Compute deterministic SHA-256 hex digest over normalized strings or JSON structures."""
        if isinstance(payload, str):
            normalized = " ".join(payload.strip().split())
        else:
            normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def _make_discovery_key(cls, topic: str, personas: List[str], model: str) -> str:
        normalized_personas = [str(p).strip().lower() for p in sorted(personas)]
        return cls.compute_hash(
            {
                "type": "discovery",
                "topic": " ".join(topic.strip().lower().split()),
                "personas": normalized_personas,
                "model": model.strip().lower(),
            }
        )

    @classmethod
    def _make_synthesis_key(cls, query: str, corpus_hash: str, model: str) -> str:
        return cls.compute_hash(
            {
                "type": "synthesis",
                "query": " ".join(query.strip().lower().split()),
                "corpus_hash": corpus_hash.strip(),
                "model": model.strip().lower(),
            }
        )

    @classmethod
    def _make_audio_key(cls, synthesis_hash: str, directive: str, model: str) -> str:
        return cls.compute_hash(
            {
                "type": "audio",
                "synthesis_hash": synthesis_hash.strip(),
                "directive": " ".join(directive.strip().lower().split()),
                "model": model.strip().lower(),
            }
        )

    @classmethod
    def _make_translation_key(cls, text_hash: str, target_lang: str) -> str:
        return cls.compute_hash(
            {
                "type": "translation",
                "text_hash": text_hash.strip(),
                "target_lang": target_lang.strip().lower(),
            }
        )

    def get_discovery(self, topic: str, personas: list[str], model: str) -> dict | None:
        key = self._make_discovery_key(topic, personas, model)
        with self._lock:
            val = self._discovery_cache.get(key)
            return dict(val) if val is not None else None

    def set_discovery(self, topic: str, personas: list[str], model: str, result: dict) -> None:
        key = self._make_discovery_key(topic, personas, model)
        with self._lock:
            self._discovery_cache[key] = dict(result)

    def get_synthesis(self, query: str, corpus_hash: str, model: str) -> str | None:
        key = self._make_synthesis_key(query, corpus_hash, model)
        with self._lock:
            return self._synthesis_cache.get(key)

    def set_synthesis(self, query: str, corpus_hash: str, model: str, result: str) -> None:
        key = self._make_synthesis_key(query, corpus_hash, model)
        with self._lock:
            self._synthesis_cache[key] = result

    def get_audio(self, synthesis_hash: str, directive: str, model: str) -> str | None:
        key = self._make_audio_key(synthesis_hash, directive, model)
        with self._lock:
            return self._audio_cache.get(key)

    def set_audio(self, synthesis_hash: str, directive: str, model: str, script: str) -> None:
        key = self._make_audio_key(synthesis_hash, directive, model)
        with self._lock:
            self._audio_cache[key] = script

    def get_translation(self, text_hash: str, target_lang: str) -> str | None:
        key = self._make_translation_key(text_hash, target_lang)
        with self._lock:
            return self._translation_cache.get(key)

    def set_translation(self, text_hash: str, target_lang: str, translated_text: str) -> None:
        key = self._make_translation_key(text_hash, target_lang)
        with self._lock:
            self._translation_cache[key] = translated_text

    def clear_all(self) -> None:
        with self._lock:
            self._discovery_cache.clear()
            self._synthesis_cache.clear()
            self._audio_cache.clear()
            self._translation_cache.clear()


GLOBAL_CACHE = CacheManager()
