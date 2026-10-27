"""Shared Markdown normalization and HTML rendering (interactive [N] and [N:p.P] citation anchors, dark-mode CSS)."""

from __future__ import annotations

import inspect
import re
from typing import Callable, List, Optional

import markdown

GHOST_BULLET_LINES = {"•", "◦", "▪", "-", "*"}

# Matches group citations like [1, 2], [1:p.4, 2:p.5], or [1, 2:p.3]
_CITE_GROUP_RE = re.compile(r"\[(\d+(?::p\.\d+)?(?:\s*,\s*\d+(?::p\.\d+)?)+)\]")
# Matches single page citations like [1:p.4]
_CITE_PAGE_RE = re.compile(r"\[(\d+):p\.(\d+)\]")
# Matches timestamp citations like [1:02:45] or [1:01:23:45]
_CITE_TIME_RE = re.compile(r"\[(\d+):((?:\d{1,2}:)?\d{2}:\d{2})\]")
# Matches single document citations like [1]
_CITE_SINGLE_RE = re.compile(r"\[(\d+)\]")
_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")

CITATION_ANCHOR_STYLE = (
    "color: #58a6ff; font-weight: bold; text-decoration: none; "
    "background: rgba(56, 139, 253, 0.15); padding: 1px 5px; border-radius: 3px;"
)


def default_citation_anchor(
    doc_id: str,
    page: Optional[str] = None,
    context_claim: str = "",
) -> str:
    """Build the styled <a> anchor for cite:N or cite:N:P or cite:N:time:MM:SS."""
    if page:
        if str(page).startswith("time:"):
            t_val = page[5:]
            href = f"cite:{doc_id}:time:{t_val}"
            label = f"[{doc_id}:{t_val}]"
        else:
            href = f"cite:{doc_id}:{page}"
            label = f"[{doc_id}:p.{page}]"
    else:
        href = f"cite:{doc_id}"
        label = f"[{doc_id}]"
    return (
        f'<a href="{href}" class="citation-anchor cite-verified" '
        f'style="{CITATION_ANCHOR_STYLE}">{label}</a>'
    )


DARK_BODY_CSS = """
    body { color: #c9d1d9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Malgun Gothic', Roboto, sans-serif; font-size: 13px; line-height: 1.6; }
    h1 { color: #58a6ff; font-size: 18px; margin-top: 14px; margin-bottom: 8px; border-bottom: 1px solid #30363d; padding-bottom: 4px; }
    h2 { color: #79c0ff; font-size: 15px; margin-top: 12px; margin-bottom: 6px; }
    h3 { color: #a5d6ff; font-size: 14px; margin-top: 10px; margin-bottom: 4px; }
    p { margin: 6px 0; }
    ul, ol { margin: 6px 0; padding-left: 20px; }
    li { margin: 3px 0; }
    table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 12px; }
    th, td { border: 1px solid #30363d; padding: 6px 10px; text-align: left; }
    th { background-color: #161b22; color: #58a6ff; font-weight: bold; }
    tr:nth-child(even) { background-color: #0d1117; }
    code { background-color: #161b22; padding: 2px 4px; border-radius: 4px; font-family: Consolas, monospace; }
    pre { background-color: #161b22; padding: 10px; border-radius: 6px; overflow-x: auto; }
    blockquote { border-left: 3px solid #30363d; margin: 8px 0; padding-left: 10px; color: #8b949e; }
    a { color: #58a6ff; }
    a.cite-suspect { color: #d29922 !important; background: rgba(210, 153, 34, 0.15) !important; }
    a.cite-refuted { color: #f85149 !important; background: rgba(248, 81, 73, 0.2) !important; border: 1px solid rgba(248, 81, 73, 0.4); }
"""


def normalize_markdown(md_text: str) -> str:
    """Convert ghost-bullet lines to blank separators and guarantee a blank line before every Markdown table."""
    normalized_lines: List[str] = []
    for raw_line in md_text.splitlines():
        stripped = raw_line.strip()
        if stripped in GHOST_BULLET_LINES:
            if normalized_lines and normalized_lines[-1] != "":
                normalized_lines.append("")
            continue
        if stripped.startswith("|") and normalized_lines:
            prev = normalized_lines[-1].strip()
            if prev != "" and not prev.startswith("|"):
                normalized_lines.append("")
        normalized_lines.append(raw_line)
    return "\n".join(normalized_lines)


