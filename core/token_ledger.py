"""True API usage ledger and session billing telemetry storing audit records in SQLite."""

from __future__ import annotations

import datetime
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from core.database import close_thread_connection, get_db_connection
from core.paths import get_app_root, get_cache_dir

PROJECT_ROOT = get_app_root()
DEFAULT_LEDGER_DB = get_cache_dir() / "token_ledger.sqlite"


@dataclass
class TokenUsageRecord:
    """Record of tokens consumed and billing cost incurred for an API operation."""

    timestamp: str
    session_id: str
    model: str
    prompt_tokens: int
    candidate_tokens: int
    cached_tokens: int
    cost_usd: float


@dataclass
class TokenTotals:
    """Aggregated tokens and dollar cost across a session."""

    prompt_tokens: int = 0
    candidate_tokens: int = 0
    cached_tokens: int = 0
    total_cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.candidate_tokens


class TokenLedger:
    """Audit store and billing calculator for all Gemini API invocations."""

    _instance: Optional[TokenLedger] = None

    def __init__(self, db_path: Path | str = DEFAULT_LEDGER_DB) -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._in_memory_con: Optional[sqlite3.Connection] = None
        else:
            self._in_memory_con = sqlite3.connect(":memory:", check_same_thread=False, timeout=30.0)
        self._init_db()

    @property
    def _con(self) -> sqlite3.Connection:
        """Return a thread-local SQLite connection scoped to the executing thread."""
        if self._in_memory_con is not None:
            return self._in_memory_con
        return get_db_connection(self.db_path)

    @classmethod
    def get_instance(cls) -> TokenLedger:
        if cls._instance is None:
            cls._instance = TokenLedger()
        return cls._instance

    def _init_db(self) -> None:
        with self._con:
            self._con.execute(
                """
                CREATE TABLE IF NOT EXISTS session_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    session_id TEXT,
                    model TEXT,
                    prompt_tokens INTEGER,
                    candidate_tokens INTEGER,
                    cached_tokens INTEGER,
                    cost_usd REAL
                );
                """
            )

    @staticmethod
    def calculate_cost(
        model: str,
        prompt_tokens: int,
        candidate_tokens: int,
        cached_tokens: int = 0,
    ) -> float:
        """
        Calculate exact cost in USD with 75% cached input discount.
        Pricing per 1M tokens:
        - gemini-4-argon / pro: $2.50 prompt, $0.625 cached, $10.00 output
        - gemini-3.8-flash / default: $0.15 prompt, $0.0375 cached, $0.60 output
        """
        model_lower = (model or "").lower()
        is_argon = "argon" in model_lower or "pro" in model_lower

        if is_argon:
            rate_prompt = 2.50 / 1_000_000
            rate_cached = 0.625 / 1_000_000
            rate_candidate = 10.00 / 1_000_000
        else:
            rate_prompt = 0.15 / 1_000_000
            rate_cached = 0.0375 / 1_000_000
            rate_candidate = 0.60 / 1_000_000

        actual_cached = min(cached_tokens, prompt_tokens)
        non_cached_prompt = max(0, prompt_tokens - actual_cached)

        cost = (
            (non_cached_prompt * rate_prompt)
            + (actual_cached * rate_cached)
            + (candidate_tokens * rate_candidate)
        )
        return round(cost, 6)

    def record_manual(
        self,
        model: str,
        prompt_tokens: int,
        candidate_tokens: int,
        cached_tokens: int = 0,
        session_id: str = "default",
    ) -> TokenUsageRecord:
        """Record an explicit token usage entry."""
        cost_usd = self.calculate_cost(model, prompt_tokens, candidate_tokens, cached_tokens)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._con:
            self._con.execute(
                """
                INSERT INTO session_tokens (timestamp, session_id, model, prompt_tokens, candidate_tokens, cached_tokens, cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (stamp, session_id, model, prompt_tokens, candidate_tokens, cached_tokens, cost_usd),
            )
        return TokenUsageRecord(
            timestamp=stamp,
            session_id=session_id,
            model=model,
            prompt_tokens=prompt_tokens,
            candidate_tokens=candidate_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost_usd,
        )

    def record_usage(
        self,
        model: str,
        usage_metadata: Any,
        session_id: str = "default",
    ) -> TokenUsageRecord:
        """Extract tokens from google.genai response.usage_metadata and record transaction."""
        prompt_tokens = 0
        candidate_tokens = 0
        cached_tokens = 0

        if usage_metadata is not None:
            prompt_tokens = int(getattr(usage_metadata, "prompt_token_count", 0) or 0)
            candidate_tokens = int(getattr(usage_metadata, "candidates_token_count", 0) or 0)
            cached_tokens = int(getattr(usage_metadata, "cached_content_token_count", 0) or 0)

            # Fallback dict lookup if object is a dict
            if isinstance(usage_metadata, dict):
                prompt_tokens = int(usage_metadata.get("prompt_token_count", 0) or 0)
                candidate_tokens = int(usage_metadata.get("candidates_token_count", 0) or 0)
                cached_tokens = int(usage_metadata.get("cached_content_token_count", 0) or 0)

        return self.record_manual(
            model=model,
            prompt_tokens=prompt_tokens,
            candidate_tokens=candidate_tokens,
            cached_tokens=cached_tokens,
            session_id=session_id,
        )

    def get_session_totals(self, session_id: Optional[str] = None) -> TokenTotals:
        """Calculate cumulative token totals and total spend in USD."""
        query = (
            "SELECT SUM(prompt_tokens), SUM(candidate_tokens), SUM(cached_tokens), SUM(cost_usd) FROM session_tokens"
        )
        params: tuple = ()
        if session_id:
            query += " WHERE session_id = ?"
            params = (session_id,)

        cur = self._con.execute(query, params)
        row = cur.fetchone()
        if not row or row[0] is None:
            return TokenTotals()

        return TokenTotals(
            prompt_tokens=int(row[0] or 0),
            candidate_tokens=int(row[1] or 0),
            cached_tokens=int(row[2] or 0),
            total_cost_usd=round(float(row[3] or 0.0), 4),
        )

    def get_all_records(self, session_id: Optional[str] = None) -> List[TokenUsageRecord]:
        """Fetch all usage records in chronological order."""
        query = (
            "SELECT timestamp, session_id, model, prompt_tokens, candidate_tokens, cached_tokens, cost_usd "
            "FROM session_tokens"
        )
        params: tuple = ()
        if session_id:
            query += " WHERE session_id = ?"
            params = (session_id,)
        query += " ORDER BY id ASC"

        cur = self._con.execute(query, params)
        records: List[TokenUsageRecord] = []
        for r in cur.fetchall():
            records.append(
                TokenUsageRecord(
                    timestamp=str(r[0]),
                    session_id=str(r[1]),
                    model=str(r[2]),
                    prompt_tokens=int(r[3]),
                    candidate_tokens=int(r[4]),
                    cached_tokens=int(r[5]),
                    cost_usd=float(r[6]),
                )
            )
        return records

    def clear(self, session_id: Optional[str] = None) -> None:
        """Clear usage records."""
        with self._con:
            if session_id:
                self._con.execute("DELETE FROM session_tokens WHERE session_id = ?", (session_id,))
            else:
                self._con.execute("DELETE FROM session_tokens")

    def close(self) -> None:
        if self._in_memory_con is not None:
            try:
                self._in_memory_con.close()
            except Exception:
                pass
        else:
            close_thread_connection(self.db_path)


GLOBAL_LEDGER = TokenLedger()
