"""Citation audit: cross-references bracketed [N] tags in a report against the active reference documents."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List

_BRACKET_GROUP_RE = re.compile(r"\[([0-9:p\.,\s]+)\]")


@dataclass
class CitationAudit:
    """Result of auditing citation markers. Counts are over DISTINCT cited source numbers."""

    total_citations: int = 0
    valid_citations: int = 0
    valid_ids: List[int] = field(default_factory=list)
    invalid_ids: List[int] = field(default_factory=list)

    @property
    def score(self) -> int:
        """Groundedness Score = (valid_citations / total_citations) * 100, rounded to a whole percent."""
        if self.total_citations <= 0:
            return 0
        return int(round(self.valid_citations / self.total_citations * 100))

    @property
    def has_citations(self) -> bool:
        return self.total_citations > 0


def extract_citation_ids(report_text: str) -> List[int]:
    """Return distinct citation numbers in first-appearance order, expanding `[1, 3]` groups and `[2:p.15]` page citations."""
    seen: List[int] = []
    for group in _BRACKET_GROUP_RE.findall(report_text or ""):
        for token in group.split(","):
            token = token.strip()
            cid_str = token.split(":p.")[0].strip() if ":p." in token else token
            if cid_str.isdigit():
                number = int(cid_str)
                if number not in seen:
                    seen.append(number)
    return seen


def audit_citations(report_text: str, documents: Iterable[object]) -> CitationAudit:
    """Audit `[N]` tags in `report_text` against enabled documents exposing `.cite_id` / `.enabled`."""
    active_ids = {int(getattr(d, "cite_id")) for d in documents if getattr(d, "enabled", True)}
    cited = extract_citation_ids(report_text)
    valid = [n for n in cited if n in active_ids]
    invalid = [n for n in cited if n not in active_ids]
    return CitationAudit(
        total_citations=len(cited),
        valid_citations=len(valid),
        valid_ids=valid,
        invalid_ids=invalid,
    )
