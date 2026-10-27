"""Zero-egress air-gapped local LLM bridge for Ollama, vLLM, and OpenAI-compatible inference servers."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

import httpx

DEFAULT_OLLAMA_URL = "http://localhost:11434/v1"
DEFAULT_VLLM_URL = "http://localhost:8000/v1"


def is_local_model(model_name: str) -> bool:
    """Return True if the model identifier routes to a local air-gapped server."""
    lowered = model_name.strip().lower()
    return (
        lowered.startswith("ollama:")
        or lowered.startswith("vllm:")
        or lowered.startswith("local:")
        or "localhost" in lowered
    )


class LocalLLMClient:
    """HTTP client communicating with local OpenAI-compatible inference endpoints."""

    def __init__(
        self,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        vllm_url: str = DEFAULT_VLLM_URL,
        timeout: float = 60.0,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.vllm_url = vllm_url.rstrip("/")
        self.timeout = timeout

    def _resolve_url_and_model(self, model_spec: str) -> tuple[str, str]:
        """Parse 'Ollama: llama3' -> (http://localhost:11434/v1, llama3)."""
        parts = model_spec.split(":", 1)
        if len(parts) == 2:
            prefix, real_model = parts[0].strip().lower(), parts[1].strip()
            if prefix == "ollama":
                return self.ollama_url, real_model
            elif prefix in ("vllm", "local"):
                return self.vllm_url, real_model
        return self.ollama_url, model_spec.strip()

    def list_local_models(self, timeout_sec: float = 1.5) -> List[str]:
        """Probe local servers and return available local model identifiers."""
        models: List[str] = []

        # 1. Probe Ollama
        try:
            with httpx.Client(timeout=timeout_sec) as client:
                res = client.get(f"{self.ollama_url}/models")
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("data", []):
                        m_id = item.get("id")
                        if m_id:
                            models.append(f"Ollama: {m_id}")
        except Exception:
            pass

        # 2. Probe vLLM / Local OpenAI
        try:
            with httpx.Client(timeout=timeout_sec) as client:
                res = client.get(f"{self.vllm_url}/models")
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("data", []):
                        m_id = item.get("id")
                        if m_id:
                            models.append(f"vLLM: {m_id}")
        except Exception:
            pass

        return models

    def stream_chat(
        self,
        model_spec: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Stream response text deltas from the local endpoint."""
        base_url, actual_model = self._resolve_url_and_model(model_spec)
        url = f"{base_url}/chat/completions"
        payload = {
            "model": actual_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk_json = json.loads(data_str)
                            delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except Exception:
                            pass

    def generate_chat(
        self,
        model_spec: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
    ) -> str:
        """Execute synchronous chat completion against local endpoint."""
        base_url, actual_model = self._resolve_url_and_model(model_spec)
        url = f"{base_url}/chat/completions"
        payload = {
            "model": actual_model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        with httpx.Client(timeout=self.timeout) as client:
            res = client.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
            return str(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
