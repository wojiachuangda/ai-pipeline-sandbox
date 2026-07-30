# T-013 工具注册（MCP）、绑定与 Skill 插件 — Implementation Plan

## Context

- **Repo**: Python 3.11+ package (`sandbox-app`) with setuptools, pytest, ruff
- **Current scaffold**: `src/sandbox_app/core.py` — `health()` / `ping()` helpers only
- **This task**: Tool registry, Agent↔Tool binding, Skill metadata upload — pure in-memory, no real MCP server
- **Pattern reference**: T-002 Agent Registration API (FastAPI + Pydantic v2 + in-memory store)

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Web framework | **FastAPI** | Consistent with T-002; Pydantic validation, auto OpenAPI, TestClient |
| Storage | **In-memory dict** | No database in skeleton; sufficient for this scope; consistent with prior tasks |
| ID generation | **uuid4** | Standard, collision-free |
| Tool schema | **free-form `dict`** for `input_schema` | Accepts arbitrary JSON Schema; Pydantic validates it's a dict |
| Binding limit | **50 per agent** (configurable in store) | AC requires max 50; use a smaller constant in tests |
| MCP connectivity | **Mock only** | AC-5: no real MCP server needed; `endpoint` field stored but never dialed |
| Skill files | **Path stub** | `file_path` stored as string; no real file I/O |
| Structure | New files under `src/sandbox_app/` | Keep `core.py` pure; add `tool_*.py` module triplet |

## Files to Create / Modify

```
src/sandbox_app/
├── __init__.py          # [MODIFY] export tool/skill/binding symbols
├── core.py              # [KEEP]   unchanged
├── tool_models.py       # [NEW]    Pydantic schemas: Tool, Binding, Skill, enums
├── tool_store.py        # [NEW]    in-memory stores with business rules
├── tool_routes.py       # [NEW]    FastAPI APIRouters for all three domains
└── app.py               # [NEW]    FastAPI app factory

tests/
├── test_core.py         # [KEEP]   unchanged
└── test_tool_api.py     # [NEW]    API tests covering all 5 ACs

pyproject.toml           # [MODIFY] add fastapi + uvicorn to dependencies
```

## Step-by-Step

### Step 1: Add dependencies (`pyproject.toml`)

Add `fastapi` and `uvicorn[standard]` to `dependencies`, `httpx` to dev deps.

### Step 2: Create `tool_models.py` — Pydantic schemas

**Enums:**
```python
class ToolType(str, Enum):
    API = "API"
    CLI = "CLI"
    FUNCTION = "FUNCTION"
    MCP = "MCP"

class BindingPermission(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ALLOW_WITH_APPROVAL = "ALLOW_WITH_APPROVAL"

class SkillStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
```

**Tool schemas:**
```python
class ToolCreateRequest(BaseModel):
    name: str
    tool_type: ToolType
    input_schema: dict          # required — JSON Schema shape
    description: str | None = None
    endpoint: str | None = None # MCP endpoint (stub, no dial)

class ToolResponse(BaseModel):
    tool_id: str = Field(default_factory=_new_id)
    name: str
    tool_type: ToolType
    input_schema: dict
    description: str | None = None
    endpoint: str | None = None
    created_at: str = Field(default_factory=_now_iso)
```

**Binding schemas:**
```python
class RateLimit(BaseModel):
    max_requests: int
    window_seconds: int

class BindingCreateRequest(BaseModel):
    agent_id: str
    tool_id: str
    permission: BindingPermission
    rate_limit: RateLimit | None = None

class BindingResponse(BaseModel):
    binding_id: str = Field(default_factory=_new_id)
    agent_id: str
    tool_id: str
    permission: BindingPermission
    rate_limit: RateLimit | None = None
    created_at: str = Field(default_factory=_now_iso)
```

**Skill schemas:**
```python
class SkillCreateRequest(BaseModel):
    name: str
    description: str | None = None
    file_path: str | None = None  # local path stub

class SkillResponse(BaseModel):
    skill_id: str = Field(default_factory=_new_id)
    name: str
    description: str | None = None
    status: SkillStatus = SkillStatus.PENDING_REVIEW
    file_path: str | None = None
    created_at: str = Field(default_factory=_now_iso)

class SkillStatusUpdateRequest(BaseModel):
    status: SkillStatus  # only APPROVED is valid from PENDING_REVIEW
```

### Step 3: Create `tool_store.py` — In-memory stores

**`ToolStore`:**
- `register(payload) → dict` — insert tool, return record
- `get(tool_id) → dict | None` — lookup
- `list() → list[dict]` — all tools

**`BindingStore`:**
- `bind(payload) → dict` — create binding; raises `BindingLimitError` if agent already has ≥ MAX_BINDINGS (default 50)
- `get(binding_id) → dict | None`
- `list_by_agent(agent_id) → list[dict]`
- `delete(binding_id) → bool`
- `MAX_BINDINGS` class constant (50); overridable in constructor for testing

**`SkillStore`:**
- `create(payload) → dict` — create skill with status = PENDING_REVIEW
- `get(skill_id) → dict | None`
- `update_status(skill_id, new_status) → dict` — validates transition PENDING_REVIEW → APPROVED; raises `InvalidStatusTransitionError` otherwise

**Custom exceptions:**
```python
class BindingLimitError(Exception): ...
class InvalidStatusTransitionError(Exception): ...
```

### Step 4: Create `tool_routes.py` — API endpoints

Three routers on distinct prefixes:

