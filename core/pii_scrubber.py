"""
PII & Secret Scrubber — Pre-processor for LLM payloads.

Detects and masks hardcoded API keys, secrets, passwords, email addresses,
and PII before any code snippet is sent to an external LLM provider.

Usage:
    from core.pii_scrubber import PIIScrubber

    scrubber = PIIScrubber()
    safe_code, report = scrubber.scrub(code_string)
    # use safe_code in LLM calls; check report for what was masked
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ─── Detection Patterns ───────────────────────────────────────────────────────

class Pattern(NamedTuple):
    name: str
    regex: str
    replacement: str


PATTERNS: list[Pattern] = [
    # Anthropic / Claude
    Pattern("anthropic_key",    r"sk-ant-[a-zA-Z0-9\-_]{20,}", "[REDACTED_ANTHROPIC_KEY]"),
    # OpenAI
    Pattern("openai_key",       r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_OPENAI_KEY]"),
    # Generic API key patterns
    Pattern("api_key_assign",   r'(?i)(api[_\-]?key|api[_\-]?token|access[_\-]?token)\s*[=:]\s*["\']([A-Za-z0-9\-_\.]{16,})["\']',
            r'\1 = "[REDACTED]"'),
    # AWS keys
    Pattern("aws_access",       r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
    Pattern("aws_secret",       r'(?i)(aws[_\-]?secret[_\-]?access[_\-]?key)\s*[=:]\s*["\']([A-Za-z0-9+/]{40})["\']',
            r'\1 = "[REDACTED_AWS_SECRET]"'),
    # GitHub tokens
    Pattern("github_token",     r"(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}", "[REDACTED_GITHUB_TOKEN]"),
    # Generic Bearer tokens
    Pattern("bearer_token",     r'(?i)bearer\s+[A-Za-z0-9\-_\.~+/]+=*', "Bearer [REDACTED_TOKEN]"),
    # Passwords in assignments
    Pattern("password_assign",  r'(?i)(password|passwd|pwd|secret)\s*[=:]\s*["\']([^"\']{4,})["\']',
            r'\1 = "[REDACTED_PASSWORD]"'),
    # Email addresses
    Pattern("email",            r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b',
            "[REDACTED_EMAIL]"),
    # IPv4 addresses (private/internal)
    Pattern("private_ip",       r'\b(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b',
            "[REDACTED_IP]"),
    # Database connection strings
    Pattern("db_conn",          r'(?i)(postgres|mysql|mongodb|redis)://[^\s"\'>]{6,}',
            "[REDACTED_DB_URL]"),
    # .env-style KEY=VERY_LONG_VALUE
    Pattern("env_secret",       r'(?m)^([A-Z][A-Z0-9_]{4,})\s*=\s*([A-Za-z0-9\-_\.~+/]{20,})$',
            r'\1=[REDACTED]'),
]

_COMPILED = [(p.name, re.compile(p.regex), p.replacement) for p in PATTERNS]


# ─── Scrub Result ─────────────────────────────────────────────────────────────

@dataclass
class ScrubReport:
    original_length: int
    scrubbed_length: int
    detections: list[dict] = field(default_factory=list)

    @property
    def triggered(self) -> bool:
        return len(self.detections) > 0

    @property
    def summary(self) -> str:
        if not self.triggered:
            return "No PII detected"
        types = ", ".join(sorted({d["type"] for d in self.detections}))
        return f"Masked {len(self.detections)} item(s): {types}"


# ─── Scrubber ─────────────────────────────────────────────────────────────────

class PIIScrubber:
    """
    Scans code/text for secrets and PII before sending to external LLMs.
    All matches are replaced with safe placeholder tokens.
    """

    def scrub(self, text: str) -> tuple[str, ScrubReport]:
        """
        Scan and mask PII/secrets in `text`.
        Returns (safe_text, report).
        """
        report = ScrubReport(original_length=len(text), scrubbed_length=0)
        result = text

        for name, pattern, replacement in _COMPILED:
            matches = list(pattern.finditer(result))
            for m in matches:
                report.detections.append({
                    "type": name,
                    "position": m.start(),
                    "length": len(m.group()),
                })
                logger.warning(f"[PIIScrubber] Masked '{name}' at position {m.start()}")
            result = pattern.sub(replacement, result)

        report.scrubbed_length = len(result)
        if report.triggered:
            logger.warning(f"[PIIScrubber] {report.summary}")
        return result, report

    def is_safe(self, text: str) -> bool:
        """Quick check — returns True if no PII is detected (no scrubbing needed)."""
        for _, pattern, _ in _COMPILED:
            if pattern.search(text):
                return False
        return True

    def scrub_dict(self, data: dict) -> tuple[dict, list[ScrubReport]]:
        """Scrub all string values in a dictionary (e.g. environment variables)."""
        reports = []
        cleaned = {}
        for k, v in data.items():
            if isinstance(v, str):
                safe, report = self.scrub(v)
                cleaned[k] = safe
                if report.triggered:
                    reports.append(report)
            else:
                cleaned[k] = v
        return cleaned, reports
