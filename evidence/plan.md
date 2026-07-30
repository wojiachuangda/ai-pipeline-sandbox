# Implementation Plan: Add version() Helper

## Overview
Add a pure Python `version()` helper function to `src/sandbox_app/__init__.py` that returns version information, with corresponding test coverage.

## Current State
- `src/sandbox_app/__init__.py` contains a single `health()` function returning `{"status": "ok"}`
- `tests/test_health.py` contains tests for the `health()` function
- Minimal Python package structure with pyproject.toml

## Implementation Steps

### Step 1: Add version() Function (AC-1)
**File:** `src/sandbox_app/__init__.py`

**Changes:**
- Add `version()` function that returns `{"version": "0.1.0"}`
- Function signature: `def version() -> dict[str, str]:`
- Keep existing `health()` helper unchanged

**Expected diff:**
```python
def health() -> dict[str, str]:
    return {"status": "ok"}

def version() -> dict[str, str]:
    return {"version": "0.1.0"}
```

### Step 2: Add Test Coverage (AC-2)
**File:** `tests/test_version.py` (new file)

**Changes:**
- Create new test file following the pattern of `test_health.py`
- Import `version` from `sandbox_app`
- Add `test_version()` function that asserts the return value

**Expected content:**
```python
from sandbox_app import version

def test_version():
    assert version()["version"] == "0.1.0"
```

### Step 3: Verification
- Run tests to ensure both test files pass
- Verify minimal diff approach (only 2 files modified/created)
- Confirm no secrets or sensitive data introduced

## Acceptance Criteria Mapping
- ✅ **AC-1:** `version()` function in `src/sandbox_app/__init__.py` returns `{"version": "0.1.0"}`
- ✅ **AC-2:** `tests/test_version.py` tests the `version()` function

## Files Modified
1. `src/sandbox_app/__init__.py` - Add `version()` function
2. `tests/test_version.py` - New file with test coverage

## Testing Strategy
- Unit test validates exact return value structure and content
- Follows existing test pattern from `test_health.py`
- No external dependencies or test infrastructure changes required
