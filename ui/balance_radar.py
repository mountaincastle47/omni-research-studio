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
        self.canvas.setMinimumSize(250, 200)
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
        self.canvas.update()


class _RadarCanvas(QWidget):
    """Sub-canvas rendering the radar polygon geometry."""

    def __init__(self, parent: EpistemicBalanceWidget) -> None:
        super().__init__(parent)
        self._parent_widget = parent

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0 + 4.0

        # Maintain at least 20px buffer from outer borders for text rendering
        radius = min(w * 0.28, h * 0.32)
        radius = max(35.0, min(75.0, radius))

        # 3 Axes at 90 deg (top), 210 deg (bottom-left), 330 deg (bottom-right)
        angles = [-math.pi / 2, -math.pi / 2 + (2 * math.pi / 3), -math.pi / 2 + (4 * math.pi / 3)]

        # 1. Concentric Grid Polygons
        painter.setPen(QPen(QColor("#1E293B"), 1.2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for factor in (0.33, 0.66, 1.0):
            poly = QPolygonF()
            for a in angles:
                px = cx + radius * factor * math.cos(a)
                py = cy + radius * factor * math.sin(a)
                poly.append(QPointF(px, py))
            painter.drawPolygon(poly)

        # 2. Axis Spokes
        painter.setPen(QPen(QColor("#334155"), 1.0))
        for a in angles:
            px = cx + radius * math.cos(a)
            py = cy + radius * math.sin(a)
            painter.drawLine(QPointF(cx, cy), QPointF(px, py))

        # 3. Data Polygon
        scores = [
            self._parent_widget.authority_score,
            self._parent_widget.linguistic_score,
            self._parent_widget.dispersion_score,
        ]

        data_poly = QPolygonF()
        for a, score in zip(angles, scores):
            r_val = radius * max(0.12, min(1.0, score))
            px = cx + r_val * math.cos(a)
            py = cy + r_val * math.sin(a)
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
        # Format label text into two lines (metric name on line 1, percentage on line 2): f"{name}\n{int(score * 100)}%"
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

        # Outer spoke vertex coordinates
        x0 = cx + radius * math.cos(angles[0])
        y0 = cy + radius * math.sin(angles[0])

        x1 = cx + radius * math.cos(angles[1])
        y1 = cy + radius * math.sin(angles[1])

        x2 = cx + radius * math.cos(angles[2])
        y2 = cy + radius * math.sin(angles[2])

        # Top Vertex ("Authority Ratio" / "1차 문헌 비율"):
        # Anchor above the point using Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
        top_rect = QRectF(x0 - 90, y0 - 36, 180, 32)
        painter.drawText(top_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, labels[0])

        # Bottom-Left Vertex ("Global Diversity" / "다국어 다원성"):
        # Anchor strictly to the left of the vertex using Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop with an 8px offset (x - 8, y + 4)
        bl_rect = QRectF(x1 - 8 - 140, y1 + 4, 140, 36)
        painter.drawText(bl_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, labels[1])

        # Bottom-Right Vertex ("Perspective Spread" / "시각 분산도"):
        # Anchor strictly to the right of the vertex using Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop with an 8px offset (x + 8, y + 4)
        br_rect = QRectF(x2 + 8, y2 + 4, 140, 36)
        painter.drawText(br_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, labels[2])
