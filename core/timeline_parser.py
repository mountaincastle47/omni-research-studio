"""Temporal Milestone & Chronology Parser: Markdown table extraction into structured milestone tracks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ChronologyMilestone:
    """Represents a discrete chronological event or development milestone."""

    date_or_period: str
    event: str
    outcome: str
    citation: str = ""

    @property
    def date_str(self) -> str:
        return self.date_or_period

    @property
    def event_title(self) -> str:
        return self.event

    @property
    def outcome_desc(self) -> str:
        return self.outcome

    @property
    def citations(self) -> List[str]:
        if not self.citation:
            return []
        found = re.findall(r"\[\d+(?::p\.\d+)?\]", self.citation)
        return found if found else [self.citation]


def parse_chronology_table(markdown_text: str) -> List[ChronologyMilestone]:
    """
    Extract chronological milestones from Markdown table titled
    'Temporal Sequence & Chronology' or containing Date / Milestone columns.
    """
    milestones: List[ChronologyMilestone] = []
    lines = markdown_text.strip().splitlines()

    in_chronology_section = False
    in_table = False
    header_col_indices = {"date": -1, "event": -1, "outcome": -1, "citation": -1}

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            if in_table:
                # Table ended
                in_table = False
            continue

        if line.startswith("#"):
            lower_h = line.lower()
            if any(k in lower_h for k in ("chronology", "temporal", "연대", "이력", "milestone")):
                in_chronology_section = True
            else:
                in_chronology_section = False

        if line.startswith("|") and ("---" not in line):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if not in_table:
                # Potential header line
                lower_cols = [c.lower() for c in cols]
                date_idx = next((i for i, c in enumerate(lower_cols) if any(k in c for k in ("date", "period", "일시", "시기", "연도"))), -1)
                event_idx = next((i for i, c in enumerate(lower_cols) if any(k in c for k in ("milestone", "event", "사건", "개발"))), -1)
                outcome_idx = next((i for i, c in enumerate(lower_cols) if any(k in c for k in ("outcome", "result", "결과", "영향", "내용"))), -1)
                cite_idx = next((i for i, c in enumerate(lower_cols) if any(k in c for k in ("citation", "source", "출처", "근거"))), -1)

                if date_idx != -1 and event_idx != -1:
                    in_table = True
                    header_col_indices = {
                        "date": date_idx,
                        "event": event_idx,
                        "outcome": outcome_idx,
                        "citation": cite_idx,
                    }
                    continue
            else:
                # Data row
                d_idx = header_col_indices["date"]
                e_idx = header_col_indices["event"]
                o_idx = header_col_indices["outcome"]
                c_idx = header_col_indices["citation"]

                d_val = cols[d_idx] if 0 <= d_idx < len(cols) else ""
                e_val = cols[e_idx] if 0 <= e_idx < len(cols) else ""
                o_val = cols[o_idx] if 0 <= o_idx < len(cols) else ""
                c_val = cols[c_idx] if 0 <= c_idx < len(cols) else ""

                if d_val or e_val:
                    milestones.append(
                        ChronologyMilestone(
                            date_or_period=d_val,
                            event=e_val,
                            outcome=o_val,
                            citation=c_val,
                        )
                    )

    # Fallback: if no dedicated table with those exact headers found, scan for any table under chronology section
    if not milestones:
        for line in lines:
            if line.startswith("|") and ("---" not in line):
                cols = [c.strip() for c in line.split("|")[1:-1]]
                if len(cols) >= 3 and any(char.isdigit() for char in cols[0]):
                    milestones.append(
                        ChronologyMilestone(
                            date_or_period=cols[0],
                            event=cols[1],
                            outcome=cols[2],
                            citation=cols[3] if len(cols) > 3 else "",
                        )
                    )

    return milestones
