"""Multi-Modal Schematic & Diagram Vision Analysis: Deconstructs technical schematics using Gemini Vision."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PIL import Image

from core.config import ConfigManager, DEFAULT_SYNTHESIS_MODEL
from core.local_llm_client import is_local_model


VISION_PROMPT_TEMPLATE = (
    "Conduct a rigorous engineering and technical deconstruction of this extracted figure within the context of: '{query}'. "
    "Transcribe embedded data curves, structural labels, failure points, and legend values. "
    "Format output as clean Markdown containing a structured data table and an analytical engineering summary."
)


class VisionAnalyzer:
    """Dispatches multi-modal schematic analysis requests to Gemini Vision."""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.config_manager = config_manager or ConfigManager()
        self._explicit_api_key = api_key

    def analyze_figure(
        self,
        image_path: str | Path,
        query: str = "",
        model_name: str = DEFAULT_SYNTHESIS_MODEL,
        stream_callback: Optional[Callable[[str], None]] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Analyze an extracted diagram or figure image with Gemini Vision multi-modal API.
        Transcribes embedded data tables, structural labels, and failure points into clean Markdown.
        """
        callback = stream_callback or on_chunk
        path = Path(image_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Figure image not found: {path}")

        prompt = VISION_PROMPT_TEMPLATE.format(query=query.strip() or "General Engineering Schematic Analysis")

        # Handle local models (vision not supported locally)
        if is_local_model(model_name):
            return (
                f"### [Vision Analysis Notice]\n"
                f"Local model `{model_name}` does not currently support multi-modal image tensor processing. "
                f"Please select a cloud Gemini model (`gemini-3.8-flash` or `gemini-4-argon`) for schematic deconstruction."
            )

        api_key = self._explicit_api_key or self.config_manager.get_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured for vision analysis.")

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            with Image.open(path) as img:
                # Copy into memory to avoid file locks
                img_copy = img.copy()

            if callback:
                full_chunks: list[str] = []
                response_stream = client.models.generate_content_stream(
                    model=model_name,
                    contents=[img_copy, prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                    ),
                )
                for chunk in response_stream:
                    txt = getattr(chunk, "text", "") or ""
                    if txt:
                        full_chunks.append(txt)
                        callback(txt)
                return "".join(full_chunks)
            else:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[img_copy, prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                    ),
                )
                return getattr(response, "text", "") or "[No vision analysis returned.]"

        except Exception as exc:
            # Fallback format if network or rate limit occurs
            return (
                f"### [Vision Analysis Fallback: {path.name}]\n\n"
                f"*Query Context:* {query or 'N/A'}\n\n"
                f"| Component / Metric | Transcribed Designation | Status / Value |\n"
                f"| :--- | :--- | :--- |\n"
                f"| Image File | `{path.name}` | Extracted schematic bitmap |\n"
                f"| Analysis Error | `{type(exc).__name__}` | {exc} |\n\n"
                f"**Analytical Summary:** Vision model query failed or reached rate limits. "
                f"Verify API key quota and network connectivity."
            )
