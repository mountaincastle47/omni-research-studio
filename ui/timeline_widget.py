"""Interactive Temporal Milestone & Chronology Track View with Searchable Date Filters."""

from __future__ import annotations

import re
from typing import List, Optional

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.i18n import get_text
from core.timeline_parser import ChronologyMilestone, parse_chronology_table


class MilestoneCard(QFrame):
    """Visual milestone card on the vertical chronology track."""

    citation_clicked = pyqtSignal(QUrl)

    def __init__(self, milestone: ChronologyMilestone, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.milestone = milestone
        self._lang = lang
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            "MilestoneCard { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 10px; margin-bottom: 6px; } "
            "MilestoneCard:hover { border: 1px solid #38BDF8; background-color: #162032; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Header row: Date badge + Event
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        date_badge = QLabel(self.milestone.date_or_period)
        date_badge.setStyleSheet(
            "background-color: #0369A1; color: #FFFFFF; font-weight: 700; "
            "font-size: 11px; padding: 2px 8px; border-radius: 4px;"
        )
        hdr.addWidget(date_badge)

        event_lbl = QLabel(self.milestone.event)
        event_lbl.setStyleSheet("color: #F8FAFC; font-weight: 700; font-size: 13px;")
        event_lbl.setWordWrap(True)
        hdr.addWidget(event_lbl, stretch=1)

        layout.addLayout(hdr)

        # Outcome row
        if self.milestone.outcome:
            outcome_lbl = QLabel(self.milestone.outcome)
            outcome_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.4;")
            outcome_lbl.setWordWrap(True)
            layout.addWidget(outcome_lbl)

        # Citation row
        if self.milestone.citation:
            cite_lbl = QLabel()
            cite_lbl.setOpenExternalLinks(False)
            cite_lbl.linkActivated.connect(self._on_link_activated)

            # Linkify citations
            c_text = self.milestone.citation
            styled_c = re.sub(
                r"\[([0-9:p\.,\s_]+)\]",
                r'<a href="cite:\1" style="color: #38BDF8; font-weight: bold; text-decoration: none; background: rgba(56, 189, 248, 0.15); padding: 1px 5px; border-radius: 3px;">[\1]</a>',
                c_text,
            )
            cite_lbl.setText(styled_c)
            layout.addWidget(cite_lbl)

    def _on_link_activated(self, link_str: str) -> None:
        self.citation_clicked.emit(QUrl(link_str))


class ChronologyTimelineWidget(QWidget):
    """Vertical interactive event track displaying temporal milestones parsed from synthesis reports."""

    citation_clicked = pyqtSignal(QUrl)

    def __init__(self, lang: str = "en", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._all_milestones: List[ChronologyMilestone] = []
        self._cards: List[MilestoneCard] = []
        self._build_ui()

    @property
    def milestones(self) -> List[ChronologyMilestone]:
        return self._all_milestones

    @property
    def cards(self) -> List[MilestoneCard]:
        return self._cards

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Filter bar
        top_bar = QHBoxLayout()
        self.title_label = QLabel(get_text("tab_chronology", self._lang))
        self.title_label.setStyleSheet("color: #38BDF8; font-size: 13px; font-weight: 700;")
        top_bar.addWidget(self.title_label)

        self.count_badge = QLabel("0 milestones", self)
        self.count_badge.setStyleSheet("color: #94A3B8; font-size: 11px; padding: 2px 6px; background: #1E293B; border-radius: 4px;")
        top_bar.addWidget(self.count_badge)

        top_bar.addStretch(1)

        self.filter_input = QLineEdit(self)
        self.filter_input.setPlaceholderText(get_text("chronology_filter_placeholder", self._lang))
        self.filter_input.setStyleSheet(
            "QLineEdit { background-color: #0F172A; color: #F1F5F9; border: 1px solid #334155; "
            "border-radius: 4px; padding: 4px 8px; font-size: 11px; min-width: 180px; }"
        )
        self.filter_input.textChanged.connect(self._on_filter_changed)
        top_bar.addWidget(self.filter_input)

        layout.addLayout(top_bar)

        # Scroll Area for timeline
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        self.timeline_container = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_container)
        self.timeline_layout.setContentsMargins(4, 4, 4, 4)
        self.timeline_layout.setSpacing(8)
        self.timeline_layout.addStretch(1)

        self.scroll.setWidget(self.timeline_container)
        layout.addWidget(self.scroll, stretch=1)

    def set_markdown_report(self, markdown_text: str) -> None:
        """Parse chronology table and populate milestone cards."""
        self._all_milestones = parse_chronology_table(markdown_text)
        self._render_milestones(self._all_milestones)

    def _render_milestones(self, milestones: List[ChronologyMilestone]) -> None:
        self.count_badge.setText(f"{len(milestones)} milestones" if self._lang == "en" else f"{len(milestones)}개 마일스톤")
        # Clear existing
        for c in self._cards:
            self.timeline_layout.removeWidget(c)
            c.deleteLater()
        self._cards.clear()

        # Remove trailing stretch
        while self.timeline_layout.count() > 0:
            item = self.timeline_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not milestones:
            empty_lbl = QLabel(
                "No chronological sequence table found in synthesis report." if self._lang == "en" else "보고서에서 사건 연대표를 찾을 수 없습니다."
            )
            empty_lbl.setStyleSheet("color: #64748B; font-size: 12px; margin: 20px; text-align: center;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.timeline_layout.addWidget(empty_lbl)
            self.timeline_layout.addStretch(1)
            return

        for m in milestones:
            card = MilestoneCard(m, lang=self._lang, parent=self)
            card.citation_clicked.connect(self.citation_clicked)
            self.timeline_layout.addWidget(card)
            self._cards.append(card)

        self.timeline_layout.addStretch(1)

    def _on_filter_changed(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            for card in self._cards:
                card.show()
            return

        for card in self._cards:
            m = card.milestone
            searchable = f"{m.date_or_period} {m.event} {m.outcome} {m.citation}".lower()
            card.setVisible(query in searchable)

    def retranslate_ui(self, lang: str) -> None:
        self._lang = lang
        self.title_label.setText(get_text("tab_chronology", lang))
        self.filter_input.setPlaceholderText(get_text("chronology_filter_placeholder", lang))
        for card in self._cards:
            card._lang = lang
