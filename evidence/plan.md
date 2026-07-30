# Implementation Plan: Add `version()` API helper

**Task ref:** `ai/task-92214731-210f-4d61-ba51-d0c1d6f21986`

## Context

The `sandbox-app` (version `0.1.0`) already exposes two API-style helpers — `health()` and `ping()` — in `src/sandbox_app/core.py`. Both return simple `dict[str, str]` payloads and follow the same function signature / docstring pattern. The ask is to add a third helper, `version()`, that reports the app version as `{"version": "0.1.0"}`.

## Acceptance criteria

| AC | Criterion | How verified |
|----|-----------|--------------|
| AC-1 | `version()` returns `{"version": "0.1.0"}` | Unit test asserts exact dict equality |
| AC-2 | Tests cover `version()` return value | `pytest tests/` green on new `test_version` case |
| AC-3 | Matches style of `health()` / `ping()` | Manual review: same signature, same docstring tone, same return type |

## Files to change

### 1. `src/sandbox_app/core.py` (+4 lines)

**Action:** Add a `version()` function immediately after `ping()` (or after `health()`, before `ping()` — both are stylistically fine; after `ping()` keeps it at the end of the module).

```python
def version() -> dict[str, str]:
    """Return application version."""
    return {"version": "0.1.0"}
```

Rationale:
- Mirrors the exact shape of `health()` / `ping()`: no args, returns `dict[str, str]`, one-line docstring, one-line body.
- Version string `"0.1.0"` is pulled from `pyproject.toml` → `[project] version = "0.1.0"`. Hard-coding here is acceptable for a minimal helper; if the team later wants a single source of truth they can read from `importlib.metadata` in a follow-up.

### 2. `tests/test_core.py` (+5 lines)

**Action:**
1. Add `version` to the import line.
2. Add a `test_version` function following the same pattern as `test_health` / `test_ping`.

```python
from sandbox_app import health, ping, version


def test_health() -> None:
    assert health()["status"] == "ok"


def test_ping() -> None:
    assert ping()["pong"] == "true"


def test_version() -> None:
    assert version() == {"version": "0.1.0"}
```

Rationale:
- `test_version` asserts the **full dict** rather than a single key (since `version()` has only one key). This is the strongest, simplest assertion.
- `test_health` / `test_ping` are left untouched — the diff is as small as possible while still covering the new function.

### Verification steps

```bash
# Install dev deps (if not already)
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint check
ruff check src/ tests/
```

Expected output: 3 tests pass, zero lint errors, zero warnings.

## Risks / edge cases

- **None.** This is a pure additive change. No existing function or test is modified. No secrets, no config changes, no dependency updates.

## Diff summary

| File | Lines added | Lines removed |
|------|-------------|---------------|
| `src/sandbox_app/core.py` | 4 | 0 |
| `tests/test_core.py` | 3 | 1 (import line edit) |
| **Total** | **7** | **1** |
