"""Redact before any request/response evidence reaches SQLite."""

import json
from typing import Any, Iterable

REDACTED = "[REDACTED]"
_SENSITIVE_PARTS = (
    "password",
    "passwd",
    "token",
    "authorization",
    "cookie",
    "secret",
    "api_key",
    "apikey",
    "access_key",
)


def _sensitive_key(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_PARTS)


def redact_structure(value: Any, secrets: Iterable[str] = ()) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _sensitive_key(key) else redact_structure(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_structure(item, secrets) for item in value]
    if isinstance(value, tuple):
        return [redact_structure(item, secrets) for item in value]
    if isinstance(value, str):
        return replace_secrets(value, secrets)
    return value


def replace_secrets(text: str, secrets: Iterable[str]) -> str:
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    return text


def evidence_summary(label: str, value: Any, secrets: Iterable[str] = ()) -> str:
    safe = redact_structure(value, secrets)
    try:
        rendered = json.dumps(safe, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        rendered = str(safe)
    rendered = replace_secrets(rendered, secrets)
    if len(rendered) > 4000:
        rendered = rendered[:3997] + "..."
    return f"{label}{rendered}"
