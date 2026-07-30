# Implementation Plan: T-004 Agent 版本、状态机与服务绑定最小集

## Context

This task implements the minimal set of Agent version control, state machine, and service binding APIs specified in goal.md (SUB-07 through SUB-12, SUB-16). The repository is a minimal Python sandbox (`sandbox_app`) with pure in-memory domain logic — no HTTP framework, no database. All state lives in module-level stores.

**Existing structure:**
- `src/sandbox_app/__init__.py` — exports `health`, `ping`
- `src/sandbox_app/core.py` — `health()` and `ping()` helpers
- `tests/test_core.py` — existing tests (untouched)

**Principle:** Minimal diff. Add new modules; do not modify `core.py` or `test_core.py`.

---

## Files to Add/Change

### 1. `src/sandbox_app/models.py` — Domain data classes (NEW)

Pure dataclasses with no logic:

- `Agent` — `agent_id: str`, `name: str`, `agent_type: str`, `status: str` (initially `"INACTIVE"`), `tenant_id: str`, `created_at`, `updated_at`
- `AgentVersion` — `version_id: str`, `agent_id: str`, `version: str` (semver like `"0.1.0"`), `description: str`, `config: dict` (snapshot of agent config — capabilities, tool bindings, knowledge bases, prompt templates), `created_by: str`, `created_at`, `is_current: bool`
- `ServiceBinding` — `agent_id`, `service_type: str` (LLM/EMBEDDING/VECTOR_DB/CODE_SANDBOX/TOOL_GATEWAY), `service_instance_id: str`, `binding_config: dict`, `status: str` (BOUND/UNBOUND)
- `TrafficConfig` — `config_id: str`, `agent_id`, `version_traffic: list[dict]` (each with `version_id` + `weight`), `enable_canary: bool`, `started_at`
- `StatusTransition` — `from_status: str`, `to_status: str`, `timestamp`, `reason`

### 2. `src/sandbox_app/versioning.py` — Version snapshot, list, rollback, diff (NEW)

In-memory store: `_versions: dict[str, list[AgentVersion]]` keyed by agent_id.

**Functions:**

- `create_version(agent_id, description, config, is_major=False) -> AgentVersion`
  - Generates `version` following semver from current latest (start at `0.1.0`). `is_major=True` → MAJOR+1, MINOR/PATCH→0; else MINOR+1, PATCH→0.
  - Snapshots the passed `config` dict.
  - Sets `is_current=True` on the new version, `False` on all others.
  - Rejects if agent has ≥100 versions (`VERSION_LIMIT_EXCEEDED`).
  - Rejects if agent status is `DEPRECATED` (403).

- `list_versions(agent_id, page=1, page_size=20) -> dict`
  - Returns `{"versions": [...], "total": N}` sorted by `created_at` descending.
  - Each entry: `version_id`, `version`, `description`, `created_by`, `created_at`, `is_current`.

- `rollback(agent_id, target_version_id, rollback_reason="") -> AgentVersion`
  - Finds target version; copies its `config`.
  - Creates a new PATCH version (PATCH+1 from current latest) with the target's config.
  - Returns `{"new_version": ..., "new_version_id": ..., "status": "ROLLBACK_COMPLETE"}`.
  - Rejects if target version not found (404) or agent DEPRECATED (403).

- `diff_versions(agent_id, version_id_a, version_id_b) -> dict`
  - Deep-compares the `config` dicts of two versions.
  - Returns `{"diffs": [{"field_path": str, "old_value": Any, "new_value": Any, "change_type": "ADDED"|"MODIFIED"|"REMOVED"}]}`.
  - Rejects if either version not found (404).

### 3. `src/sandbox_app/state_machine.py` — Status state machine (NEW)

In-memory store: `_agent_states: dict[str, str]` plus a reference to service bindings for validation.

**Valid transitions:** `INACTIVE ↔ ACTIVE`, `ACTIVE → DEPRECATED` (irreversible). `DEPRECATED` is terminal.

**Functions:**

- `transition_status(agent_id, target_status, reason="") -> dict`
  - Validates the transition is legal → else `INVALID_STATUS_TRANSITION` error.
  - `INACTIVE → ACTIVE`: checks that at least one critical service is bound (see §4). Rejects with 400 `MISSING_REQUIRED_BINDING` if not.
  - `ACTIVE → DEPRECATED`: sets `approval_required=True` in response (mock — see §6).
  - Returns `{"agent_id": ..., "current_status": ..., "updated_at": ..., "approval_required": bool}`.

- `get_status(agent_id) -> str` — current status lookup.

- `is_valid_transition(from_status, to_status) -> bool` — pure function, testable in isolation.

### 4. `src/sandbox_app/service_binding.py` — Service binding BIND/UNBIND (NEW)

In-memory store: `_bindings: dict[tuple[str, str, str], ServiceBinding]` keyed by `(agent_id, service_type, service_instance_id)`.

**Critical service map** (per `agent_type`):
- `LLM` → must bind `LLM`
- `RAG` → must bind `LLM`, `EMBEDDING`, `VECTOR_DB`
- `CODE_EXEC` → must bind `CODE_SANDBOX`
- Other types → no mandatory bindings (flexible)

**Functions:**

- `bind_service(agent_id, service_type, service_instance_id, binding_config=None) -> ServiceBinding`
  - Creates or updates a binding with `status=BOUND`.
  - Returns the binding record.

