# T-011 节点类型与协作模式/上下文 — Implementation Plan

## Goal

Implement node-type enumeration & validation, agent-reference integrity checks, collaboration-mode configuration, and context-scope management with size-threshold enforcement. All acceptance criteria are met with automated tests and minimal diff.

## Current State

- **Package**: `src/sandbox_app/` — currently only `core.py` with `health()` / `ping()` stubs.
- **Tests**: `tests/test_core.py` — two trivial tests for the stubs.
- **Tooling**: Python ≥3.11, pytest ≥8.0, ruff ≥0.8. CI runs `ruff check .` then `pytest -q`.

## Plan — Step by Step

### Step 1 — Node Types & Collaboration Modes (pure enums + dataclasses)

**New file**: `src/sandbox_app/nodes.py`

Define the domain types:

- `NodeType` (enum): `AGENT | CONDITION | FOREACH | PARALLEL_GATEWAY | SUB_WORKFLOW`
- `CollabMode` (enum): `SEQUENTIAL | PARALLEL | CONSENSUS | LOOP`
- `ContextScope` (enum): `GLOBAL | NODE | SESSION`
- `AgentRef` (dataclass): `id: str`, `status: str` (default `"ACTIVE"`)
- `ContextVar` (dataclass): `scope: ContextScope`, `key: str`, `value: str`
- `NodeConfig` (dataclass):
  - `type: NodeType`
  - `agent_ref: Optional[AgentRef]` (required when type is AGENT, `None` otherwise)
  - `collab: CollabMode` (default `SEQUENTIAL`)
  - `context_vars: list[ContextVar]` (default empty)
  - `max_context_size: int` (bytes, default 1 MiB)
  - `voting_nodes: int` (default 0, must be ≥2 when collab is CONSENSUS)

### Step 2 — Validation Logic

**New file**: `src/sandbox_app/validation.py`

Pure functions — no I/O, no side effects:

- `validate_node_config(nc: NodeConfig) -> list[str]` — returns a list of error strings (empty = valid), covering:
  - Unknown/invalid `NodeType` (already enforced by enum, but explicitly tested).
  - AGENT node missing `agent_ref` → `"AGENT node requires agent_ref"`.
  - AGENT node with non-ACTIVE agent status → `"Agent must be ACTIVE"`.
  - CONSENSUS mode with `voting_nodes < 2` → `"CONSENSUS requires at least 2 voting nodes"`.
  - Any other schema-level invariant.

- `validate_context_size(vars: list[ContextVar], max_bytes: int) -> str | None`:
  - Serialize keys + values, sum byte lengths. If total > `max_bytes` return `"CONTEXT_SIZE_EXCEEDED: <N> bytes over limit"`, else `None`.
  - Allows a tiny threshold (e.g. `max_context_size=8`) to make the limit trivially testable.

- Re-export clean public API through `src/sandbox_app/__init__.py`.

### Step 3 — Tests (acceptance criteria AC-1 through AC-5)

**New file**: `tests/test_nodes.py`

| AC | Test name | What it verifies |
|----|-----------|------------------|
| AC-1 | `test_node_type_enum_all_values` | All five node types are defined and distinct |
| AC-1 | `test_valid_node_config_passes` | A well-formed AGENT config returns zero errors |
| AC-1 | `test_non_agent_type_rejects_agent_ref` | CONDITION etc. with agent_ref → error |
| AC-2 | `test_agent_node_missing_ref` | AGENT without agent_ref → error |
| AC-2 | `test_agent_node_inactive_status` | agent_ref with status `"INACTIVE"` → error |
| AC-3 | `test_collab_mode_all_values` | All four collab modes defined |
| AC-3 | `test_consensus_requires_two_voting_nodes` | CONSENSUS + voting_nodes=1 → error |
| AC-3 | `test_consensus_two_voting_nodes_passes` | CONSENSUS + voting_nodes=2 → OK |
| AC-4 | `test_context_size_within_limit` | Small context vars within limit → no error |
| AC-4 | `test_context_size_exceeded` | Large context vars over tiny limit → `CONTEXT_SIZE_EXCEEDED` |
| AC-5 | (Covers all above — at least one test per error path) | |

Also extend `tests/test_core.py` — no changes needed (existing tests remain passing as a regression guard).

### Step 4 — Wiring & CI

- `src/sandbox_app/__init__.py`: export new symbols from `nodes` and `validation`.
- `pyproject.toml`: no changes needed (deps, paths already correct).
- `README.md`: note new modules.
- Run `ruff check .` and `pytest -q` locally before committing.

## Files Changed (Minimal Diff)

| File | Action | Purpose |
|------|--------|---------|
| `src/sandbox_app/nodes.py` | **NEW** | Enums + dataclasses for node types, collab modes, context |
| `src/sandbox_app/validation.py` | **NEW** | Pure validation functions |
| `src/sandbox_app/__init__.py` | **EDIT** | Export new public API |
| `tests/test_nodes.py` | **NEW** | 10+ tests covering AC-1 through AC-5 |
| `README.md` | **EDIT** | Mention new modules |

Zero changes to `core.py`, `test_core.py`, `pyproject.toml`, or CI config.

## Constraints Checklist

- [x] **Minimal diff**: 2 new domain files, 1 new test file, 1 edit to `__init__.py`, 1 doc edit.
- [x] **Automated tests per AC**: Each AC has ≥1 test; AC-5 is the aggregate coverage.
- [x] **No secrets**: Pure Python, no credentials or tokens.
- [x] **No external dependencies**: Uses only stdlib (`enum`, `dataclasses`, `typing`).
