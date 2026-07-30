# T-006: Agent 归档、删除与冷却 — Implementation Plan

## 1. Context

**Repository:** AI Pipeline Sandbox — minimal Python project (`src/sandbox_app/`, `tests/`, CI).  
**Baseline:** Two trivial functions (`health`, `ping`) in `core.py`; no agent model exists yet.  
**Goal:** Add agent lifecycle operations (archive, delete with cooldown, audit trail) with full test coverage.  
**Constraint:** Minimal diff — add new files, no changes to existing `core.py` or `test_core.py`.

## 2. State Machine

```
                 ┌──────────────────────┐
                 │     DEPRECATED       │  ← only valid source for archive
                 └──────┬───────────────┘
                        │ archive()
                        ▼
                 ┌──────────────────────┐
                 │     ARCHIVED         │  ← terminal (can be deleted)
                 └──────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          │ delete()     │ delete()    │
          ▼              ▼             
   DEPRECATED      ARCHIVED           
   (cold check)    (cold check)       
```

- **DEPRECATED** → only state eligible for `archive()`; `archive()` → **ARCHIVED** + returns `archive_id`.
- **ARCHIVED** is terminal (no further state transitions).
- **delete()** accepted only on **DEPRECATED** or **ARCHIVED**; requires `confirm_text="DELETE"`.
- Deletion gated by configurable cooldown (seconds) from `deprecated_at`; returns `DELETION_COOLDOWN_ACTIVE` if not expired.
- All deletions are logged to an in-memory audit store.

## 3. Files to Add

### 3.1 `src/sandbox_app/agent.py` — net-new (~80 lines)

| Symbol | Role |
|---|---|
| `AgentStatus` | `StrEnum`: `DEPRECATED`, `ARCHIVED` |
| `ArchiveError` | Exception for invalid archive attempts |
| `DeleteError` | Exception for invalid delete attempts |
| `CooldownError` | Exception with `.code = "DELETION_COOLDOWN_ACTIVE"` |
| `AuditRecord` | `NamedTuple`: `agent_id`, `action`, `timestamp` |
| `audit_log` | Module-level `list[AuditRecord]` |
| `Agent` | `@dataclass` with `id`, `status`, `deprecated_at`, `archive_id`, `cooldown_seconds` |

**`Agent` methods:**
- `archive() -> str` — raises `ArchiveError` unless `status == DEPRECATED`; sets `status = ARCHIVED`, generates UUID `archive_id`, returns it.
- `delete(confirm_text: str) -> None` — raises `DeleteError` unless `confirm_text == "DELETE"` and `status in (DEPRECATED, ARCHIVED)`; raises `CooldownError` if `cooldown_seconds` has not elapsed since `deprecated_at`; appends to `audit_log`, then marks self as deleted (or removes from registry — for minimal impl, set `status = None` or internal flag).
- `can_delete() -> bool` — checks cooldown elapsed (public helper for tests).

### 3.2 `src/sandbox_app/__init__.py` — append exports

Add exports for `Agent`, `AgentStatus`, `ArchiveError`, `DeleteError`, `CooldownError`, `AuditRecord`, `audit_log`.

### 3.3 `tests/test_agent.py` — net-new (~100 lines)

| Test | AC |
|---|---|
| `test_archive_deprecated_succeeds` | AC-1 |
| `test_archive_returns_archive_id` | AC-1 |
| `test_archive_non_deprecated_raises` | AC-4 |
| `test_archive_archived_raises` | AC-4 |
| `test_delete_without_confirm_text_raises` | AC-4 |
| `test_delete_wrong_confirm_text_raises` | AC-4 |
| `test_delete_deprecated_after_cooldown` | AC-2, AC-4 |
| `test_delete_during_cooldown_returns_error` | AC-3 |
| `test_delete_archived_after_cooldown` | AC-2, AC-4 |
| `test_delete_audit_logged` | AC-3 |
| `test_cooldown_configurable` | AC-2 |

### 3.4 No changes to

- `core.py`, `test_core.py` — untouched
- `pyproject.toml` — no new dependencies needed
- `.github/workflows/ci.yml` — already runs `pytest -q` on all `tests/`

## 4. Implementation Order

1. Write `agent.py` with `AgentStatus`, exceptions, `AuditRecord`, `audit_log`, and `Agent` dataclass.
2. Update `__init__.py` exports.
3. Write `tests/test_agent.py` covering all ACs.
4. Run `pytest -q` and `ruff check .` locally.
5. Commit.

## 5. Key Design Decisions

- **In-memory audit log:** `audit_log: list[AuditRecord]` at module level. Simple, testable, no external deps. Can be swapped for DB later.
- **Cooldown as `Agent` attribute** (`cooldown_seconds`): allows per-agent configuration in tests. `0` = no cooldown (immediate deletion). Default value up for discussion; suggest 0 by default (permissive), override in tests.
- **`deprecated_at` as `float`** (epoch seconds from `time.time()`): simple arithmetic for cooldown check; no `datetime` dependency needed.
- **No `DELETED` status:** for minimal diff, deletion removes the agent or sets an internal flag rather than introducing a new state (T-006 scope is archive+delete, not status enumeration expansion).
- **`CooldownError.code = "DELETION_COOLDOWN_ACTIVE"`**: matches AC-3 requirement exactly as a machine-readable error code.

## 6. Risk & Alternatives

- **Risk:** Auditors may want persistent audit storage. **Mitigation:** Audit interface is separate (`audit_log.append()`); swapping to DB is a one-line change inside `delete()`.
- **Alternative:** Introduce a proper `DELETED` status instead of internal flag. Deferred — cleaner but larger diff; T-006 ACs don't require it.
