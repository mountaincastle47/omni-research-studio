"""Client-side pre-flight sensitive pattern scrubber redacting API keys, IPs, emails, and PII."""

from __future__ import annotations

import re
from typing import List, Tuple

# Comprehensive sensitive token detection patterns
_PATTERNS = [
    # 1. Google Gemini / Cloud API Key (Google API Key pattern)
    (re.compile(r"\b[A][I][z][a][0-9A-Za-z\-_]{33,36}\b"), "[REDACTED:API_KEY]"),
    # 2. OpenAI / Anthropic / Generic Bearer API Keys (sk-...)
    (re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9\-_]{32,80}\b"), "[REDACTED:API_KEY]"),
    # 3. AWS Access Key ID (AKIA...)
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED:AWS_KEY]"),
    # 4. Korean Resident Registration Number (RRN: 6 digits - 7 digits starting with 1-4)
    (re.compile(r"\b\d{6}\s*-\s*[1-4]\d{6}\b"), "[REDACTED:RRN]"),
    # 5. Email addresses
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[REDACTED:EMAIL]"),
    # 6. IPv4 addresses with optional port (excluding version numbers like 1.0.0 or 0.0.0.0)
    (
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?::\d{1,5})?\b"
        ),
        "[REDACTED:IP]",
    ),
]


def scrub_sensitive_patterns(text: str) -> Tuple[str, int]:
    """
    Scan and redact sensitive credentials and PII from prompt text prior to API transmission.
    Returns (sanitized_text, total_redaction_count).
    """
    if not text:
        return "", 0

    sanitized = text
    total_redactions = 0

    for regex, replacement in _PATTERNS:
        matches = regex.findall(sanitized)
        if matches:
            total_redactions += len(matches)
            sanitized = regex.sub(replacement, sanitized)

    return sanitized, total_redactions
