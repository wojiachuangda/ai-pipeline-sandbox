"""Sensitive field masking utilities.

Provides `mask_value`, `mask_dict`, and `mask_sensitive` for redacting
sensitive fields (password, token, secret, api_key, authorization) in
plain dicts, nested dicts, and lists of dicts.
"""

from __future__ import annotations

from typing import Any

_DEFAULT_SENSITIVE_FIELDS: tuple[str, ...] = (
    "password",
    "token",
    "secret",
    "api_key",
    "authorization",
)


def mask_value(value: str, keep_chars: int = 4) -> str:
    """Mask a string value, keeping the first ``keep_chars`` characters visible.

    >>> mask_value("my-secret-token", 4)
    'my-s**********'
    >>> mask_value("abc", 4)
    'abc'
    >>> mask_value("abc", 2)
    'ab*'
    """
    if len(value) <= keep_chars:
        return value
    return value[:keep_chars] + "*" * (len(value) - keep_chars)


def mask_dict(
    data: dict[str, Any],
    sensitive_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Recursively mask sensitive fields in a dict.

    Returns a **new** dict — the original is never mutated.
    Sensitive keys are matched case-insensitively.

    ``sensitive_fields`` defaults to
    ``["password", "token", "secret", "api_key", "authorization"]``.
    """
    fields = (
        [f.lower() for f in sensitive_fields]
        if sensitive_fields
        else list(_DEFAULT_SENSITIVE_FIELDS)
    )

    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            result: dict[str, Any] = {}
            for k, v in obj.items():
                if k.lower() in fields and isinstance(v, str):
                    result[k] = mask_value(v)
                elif k.lower() in fields:
                    # Sensitive field but not a string — keep as-is (edge-case).
                    result[k] = v
                else:
                    result[k] = _walk(v)
            return result
        if isinstance(obj, list):
            return [_walk(item) for item in obj]
        return obj

    return _walk(data)


def mask_sensitive(data: dict[str, Any]) -> dict[str, Any]:
    """Convenience wrapper around ``mask_dict`` using the default field list."""
    return mask_dict(data)
