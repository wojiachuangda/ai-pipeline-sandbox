# Implementation Plan: Add version() helper

## Overview
Add a `version()` helper function to `sandbox_app` that returns version metadata. This is a minimal change following the existing pattern established by `health()`.

## Steps

### 1. Implement version() function
**File:** `src/sandbox_app/__init__.py`
- Add `version()` function below the existing `health()` function
- Return type: `dict[str, str]`
- Return value: `{"version": "0.1.0"}`
- Follow same minimal pattern as `health()`

**Estimated lines:** +3 lines

### 2. Add test coverage
**File:** `tests/test_version.py` (new file)
- Import `version` from `sandbox_app`
- Add `test_version()` function
- Assert return value structure and version string
- Mirror the simple pattern in `test_health.py`

**Estimated lines:** ~5 lines

## Acceptance Criteria Mapping
- **AC-1**: Step 1 implements `version()` returning `{"version": "0.1.0"}`
- **AC-2**: Step 2 creates `tests/test_version.py` with coverage

## Risk Assessment
- **Risk:** None - pure function with no external dependencies
- **Breaking changes:** None - additive only

## Validation
Run test suite to verify:
```bash
pytest tests/test_version.py -v
```