- `unbind_service(agent_id, service_type, service_instance_id) -> ServiceBinding`
  - If agent is `ACTIVE` and `service_type` is critical for the agent's type → 409 `CRITICAL_SERVICE_IN_USE`.
  - Sets `status=UNBOUND`.
  - Returns the updated record.

- `get_bindings(agent_id) -> list[ServiceBinding]` — all bindings for an agent.

- `has_critical_bindings(agent_id, agent_type) -> bool` — used by state machine to gate `INACTIVE → ACTIVE`.

### 5. `src/sandbox_app/traffic.py` — Multi-version traffic / canary config (NEW)

In-memory store: `_traffic_configs: dict[str, TrafficConfig]` keyed by `agent_id`.

**Functions:**

- `configure_traffic(agent_id, version_traffic, enable_canary=False) -> TrafficConfig`
  - Validates `sum(weight) == 100` → else 400 `TRAFFIC_WEIGHT_INVALID`.
  - Validates `len(version_traffic) <= 3` → else 400 `TOO_MANY_VERSIONS`.
  - Validates all referenced versions exist and their agent is `ACTIVE`.
  - Creates/updates the traffic config. Returns the config.

- `get_traffic_config(agent_id) -> TrafficConfig | None`

- `route_request(agent_id) -> str | None` — weighted random selection of a `version_id` (bonus; useful for integration tests).

### 6. `src/sandbox_app/approval.py` — Mock approval engine (NEW)

No state. Always returns a mock result.

- `check_approval_required(action: str, agent_id: str) -> dict`
  - Returns `{"approval_required": True, "approval_id": "mock-...", "status": "PENDING"}` for `ACTIVATE` and `DEPRECATE` actions.
  - Returns `{"approval_required": False}` for all other actions.

---

## Test Files

### 7. `tests/test_versioning.py` (NEW)
- `test_create_version_initial` — first version is `0.1.0`, `is_current=True`
- `test_create_version_minor_bump` — second non-major → `0.2.0`
- `test_create_version_major_bump` — `is_major=True` → `1.0.0`
- `test_list_versions_descending` — list returns reverse chronological
- `test_list_versions_is_current` — only one version has `is_current=True`
- `test_version_limit` — 100 versions ok, 101st raises error
- `test_rollback_creates_patch` — rollback creates PATCH+1 with target config
- `test_rollback_nonexistent_target` — 404
- `test_diff_added_modified_removed` — covers all change_type values
- `test_diff_nonexistent_version` — 404

### 8. `tests/test_state_machine.py` (NEW)
- `test_valid_transitions` — INACTIVE→ACTIVE, ACTIVE→INACTIVE, ACTIVE→DEPRECATED all work
- `test_invalid_transition_inactive_to_deprecated` — direct INACTIVE→DEPRECATED rejected
- `test_invalid_transition_deprecated_to_anything` — DEPRECATED is terminal
- `test_activate_without_critical_binding` — rejected (need mock bindings)
- `test_activate_with_critical_binding` — succeeds
- `test_deprecate_requires_approval` — `approval_required=True` returned

### 9. `tests/test_service_binding.py` (NEW)
- `test_bind_service` — creates binding, status BOUND
- `test_unbind_service` — status becomes UNBOUND
- `test_unbind_critical_service_while_active` — 409 CRITICAL_SERVICE_IN_USE
- `test_unbind_noncritical_while_active` — allowed
- `test_unbind_while_inactive` — always allowed
- `test_has_critical_bindings` — returns True only when all required types bound

### 10. `tests/test_traffic.py` (NEW)
- `test_valid_traffic_config` — weights sum to 100, ≤3 versions
- `test_weight_sum_not_100` — 400 TRAFFIC_WEIGHT_INVALID
- `test_too_many_versions` — >3 versions → 400
- `test_weighted_routing` — basic distribution check
- `test_canary_mode` — `enable_canary=True` reflected

### 11. `tests/test_approval.py` (NEW)
- `test_approval_required_for_activate` — returns `approval_required=True`
- `test_approval_required_for_deprecate` — returns `approval_required=True`
- `test_approval_not_required_for_other_actions` — False for non-sensitive actions

---

## Acceptance Criteria Coverage

| AC | Description | Covered By |
|----|-------------|------------|
| AC-1 | Version snapshot API: version/version_id, list reverse, is_current | `versioning.py` + `test_versioning.py` |
| AC-2 | Rollback: new PATCH version, config copy from target | `versioning.py::rollback()` + tests |
| AC-3 | Two-version diff: field_path + change_type | `versioning.py::diff_versions()` + tests |
| AC-4 | Status transitions: INVALID_STATUS_TRANSITION; ACTIVATE needs binding | `state_machine.py` + tests |
| AC-5 | BIND/UNBIND; ACTIVE forbids critical unbind (409) | `service_binding.py` + tests |
| AC-6 | Traffic: weight sum=100, max 3 versions | `traffic.py` + tests |
| AC-7 | Tests covering all of the above | 5 test files, ~25 test cases |
| AC-8 | Approval mock (approval_required field, no real engine) | `approval.py` + `test_approval.py` |

---

## Verification

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
```

---

## Diff Summary

- **6 new source files** in `src/sandbox_app/`
- **5 new test files** in `tests/`
- **0 existing files modified**
- **No new dependencies** (stdlib only: `dataclasses`, `uuid`, `datetime`, `copy`, `itertools`)
- **No secrets, no HTTP, no database**
