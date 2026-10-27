"""Radar chart component alias for epistemic balance and source diversity visualization."""

from __future__ import annotations

from ui.balance_radar import EpistemicBalanceWidget, _RadarCanvas

RadarChartWidget = EpistemicBalanceWidget

__all__ = ["EpistemicBalanceWidget", "RadarChartWidget", "_RadarCanvas"]