def _extract_preceding_claim(text: str) -> str:
    """Extract the last sentence preceding a citation anchor to serve as the factual claim context."""
    chunks = re.split(r"(?:[\.\?\!\n]+|\.\s+)", text)
    return chunks[-1].strip() if chunks else ""


def linkify_citations(
    html_text: str,
    anchor_builder: Optional[Callable[..., str]] = None,
) -> str:
    """Turn literal `[N]`, `[N:p.P]`, and `[N, M]` text into `cite:N` anchors, skipping tags, existing anchors, and code blocks."""
    if anchor_builder is not None:
        try:
            sig = inspect.signature(anchor_builder)
            params = len(sig.parameters)
            if params == 1:
                _orig = anchor_builder
                build = lambda doc_id, page=None, context="": _orig(f"{doc_id}:p.{page}" if page else doc_id)
            elif params == 2:
                _orig = anchor_builder
                build = lambda doc_id, page=None, context="": _orig(doc_id, page)
            else:
                build = anchor_builder
        except (ValueError, TypeError):
            build = anchor_builder
    else:
        build = default_citation_anchor

    parts = _TAG_SPLIT_RE.split(html_text)
    out: List[str] = []
    depth_skip = 0  # >0 while inside <a>, <code> or <pre>
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            lowered = part.lower()
            if re.match(r"<(a|code|pre)(\s|>)", lowered):
                depth_skip += 1
            elif re.match(r"</(a|code|pre)\s*>", lowered):
                depth_skip = max(0, depth_skip - 1)
            out.append(part)
            continue
        if depth_skip:
            out.append(part)
            continue

        def _group_sub(match: re.Match[str]) -> str:
            claim = _extract_preceding_claim(part[: match.start()])
            tokens = [tok.strip() for tok in match.group(1).split(",")]
            anchors: List[str] = []
            for tok in tokens:
                page_match = re.match(r"^(\d+):p\.(\d+)$", tok)
                if page_match:
                    anchors.append(build(page_match.group(1), page_match.group(2), claim))
                else:
                    anchors.append(build(tok, None, claim))
            return " ".join(anchors)

        converted = _CITE_GROUP_RE.sub(_group_sub, part)

        # Single markers: protect already-converted anchors by only touching text outside generated tags.
        sub_parts = _TAG_SPLIT_RE.split(converted)
        rebuilt: List[str] = []
        inner_skip = 0
        for sp in sub_parts:
            if sp.startswith("<") and sp.endswith(">"):
                low = sp.lower()
                if low.startswith("<a ") or low == "<a>":
                    inner_skip += 1
                elif low.startswith("</a"):
                    inner_skip = max(0, inner_skip - 1)
                rebuilt.append(sp)
            elif inner_skip:
                rebuilt.append(sp)
            else:
                def _page_sub(m: re.Match[str]) -> str:
                    claim = _extract_preceding_claim(sp[: m.start()])
                    return build(m.group(1), m.group(2), claim)

                def _time_sub(m: re.Match[str]) -> str:
                    claim = _extract_preceding_claim(sp[: m.start()])
                    return build(m.group(1), f"time:{m.group(2)}", claim)

                def _single_sub(m: re.Match[str]) -> str:
                    claim = _extract_preceding_claim(sp[: m.start()])
                    return build(m.group(1), None, claim)

                sp_page = _CITE_PAGE_RE.sub(_page_sub, sp)
                sp_time = _CITE_TIME_RE.sub(_time_sub, sp_page)
                sp_final = _CITE_SINGLE_RE.sub(_single_sub, sp_time)
                rebuilt.append(sp_final)
        out.append("".join(rebuilt))
    return "".join(out)


def markdown_to_html(
    md_text: str,
    interactive_citations: bool = True,
    anchor_builder: Optional[Callable[..., str]] = None,
) -> str:
    """Render Markdown into an HTML fragment (tables, fenced code, sane lists, nl2br) with optional cite anchors."""
    html = markdown.markdown(
        normalize_markdown(md_text),
        extensions=["tables", "fenced_code", "sane_lists", "nl2br"],
    )
    if interactive_citations:
        html = linkify_citations(html, anchor_builder=anchor_builder)
    return html


def build_dark_html(
    md_text: str,
    interactive_citations: bool = True,
    anchor_builder: Optional[Callable[..., str]] = None,
) -> str:
    """Return a complete dark-mode HTML document string for Qt rich-text widgets."""
    body = markdown_to_html(md_text, interactive_citations=interactive_citations, anchor_builder=anchor_builder)
    return f"<style>{DARK_BODY_CSS}</style><body>{body}</body>"
