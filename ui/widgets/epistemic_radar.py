"""Epistemic Balance and Evidence Distribution Radar Widget."""

from __future__ import annotations

from ui.balance_radar import (
    AXIS_EXPLANATIONS,
    EpistemicBalanceWidget,
    _RadarCanvas,
)

EpistemicRadarWidget = EpistemicBalanceWidget

__all__ = [
    "EpistemicBalanceWidget",
    "EpistemicRadarWidget",
    "_RadarCanvas",
    "AXIS_EXPLANATIONS",
]
