"""Centralized redaction for HTTP logs and externally returned error text."""
from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----", re.I),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.I),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(https?://)[^/\s:@]+:[^/\s@]+@", re.I),
    re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|cookie|client[_-]?secret)\b(\s*[:=]\s*)([^,\s;\"']+)"),
    re.compile(r"(?i)([?&](?:token|access_token|api_key|key|password|secret|signature|sig|code|authorization)=)[^&#\s]+"),
]


def redact_text(value: str) -> str:
    text = str(value)
    for pattern in _PATTERNS:
        if pattern.pattern.startswith("(?i)([?&]"):
            text = pattern.sub(lambda m: m.group(1) + REDACTED, text)
        elif "password|passwd|secret|api" in pattern.pattern:
            text = pattern.sub(lambda m: m.group(1) + m.group(2) + REDACTED, text)
        elif pattern.pattern.startswith(r"\b(https?"):
            text = pattern.sub(lambda m: m.group(1) + REDACTED + "@" , text)
        else:
            text = pattern.sub(REDACTED, text)
    return text


def redact_value(value: Any) -> Any:
    """Redact string leaves recursively without persisting arbitrary raw values."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    return value
