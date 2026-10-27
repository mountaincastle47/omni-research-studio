"""SQLite FTS5 full-text search indexing with sub-5ms BM25 ranking for corpus documents."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import List, Optional, Sequence

from core.document_loader import SourceDocument


@dataclass
class SearchResult:
    """Individual match from SQLite FTS5 index query."""

    doc_id: int
    doc_title: str
    page_num: int
    snippet: str
    bm25_score: float


def sanitize_fts_query(raw_query: str) -> str:
    """Sanitize user query for safe FTS5 MATCH evaluation."""
    cleaned = re.sub(r"[^\w\s\uac00-\ud7a3]", " ", raw_query).strip()
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return ""
    # Prefix-matching phrase OR disjunction
    return " OR ".join(f'"{t}"*' for t in tokens)


class CorpusSearchIndex:
    """Manages an SQLite FTS5 virtual table for lightning-fast BM25 keyword search across corpus documents."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._con = sqlite3.connect(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with self._con:
            self._con.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS corpus_fts USING fts5(
                    doc_id UNINDEXED,
                    doc_title,
                    page_num UNINDEXED,
                    content,
                    tokenize = 'unicode61'
                );
                """
            )

    def clear(self) -> None:
        """Clear all indexed records."""
        with self._con:
            self._con.execute("DELETE FROM corpus_fts;")

    def remove_document(self, doc_id: int) -> None:
        """Remove all indexed pages for a given doc_id."""
        with self._con:
            self._con.execute("DELETE FROM corpus_fts WHERE doc_id = ?;", (str(doc_id),))

    def index_document(self, doc_id: int, title: str, content: str, page_num: int = 1) -> None:
        """Index a single text page chunk."""
        with self._con:
            self._con.execute(
                "INSERT INTO corpus_fts(doc_id, doc_title, page_num, content) VALUES (?, ?, ?, ?);",
                (str(doc_id), title, str(page_num), content),
            )

    def index_source_document(self, doc: SourceDocument) -> None:
        """Index a SourceDocument, breaking into per-page records if page markers exist."""
        self.remove_document(doc.cite_id)
        content = doc.content

        # Check for <!--PAGE_START:X--> page markers
        pattern = re.compile(r"<!--PAGE_START:(\d+)-->")
        splits = list(pattern.finditer(content))

        if splits:
            for i, match in enumerate(splits):
                page_num = int(match.group(1))
                start_pos = match.end()
                end_pos = splits[i + 1].start() if i + 1 < len(splits) else len(content)
                page_text = content[start_pos:end_pos].strip()
                if page_text:
                    self.index_document(doc.cite_id, doc.title, page_text, page_num)
        else:
            self.index_document(doc.cite_id, doc.title, content.strip(), 1)

    def index_corpus(self, documents: Sequence[SourceDocument]) -> None:
        """Re-index the entire set of documents."""
        self.clear()
        for doc in documents:
            if doc.enabled:
                self.index_source_document(doc)

    def search_corpus(self, query: str, limit: int = 25) -> List[SearchResult]:
        """Execute BM25 search across indexed pages."""
        sanitized = sanitize_fts_query(query)
        if not sanitized:
            return []

        try:
            cur = self._con.execute(
                """
                SELECT
                    doc_id,
                    doc_title,
                    page_num,
                    snippet(corpus_fts, 3, '<mark>', '</mark>', '...', 25),
                    bm25(corpus_fts)
                FROM corpus_fts
                WHERE corpus_fts MATCH ?
                ORDER BY bm25(corpus_fts)
                LIMIT ?;
                """,
                (sanitized, limit),
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Fallback to plain quoted token if complex query fails
            safe_phrase = f'"{query.replace('"', '')}"*'
            try:
                cur = self._con.execute(
                    """
                    SELECT
                        doc_id,
                        doc_title,
                        page_num,
                        snippet(corpus_fts, 3, '<mark>', '</mark>', '...', 25),
                        bm25(corpus_fts)
                    FROM corpus_fts
                    WHERE corpus_fts MATCH ?
                    ORDER BY bm25(corpus_fts)
                    LIMIT ?;
                    """,
                    (safe_phrase, limit),
                )
                rows = cur.fetchall()
            except sqlite3.OperationalError:
                return []

        results: List[SearchResult] = []
        for r in rows:
            try:
                results.append(
                    SearchResult(
                        doc_id=int(r[0]),
                        doc_title=str(r[1]),
                        page_num=int(r[2]),
                        snippet=str(r[3]),
                        bm25_score=float(r[4]),
                    )
                )
            except (ValueError, TypeError):
                continue
        return results

    def close(self) -> None:
        """Close SQLite connection."""
        try:
            self._con.close()
        except Exception:
            pass