#### Tools (`/tools`)
| Method | Path | Handler | Status | AC |
|--------|------|---------|--------|-----|
| `POST` | `/tools` | `register_tool` | 201 | AC-1 |
| `GET` | `/tools/{tool_id}` | `get_tool` | 200 | AC-1 |
| `GET` | `/tools` | `list_tools` | 200 | — |

- `POST` validates `input_schema` is present (Pydantic enforces); returns `ToolResponse` with generated `tool_id`
- Missing `input_schema` → Pydantic 422 (tested explicitly)

#### Bindings (`/bindings`)
| Method | Path | Handler | Status | AC |
|--------|------|---------|--------|-----|
| `POST` | `/bindings` | `create_binding` | 201 | AC-2 |
| `GET` | `/bindings` | `list_bindings` | 200 | AC-2 |
| `DELETE` | `/bindings/{binding_id}` | `delete_binding` | 204 | — |

- `POST` checks tool exists (404 if not), checks binding limit → `HTTPException(400, "BINDING_LIMIT_EXCEEDED")`
- `rate_limit` stored as-is when provided
- Query param `?agent_id=` filters listing

#### Skills (`/skills`)
| Method | Path | Handler | Status | AC |
|--------|------|---------|--------|-----|
| `POST` | `/skills` | `create_skill` | 201 | AC-3 |
| `GET` | `/skills/{skill_id}` | `get_skill` | 200 | AC-3 |
| `PATCH` | `/skills/{skill_id}/status` | `update_skill_status` | 200 | AC-3 |

- `POST` returns skill with `status: "PENDING_REVIEW"`
- `PATCH` transitions to `APPROVED`; any other transition → `HTTPException(400, "INVALID_STATUS_TRANSITION")`

### Step 5: Create `app.py` — FastAPI app factory

```python
from fastapi import FastAPI
from .tool_routes import tool_router, binding_router, skill_router, init_stores

def create_app() -> FastAPI:
    app = FastAPI(title="Tool Registry & Skill API")
    init_stores()
    app.include_router(tool_router)
    app.include_router(binding_router)
    app.include_router(skill_router)
    return app
```

### Step 6: Update `__init__.py`

Export new public symbols: `ToolStore`, `BindingStore`, `SkillStore`, `create_app`, model classes.

### Step 7: Create `tests/test_tool_api.py` — 12 test cases

| # | Test | Covers |
|---|------|--------|
| 1 | `test_register_tool_ok` | AC-1: POST /tools → 201, tool_id returned, all 4 types accepted |
| 2 | `test_register_tool_missing_input_schema` | AC-1: POST without input_schema → 422 |
| 3 | `test_get_tool_found` | AC-1: GET /tools/{id} → 200 |
| 4 | `test_get_tool_not_found` | AC-1: GET unknown → 404 |
| 5 | `test_create_binding_allow` | AC-2: POST /bindings with ALLOW → 201 |
| 6 | `test_create_binding_deny` | AC-2: POST /bindings with DENY → 201 |
| 7 | `test_create_binding_with_approval_and_rate_limit` | AC-2: ALLOW_WITH_APPROVAL + rate_limit struct → 201, rate_limit preserved |
| 8 | `test_binding_limit_exceeded` | AC-2: create N (≤50) bindings → error on N+1; use small limit like 3 for test speed |
| 9 | `test_create_skill_pending_review` | AC-3: POST /skills → 201, status=PENDING_REVIEW |
| 10 | `test_approve_skill` | AC-3: PATCH status → APPROVED → 200 |
| 11 | `test_skill_invalid_status_transition` | AC-3: PATCH APPROVED → APPROVED or APPROVED → PENDING_REVIEW → 400 |
| 12 | `test_binding_nonexistent_tool` | AC-2: bind to nonexistent tool_id → 404 |

### Step 8: Verify

```bash
pip install -e ".[dev]"
pytest -v tests/
ruff check src/ tests/
```

## Acceptance Criteria Mapping

| AC | Requirement | Tests | Implementation |
|----|-------------|-------|----------------|
| AC-1 | Tool registration: API/CLI/FUNCTION/MCP types; input_schema required; returns tool_id | #1–#4 | `tool_models.py` + `tool_store.py` + `tool_routes.py` POST/GET |
| AC-2 | Agent-tool binding: ALLOW/DENY/ALLOW_WITH_APPROVAL; rate_limit struct; max 50 | #5–#8, #12 | `BindingStore` with limit + `tool_routes.py` POST bindings |
| AC-3 | Skill metadata upload (path stub); PENDING_REVIEW→APPROVED | #9–#11 | `SkillStore` with status validation + `tool_routes.py` POST/PATCH |
| AC-4 | Tests cover registration, binding, limit rejection, status transitions | All 12 tests | `tests/test_tool_api.py` |
| AC-5 | No real MCP server; endpoint check mockable | — (by design) | `endpoint` stored as string, never dialed |

## Out of Scope

- Real MCP server connectivity (AC-5 says mock only)
- Authentication / authorization (no secrets per constraints)
- Real file storage for skill binaries (path stub only)
- Tool execution / invocation (registration and binding only)
- Agent model — referenced by `agent_id` string only (no FK validation)

## File Inventory (diff summary)

| File | Action | Lines Δ |
|------|--------|---------|
| `pyproject.toml` | modify | ~3 |
| `src/sandbox_app/tool_models.py` | new | ~75 |
| `src/sandbox_app/tool_store.py` | new | ~90 |
| `src/sandbox_app/tool_routes.py` | new | ~100 |
| `src/sandbox_app/app.py` | new | ~12 |
| `src/sandbox_app/__init__.py` | modify | ~5 |
| `tests/test_tool_api.py` | new | ~170 |
| **Total** | | **~455 lines** |
