# Implementation Plan: Add version() helper to sandbox_app

## Context

The `sandbox_app` package currently exposes a single helper `health()` in `src/sandbox_app/__init__.py`. The task adds a new `version()` helper alongside it, with a corresponding test.

## Files to Change

### 1. `src/sandbox_app/__init__.py` — Add `version()` function

Append a new function `version()` returning `{"version": "0.1.0"}` below the existing `health()`.

```python
def health() -> dict[str, str]:
    return {"status": "ok"}


def version() -> dict[str, str]:
    return {"version": "0.1.0"}
```

- **Rationale**: Pure Python, no dependencies, no HTTP. Keeps the existing `health()` unchanged. Follows the same type annotation pattern (`dict[str, str]`).

### 2. `tests/test_version.py` — Add test for `version()`

Create a new test file mirroring the pattern in `tests/test_health.py`:

```python
from sandbox_app import version


def test_version():
    assert version()["version"] == "0.1.0"
```

- **Rationale**: Simple assertion matching the existing test style. Validates both the key (`"version"`) and the value (`"0.1.0"`) returned by the function.

## Acceptance Criteria Coverage

| AC | Description | How Covered |
|----|-------------|-------------|
| AC-1 | Add `version()` returning `{"version": "0.1.0"}` | Function added in `__init__.py` |
| AC-2 | Add `tests/test_version.py` covering `version()` | New test file with `test_version()` assertion |

## Verification

After implementing, run:

```bash
python -m pytest tests/test_version.py -v
```

## Diff Summary

- **2 files changed** (1 modified, 1 added)
- **Net +5 lines** (3 in `__init__.py`, 5 in `tests/test_version.py`)
- **No secrets, no HTTP, no dependency changes**
