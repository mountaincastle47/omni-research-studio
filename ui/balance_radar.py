"""Dynamic Epistemic Balance & Evidence Distribution Radar: Multi-axis authority and perspective visualization."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from core.citation_audit import CitationAudit
from core.document_loader import SourceDocument
from core.i18n import get_text

AXIS_EXPLANATIONS = {
    "en": {
        "authority": "Authority Ratio: Proportion of primary empirical evidence (academic research, flight logs, official specifications) vs secondary/tertiary reporting.",
        "linguistic": "Global Diversity: Distribution and linguistic variety of cross-lingual international sources preventing regional mono-lingual bias.",
        "dispersion": "Perspective Spread: Diversity of analytical viewpoints (Systems, Empirical, Contrarian, Economic) synthesized in the corpus.",
    },
    "ko": {
        "authority": "1차 문헌 비율: 2차/3차 해설 대비 학술 논문, 공식 시험 비행/시험 데이터, 1차 기술 규격서 등 실증적 1차 자료의 비중입니다.",
        "linguistic": "다국어 다원성: 단일 언어 편향을 방지하는 다국어 교차 검증 수준(영어, 한국어, 독어, 노어, 일어 등)입니다.",
        "dispersion": "시각 분산도: 시스템 엔지니어링, 실증/실험, 회의론/비판, 경제성 등 다각적 분석 관점의 분산도입니다.",
    },
}


class EpistemicBalanceWidget(QWidget):
    """
    Renders an interactive 3-axis radar chart displaying:
    1. Authority Ratio (% Primary Empirical vs. Secondary/Tertiary)
    2. Regional/Linguistic Balance (% Global vs. Regional Native Sources)
    3. Perspective Dispersion (Systems vs. Skeptic vs. Economic vs. Empirical)
    """

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang

        # Metrics normalized between 0.0 and 1.0
        self.authority_score: float = 0.5
        self.linguistic_score: float = 0.5
        self.dispersion_score: float = 0.5

        self.warning_text: str = ""
        self._build_ui()
        self._update_tooltips()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header Title
        self.title_label = QLabel(get_text("epistemic_radar_title", self._lang))
        self.title_label.setStyleSheet("color: #38BDF8; font-weight: 700; font-size: 11px;")
        layout.addWidget(self.title_label)

        # Radar Canvas with guaranteed layout margins
        self.canvas = _RadarCanvas(self)
        self.setMinimumHeight(260)
        self.canvas.setMinimumSize(250, 260)
        self.canvas.setMinimumHeight(260)
        layout.addWidget(self.canvas, stretch=1)

        # Bias Warning Banner
        self.warning_banner = QLabel(self)
        self.warning_banner.setWordWrap(True)
        self.warning_banner.setStyleSheet(
            "QLabel { background-color: #0F172A; color: #94A3B8; font-size: 10px; "
            "border: 1px solid #1E293B; border-radius: 4px; padding: 4px 6px; }"
        )
        layout.addWidget(self.warning_banner)
        self._update_warning_banner()

    def _update_tooltips(self) -> None:
        exps = AXIS_EXPLANATIONS.get(self._lang, AXIS_EXPLANATIONS["en"])
        overview = f"• {exps['authority']}\n• {exps['linguistic']}\n• {exps['dispersion']}"
        self.setToolTip(overview)
        self.title_label.setToolTip(overview)
        if hasattr(self, "canvas"):
            self.canvas.setToolTip(overview)

    def get_axis_tooltip(self, axis_name: str) -> str:
        exps = AXIS_EXPLANATIONS.get(self._lang, AXIS_EXPLANATIONS["en"])
        key = "authority" if ("author" in axis_name.lower() or "1차" in axis_name) else ("linguistic" if ("ling" in axis_name.lower() or "global" in axis_name.lower() or "다국어" in axis_name) else "dispersion")
        return exps.get(key, "")

    def calculate_balance(
        self,
        documents: List[SourceDocument],
        audit: Optional[CitationAudit] = None,
    ) -> Dict[str, float]:
        """Calculate and return balance scores dictionary for testing and telemetry."""
        self.update_balance(documents, audit)
        return {
            "authority": self.authority_score,
            "linguistic": self.linguistic_score,
            "dispersion": self.dispersion_score,
        }

    def update_balance(
        self,
        documents: List[SourceDocument],
        audit: Optional[CitationAudit] = None,
    ) -> None:
        """Recalculate balance metrics based on indexed corpus and citation audit."""
        enabled_docs = [d for d in documents if getattr(d, "enabled", True)]
        if not enabled_docs:
            self.authority_score = 0.5
            self.linguistic_score = 0.5
            self.dispersion_score = 0.5
            self._update_warning_banner()
            self.canvas.update()
            return

        # 1. Authority Ratio: Academic / PDF / Direct Specs vs General Web
        primary_types = {"academic_arxiv", "academic_doi", "local_pdf", "local_docx"}
        primary_count = sum(1 for d in enabled_docs if d.source_type in primary_types or d.metadata.get("authority") == "primary")
        self.authority_score = max(0.1, min(1.0, primary_count / max(1, len(enabled_docs))))

        # 2. Regional / Linguistic Balance: Diversity of language tags
        origins = set()
        for d in enabled_docs:
            tag = d.metadata.get("origin_tag") or ""
            if tag:
                origins.add(tag)
        # 1 origin = 0.35, 2 = 0.65, 3+ = 0.95
        self.linguistic_score = min(1.0, 0.35 + 0.30 * max(0, len(origins) - 1))

        # 3. Perspective Dispersion: Variety of perspectives
        perspectives = set()
        for d in enabled_docs:
            p_name = d.metadata.get("perspective") or ""
            if p_name:
                perspectives.add(p_name)
        self.dispersion_score = min(1.0, 0.25 + 0.25 * len(perspectives))

        self._update_warning_banner()
        self.canvas.update()

    def _update_warning_banner(self) -> None:
        if self.authority_score < 0.25:
            msg = (
                "⚠ Epistemic Vulnerability: Over 75% of claims rely on tertiary commentary with low primary empirical grounding."
                if self._lang == "en"
                else "⚠ 근거 취약점: 주장의 75% 이상이 1차 실증 자료 없이 3차 해설에 의존하고 있습니다."
            )
            self.warning_banner.setStyleSheet(
                "QLabel { background-color: rgba(239, 68, 68, 0.15); color: #FCA5A5; font-size: 10px; "
                "border: 1px solid #EF4444; border-radius: 4px; padding: 4px 6px; font-weight: 500; }"
            )
        elif self.linguistic_score < 0.4:
            msg = (
                "⚠ Regional Bias: Single-language sourcing detected. Consider cross-lingual OmniSweep discovery."
                if self._lang == "en"
                else "⚠ 단일 언어 편향: 단일 언어 출처에 집중되어 있습니다. 다국어 교차 검증을 권장합니다."
            )
            self.warning_banner.setStyleSheet(
                "QLabel { background-color: rgba(234, 179, 8, 0.15); color: #FDE047; font-size: 10px; "
                "border: 1px solid #EAB308; border-radius: 4px; padding: 4px 6px; font-weight: 500; }"
            )
        else:
            msg = (
                "✔ Robust Epistemic Balance: High primary authority with multi-perspective distribution."
                if self._lang == "en"
                else "✔ 견고한 인식론적 균형: 높은 1차 문헌 신뢰도 및 다각화된 시각 확보."
            )
            self.warning_banner.setStyleSheet(
                "QLabel { background-color: rgba(34, 197, 94, 0.15); color: #86EFAC; font-size: 10px; "
                "border: 1px solid #22C55E; border-radius: 4px; padding: 4px 6px; font-weight: 500; }"
            )

        self.warning_banner.setText(msg)

    def retranslate_ui(self, lang: str = "en") -> None:
        self._lang = lang
        self.title_label.setText(get_text("epistemic_radar_title", lang))
        self._update_warning_banner()
        self._update_tooltips()
        self.canvas.update()


class _RadarCanvas(QWidget):
    """Sub-canvas rendering the radar polygon geometry."""

    def __init__(self, parent: EpistemicBalanceWidget) -> None:
        super().__init__(parent)
        self._parent_widget = parent
        self.setMouseTracking(True)
        self._top_rect = QRectF()
        self._bl_rect = QRectF()
        self._br_rect = QRectF()

    def get_axis_tooltip(self, axis_name: str) -> str:
        lang = self._parent_widget._lang
        exps = AXIS_EXPLANATIONS.get(lang, AXIS_EXPLANATIONS["en"])
        key = "authority" if ("author" in axis_name.lower() or "1차" in axis_name) else ("linguistic" if ("ling" in axis_name.lower() or "global" in axis_name.lower() or "다국어" in axis_name) else "dispersion")
        return exps.get(key, "")

    def mouseMoveEvent(self, event: Any) -> None:
        pos = event.position() if hasattr(event, "position") else event.pos()
        lang = self._parent_widget._lang
        exps = AXIS_EXPLANATIONS.get(lang, AXIS_EXPLANATIONS["en"])
        if hasattr(self, "_top_rect") and self._top_rect.contains(pos):
            self.setToolTip(exps["authority"])
        elif hasattr(self, "_bl_rect") and self._bl_rect.contains(pos):
            self.setToolTip(exps["linguistic"])
        elif hasattr(self, "_br_rect") and self._br_rect.contains(pos):
            self.setToolTip(exps["dispersion"])
        else:
            self.setToolTip(f"• {exps['authority']}\n• {exps['linguistic']}\n• {exps['dispersion']}")
        super().mouseMoveEvent(event)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        center_x = w / 2.0
        center_y = (h / 2.0) + 12.0
        radius = max(85.0, min((w / 2.0) - 110.0, (h / 2.0) - 55.0))

        # 3 Axes: Top (-90 deg), Bottom-Left (150 deg), Bottom-Right (30 deg)
        angles = [-math.pi / 2, 5 * math.pi / 6, math.pi / 6]

        # 1. Concentric Grid Polygons
        painter.setPen(QPen(QColor("#1E293B"), 1.2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for factor in (0.33, 0.66, 1.0):
            poly = QPolygonF()
            for a in angles:
                px = center_x + radius * factor * math.cos(a)
                py = center_y + radius * factor * math.sin(a)
                poly.append(QPointF(px, py))
            painter.drawPolygon(poly)

        # 2. Axis Spokes
        painter.setPen(QPen(QColor("#334155"), 1.0))
        for a in angles:
            px = center_x + radius * math.cos(a)
            py = center_y + radius * math.sin(a)
            painter.drawLine(QPointF(center_x, center_y), QPointF(px, py))

        # 3. Data Polygon
        scores = [
            self._parent_widget.authority_score,
            self._parent_widget.linguistic_score,
            self._parent_widget.dispersion_score,
        ]

        data_poly = QPolygonF()
        for a, score in zip(angles, scores):
            r_val = radius * max(0.12, min(1.0, score))
            px = center_x + r_val * math.cos(a)
            py = center_y + r_val * math.sin(a)
            data_poly.append(QPointF(px, py))

        # Draw filled shape
        painter.setBrush(QBrush(QColor(56, 189, 248, 60)))
        painter.setPen(QPen(QColor("#38BDF8"), 2.0))
        painter.drawPolygon(data_poly)

        # Draw vertices
        painter.setBrush(QBrush(QColor("#38BDF8")))
        for pt in data_poly:
            painter.drawEllipse(pt, 3.5, 3.5)

        # 4. Axis Labels
        lang = self._parent_widget._lang
        axis_names = [
            get_text('radar_axis_authority', lang),
            get_text('radar_axis_linguistic', lang),
            get_text('radar_axis_dispersion', lang),
        ]
        labels = [
            f"{name}\n{int(score * 100)}%"
            for name, score in zip(axis_names, scores)
        ]

        painter.setFont(QFont("-apple-system, sans-serif", 8, QFont.Weight.Bold))
        painter.setPen(QColor("#94A3B8"))

        # Top vertex: Center above point
        self._top_rect = QRectF(center_x - 80, center_y - radius - 44, 160, 40)
        painter.drawText(self._top_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, labels[0])

        # Bottom-Left vertex ("Global Diversity" / "다국어 다원성"): Anchor outside-left with right alignment
        self._bl_rect = QRectF(center_x - radius * 0.866 - 145, center_y + radius * 0.5 - 12, 135, 44)
        painter.drawText(self._bl_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, labels[1])

        # Bottom-Right vertex ("Perspective Spread" / "시각 분산도"): Anchor outside-right with left alignment
        self._br_rect = QRectF(center_x + radius * 0.866 + 10, center_y + radius * 0.5 - 12, 135, 44)
        painter.drawText(self._br_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, labels[2])
