"""Configuration and Gemini API key management for OmniResearch Studio."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from google import genai


CONFIG_DIR = Path.home() / ".omniresearch_studio"
CONFIG_FILE = CONFIG_DIR / "config.json"

AVAILABLE_MODELS: List[str] = [
    "gemini-4-argon",
    "gemini-3.1-pro-preview",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
]

DISCOVERY_MODELS: List[str] = AVAILABLE_MODELS
SYNTHESIS_MODELS: List[str] = AVAILABLE_MODELS

DEFAULT_DISCOVERY_MODEL = "gemini-3.8-flash"
DEFAULT_SYNTHESIS_MODEL = "gemini-4-argon"

DEFAULT_PERSPECTIVES: List[Dict[str, str]] = [
    {
        "id": "systems_architect",
        "name": "Systems & Technical Architect",
        "role": "Evaluates underlying mechanisms, scalability, hardware/software bottlenecks, and structural engineering trade-offs.",
    },
    {
        "id": "empirical_skeptic",
        "name": "Empirical & Methodological Skeptic",
        "role": "Audits data validity, identifies confounding variables, exposes unverified assumptions, and searches for counter-evidence.",
    },
    {
        "id": "domain_strategist",
        "name": "Applied Domain & Economic Strategist",
        "role": "Analyzes real-world deployment constraints, cost-benefit dynamics, regulatory landscapes, and long-term industry impact.",
    },
    {
        "id": "historical_comparativist",
        "name": "Historical & Comparative Analyst",
        "role": "Contextualizes findings against prior art, parallel precedents, and evolutionary trajectories across related fields.",
    },
]


@dataclass
class AppConfig:
    """Application runtime configuration."""

    api_key: str = ""
    discovery_model: str = DEFAULT_DISCOVERY_MODEL
    synthesis_model: str = DEFAULT_SYNTHESIS_MODEL
    audio_model: str = DEFAULT_DISCOVERY_MODEL
    synthesis_temperature: float = 0.0
    discovery_temperature: float = 0.3
    audio_temperature: float = 0.6
    max_output_tokens: int = 8192
    perspectives: List[Dict[str, str]] = field(default_factory=lambda: list(DEFAULT_PERSPECTIVES))


from core.config_manager import ConfigManager
