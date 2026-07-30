# T-002 Agent Registration & Query API — Implementation Plan

## Context

- **Repo**: Python 3.11+ package (`sandbox-app`) with setuptools, pytest, ruff
- **T-001 skeleton**: `src/sandbox_app/core.py` — `health()` / `ping()` helpers
- **This task**: First real API layer on top of the skeleton; no database yet (in-memory store)

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Web framework | **FastAPI** | Pydantic validation, auto OpenAPI docs, modern async; minimal boilerplate |
| Storage | **In-memory dict** | No DB in skeleton yet; sufficient for this CRUD scope; can swap to SQL later |
| ID generation | **uuid4** | Standard, collision-free, no sequence dependency |
| Testing | **FastAPI TestClient + pytest** | Built-in, no server needed; tests stay fast |
| Structure | New files under `src/sandbox_app/` | Keep core.py pure; add `models.py`, `routes.py`, `store.py` |

## Files to Create / Modify

```
src/sandbox_app/
├── __init__.py          # [MODIFY] export new public symbols
├── core.py              # [KEEP]   unchanged
├── models.py            # [NEW]    Pydantic request/response schemas
├── store.py             # [NEW]    in-memory agent registry with uniqueness check
├── routes.py            # [NEW]    FastAPI APIRouter — POST/GET/PATCH endpoints
└── app.py               # [NEW]    FastAPI app factory

tests/
├── test_core.py         # [KEEP]   unchanged
└── test_agent_api.py    # [NEW]    API tests covering all ACs

pyproject.toml           # [MODIFY] add fastapi + uvicorn to dependencies
```

## Step-by-Step

### Step 1: Add dependencies (`pyproject.toml`)

Add `fastapi` and `uvicorn[standard]` to `dependencies`, and `httpx` to dev deps (TestClient needs it).

### Step 2: Create `models.py` — Pydantic schemas

```python
# Request
class AgentCreateRequest(BaseModel):
    name: str
    agent_type: str
    owner_id: str
    tenant_id: str

class AgentUpdateRequest(BaseModel):
    description: str | None = None
    tags: list[str] | None = None
    owner_id: str | None = None

# Response
class AgentResponse(BaseModel):
    agent_id: str
    name: str
    agent_type: str
    owner_id: str
    tenant_id: str
    status: str          # "INACTIVE"
    created_at: str      # ISO 8601
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
```

### Step 3: Create `store.py` — In-memory registry

- `AgentStore` class with `dict[str, dict]` keyed by `agent_id`
- `register(agent) -> dict`: checks `(tenant_id, name)` uniqueness → raises `DuplicateError` if conflict; inserts + returns
- `get(agent_id) -> dict | None`: simple lookup
- `update(agent_id, patch) -> dict`: merge update, return patched agent; `KeyError` on missing
- Custom `DuplicateError` exception for clean 400 mapping

### Step 4: Create `routes.py` — API endpoints

| Method   | Path              | Handler                | AC  |
|----------|--------------------|------------------------|-----|
| `POST`   | `/agents`         | `register_agent`       | AC-1, AC-2 |
| `GET`    | `/agents/{id}`    | `get_agent`            | AC-3 |
| `PATCH`  | `/agents/{id}`    | `update_agent`         | AC-4 |

- `POST`: validate → call store.register → return 201 with `AgentResponse`
- Duplicate → catch `DuplicateError` → `HTTPException(400, detail="AGENT_NAME_DUPLICATE")`
- `GET`: lookup → 200 or `HTTPException(404)`
- `PATCH`: validate → update → 200; missing → 404

### Step 5: Create `app.py` — FastAPI app factory

```python
from fastapi import FastAPI
from .routes import router

def create_app() -> FastAPI:
    app = FastAPI(title="Agent Registry API")
    app.include_router(router)
    return app
```

### Step 6: Update `__init__.py`

Export the new public API: `AgentStore`, `create_app`, model classes.

### Step 7: Create `tests/test_agent_api.py` — 5 test cases

| Test                        | Covers |
|-----------------------------|--------|
| `test_register_agent_ok`    | AC-1: valid POST → 201, agent_id + status=INACTIVE + created_at |
| `test_register_duplicate`   | AC-2: same tenant+name → 400 with AGENT_NAME_DUPLICATE |
| `test_get_agent_found`      | AC-3: register then GET → 200 with correct fields |
| `test_get_agent_not_found`  | AC-3: GET unknown id → 404 |
| `test_update_agent_metadata`| AC-4: PATCH description/tags/owner_id → 200 with updated fields |

Each test uses `TestClient(app)` — no server startup needed.

### Step 8: Verify

```bash
pip install -e ".[dev]"
pytest -v tests/
ruff check src/ tests/
```

## Out of Scope (per AC-6)

- Template marketplace
- Agent versions
- Activation state transitions (INACTIVE → ACTIVE flow)
- These belong to T-003 / T-004

## File Inventory (diff summary)

| File | Action | Lines Δ |
|------|--------|---------|
| `pyproject.toml` | modify | ~3 |
| `src/sandbox_app/models.py` | new | ~30 |
| `src/sandbox_app/store.py` | new | ~35 |
| `src/sandbox_app/routes.py` | new | ~45 |
| `src/sandbox_app/app.py` | new | ~10 |
| `src/sandbox_app/__init__.py` | modify | ~4 |
| `tests/test_agent_api.py` | new | ~65 |
| **Total** | | **~190 lines** |
