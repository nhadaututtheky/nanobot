"""Dynamic credential scrubbing for tool outputs and session history."""

from __future__ import annotations

import re

# (label, compiled pattern) — order matters: longer patterns first to avoid partial matches.
_CREDENTIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # OpenAI / Anthropic / generic sk- keys
    ("API Key", re.compile(r"sk-[a-zA-Z0-9_\-]{20,}")),
    # AWS Access Key ID
    ("AWS Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    # AWS Secret Access Key (40-char base64)
    ("AWS Secret", re.compile(r"(?<=[\"' =:])[A-Za-z0-9/+=]{40}(?=[\"' \n,])")),
    # Bearer / Bot tokens in headers
    ("Bearer Token", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}")),
    # Telegram Bot Token (digits:alphanumeric)
    ("Bot Token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b")),
    # GitHub PAT / fine-grained tokens
    ("GitHub Token", re.compile(r"gh[ps]_[A-Za-z0-9_]{36,}")),
    ("GitHub Fine-grained", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    # Generic long hex secrets (32+ chars, e.g. webhook secrets)
    ("Hex Secret", re.compile(r"\b[0-9a-f]{32,64}\b", re.IGNORECASE)),
    # Basic auth in URLs  (user:pass@host)
    ("URL Credentials", re.compile(r"://[^@\s]+:[^@\s]+@")),
    # Private key blocks
    ("Private Key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


def scrub_credentials(text: str) -> str:
    """Replace detected credentials with [REDACTED:<type>] placeholders.

    Args:
        text: Raw text that may contain sensitive values.

    Returns:
        Sanitised copy with credentials replaced.
    """
    if not text:
        return text

    result = text
    for label, pattern in _CREDENTIAL_PATTERNS:
        if label == "URL Credentials":
            # Special handling: keep scheme and host, redact user:pass
            result = pattern.sub("://[REDACTED]@", result)
        elif label == "Private Key":
            result = pattern.sub(f"[REDACTED:{label}]", result)
        else:
            result = pattern.sub(f"[REDACTED:{label}]", result)
    return result
