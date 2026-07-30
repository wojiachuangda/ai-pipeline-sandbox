# Implementation Plan: T-015 提示词模板、版本与 A/B 实验

## Overview

Implement prompt-template CRUD with `{{var}}` interpolation, template versioning with rollback, and A/B experiment management — all as new modules in the existing `sandbox_app` package with matching test coverage.

## Architecture

```
src/sandbox_app/
├── __init__.py              # + export new modules
├── core.py                  # (unchanged)
├── templates.py             # NEW: template model, CRUD, render, token estimation
├── template_versions.py     # NEW: version store, list, rollback
└── ab_experiments.py        # NEW: experiment model, validation, lifecycle
tests/
├── test_core.py             # (unchanged)
├── test_templates.py        # NEW: AC-1 CRUD, AC-2 render + validation
└── test_ab_experiments.py   # NEW: AC-4 experiment validation + lifecycle
```

## Step-by-step

### Step 1 — AC-1: Prompt template CRUD with variable safety

**File:** `src/sandbox_app/templates.py`

- `PromptTemplate` dataclass: `id`, `name`, `body` (text with `{{var_name}}` markers), `required_vars: list[str]`, `created_at`, `updated_at`
- `TemplateStore` class (in-memory dict): `create()`, `get()`, `update()`, `delete()`, `list()`
- `extract_variables(body: str) -> set[str]` — regex `\{\{(\w+)\}\}` to discover variables
- `validate_no_executable(body: str) -> list[str]` — reject `{%`, `{{%`, `{% raw %}`, `__` dunder patterns, `exec(`, `eval(`; return error messages
- `create` enforces: body must pass `validate_no_executable`, otherwise `ValueError`

### Step 2 — AC-2: Render + token estimation

**File:** `src/sandbox_app/templates.py` (same module)

- `render(template: PromptTemplate, variables: dict[str, str]) -> str`
  - Interpolate `{{var}}` → value
  - If a var in `required_vars` is missing → raise `MissingTemplateVariableError(var_name)` (custom exception with code `MISSING_TEMPLATE_VARIABLE`)
- `estimate_tokens(body: str) -> int` — rough token count: `len(body.split())`; note the estimation approach in a docstring

### Step 3 — AC-3: Template version list/rollback

**File:** `src/sandbox_app/template_versions.py`

- `TemplateVersion` dataclass: `template_id`, `version (int)`, `body`, `required_vars`, `created_at`
- `VersionedTemplateStore`:
  - `save_version(template: PromptTemplate) -> TemplateVersion` — snapshot before each `update`
  - `list_versions(template_id: str) -> list[TemplateVersion]`
  - `rollback(template_id: str, version: int) -> PromptTemplate` — restore body + required_vars from a version snapshot
- Version numbers auto-increment per template

### Step 4 — AC-4: A/B experiment management

**File:** `src/sandbox_app/ab_experiments.py`

- `Variant`: `template_id`, `weight (int)`, `config (dict)`
- `Experiment` dataclass: `id`, `name`, `variants: list[Variant]`, `metrics: list[str]`, `status: ExperimentStatus`
- `ExperimentStatus` enum: `SCHEDULED`, `RUNNING`, `COMPLETED`, `CANCELLED`
- `VALID_METRICS` set — e.g. `{"response_time", "token_usage", "user_rating", "conversion_rate"}`
- `ExperimentStore`:
  - `create(...)` — validates: `sum(v.weight for v in variants) == 100`, every `m in metrics` must be in `VALID_METRICS`; rejects with `ValueError` otherwise
  - `get()`, `list()`, `update_status(id, status)`
  - Status transitions: `SCHEDULED → RUNNING → COMPLETED | CANCELLED`; `CANCELLED` and `COMPLETED` are terminal

### Step 5 — Package exports

**File:** `src/sandbox_app/__init__.py`

Add imports and `__all__` entries for the new public symbols (exceptions, store classes, dataclasses ready for external use).

### Step 6 — AC-5: Tests

**File:** `tests/test_templates.py`

- `test_create_template` — CRUD round-trip
- `test_create_rejects_executable` — `{{% code %}}`, `{% raw %}`, `exec(` each raise `ValueError`
- `test_extract_variables` — finds `{{var}}`, ignores `{{%}}`
- `test_render_success` — variables interpolated correctly
- `test_render_missing_required_variable` — raises `MissingTemplateVariableError` with `MISSING_TEMPLATE_VARIABLE` code
- `test_estimate_tokens` — non-zero int returned
- `test_version_list_and_rollback` — save versions on each update, restore from version

**File:** `tests/test_ab_experiments.py`

- `test_create_experiment_success` — valid variants + metrics
- `test_create_fails_on_weight_not_100` — sum != 100 raises `ValueError`
- `test_create_fails_on_invalid_metric` — unknown metric raises `ValueError`
- `test_status_lifecycle` — SCHEDULED→RUNNING→COMPLETED works; invalid transitions raise
- `test_list_and_get` — basic store operations

## Dependencies

No new dependencies — pure Python stdlib (`dataclasses`, `re`, `enum`, `datetime`, `uuid`).

## Constraints

- Minimal diff: all new code in 3 new source files + 2 new test files; only `__init__.py` touched
- No secrets anywhere
- All ACs covered by automated tests
- In-memory stores (no database) — consistent with current app style
