# T-003 Implementation Plan: Agent Template Marketplace

## Context

This worktree is a minimal Python 3.11+ scaffold (`sandbox-app`) with `core.py` providing `health()`/`ping()` stubs and `pytest`+`ruff` CI. This is **task T-003** of the 16-task pipeline split from `goal.md`.

**Key constraint:** no real LLM/sandbox calls, automated tests per AC, minimal diff, no secrets.

**Upstream dependency:** T-002 (Agent Registration & Query API, branch `ai/task-2dad2c04`) provides FastAPI foundations, Pydantic models, and `AgentStore` with `register()`/`get()`. T-003 extends that with templates and `create_from_template()`. If T-002 is not yet merged, this plan builds models that compose cleanly when it lands.

---

## Architecture Overview

Follow T-002's pattern: **Pydantic models → in-memory store → pure function API → TestClient**.

```
src/sandbox_app/
  models.py         # Enums, AgentTemplate, Agent dataclasses
  template_store.py # Pre-seeded presets + list/filter/page + custom save
  agent_store.py    # Agent CRUD + create_from_template + save_as_template
  api.py            # Public re-export surface
tests/
  test_templates.py # AC-1, AC-5
  test_agents.py    # AC-2–AC-4, AC-6
```

Storage is thread-safe in-memory dicts. No external DB, no HTTP/LLM/sandbox I/O.

---

## Step-by-step Plan

### Step 1 — Data Models (`src/sandbox_app/models.py`)

| Class | Fields |
|-------|--------|
| `AgentType` (str enum) | `LLM`, `RAG`, `CODE` |
| `AgentStatus` (str enum) | `ACTIVE`, `INACTIVE` |
| `AgentTemplate` (dataclass) | `id: str` (PRD IDs: `TPL-LLM-V1` etc.), `name: str`, `agent_type: AgentType`, `description: str`, `keywords: list[str]`, `is_preset: bool`, `default_config: dict` |
| `Agent` (dataclass) | `id: str`, `name: str`, `agent_type: AgentType`, `status: AgentStatus`, `config: dict`, `template_id: str \| None`, `needs_knowledge_base: bool` (AC-3) |

**Per-type `default_config` shapes:**

```python
# LLM (SUB-02 / TPL-LLM-V1)
{"model_name": "claude-sonnet-5", "system_prompt_template": "", "temperature": 0.7}

# RAG (SUB-03 / TPL-RAG-V1)
{"embedding_model": "text-embedding-3-small", "chunk_size": 512, "top_k": 5}

# CODE (SUB-04 / TPL-CODE-V1)
{"allowed_languages": ["python"], "execution_timeout_secs": 30, "memory_limit_mb": 256}
```

The `needs_knowledge_base: bool` on Agent surfaces the RAG constraint without digging into config (AC-3).

### Step 2 — Template Store (`src/sandbox_app/template_store.py`)

Three **pre-seeded presets** per PRD naming convention:

| id | name | type | keywords |
|----|------|------|----------|
| `TPL-LLM-V1` | LLM Agent | LLM | llm, chat, assistant, text |
| `TPL-RAG-V1` | RAG Agent | RAG | rag, retrieval, knowledge, search |
| `TPL-CODE-V1` | Code Execution Agent | CODE | code, sandbox, execute, python |

```python
class TemplateStore:
    def list(keyword=None, agent_type=None, page=1, page_size=20) -> dict:
        # keyword: case-insensitive substring match on name + keywords (AND with agent_type)
        # returns {"items": [...], "total": int, "page": int, "page_size": int}
    def get(template_id) -> AgentTemplate | None: ...
    def save_custom(tenant_id, name, agent) -> AgentTemplate:
        # raises ValueError on tenant+name collision
```

### Step 3 — Agent Store (`src/sandbox_app/agent_store.py`)

```python
class AgentStore:
    def register(name, agent_type, config) -> Agent:
        # standard registration → status ACTIVE (T-002 compatibility)

    def create_from_template(template_id, name, overrides=None) -> Agent:
        # 1. Lookup template → ValueError if missing
        # 2. Deep-copy default_config, merge overrides
        # 3. Create Agent(status=INACTIVE, template_id=...)
        # 4. If RAG: needs_knowledge_base=True + config hint
        # 5. If CODE: validate language/timeout/memory keys present
        # 6. Store & return (same shape as register())

    def get(agent_id) -> Agent | None: ...

    def save_as_template(agent_id, tenant_id, name) -> AgentTemplate:
        # Load agent, delegate to TemplateStore.save_custom()
```

**AC-3 detail:** When creating from `TPL-RAG-V1`, the Agent gets `needs_knowledge_base=True` and config includes `"_hint": "This agent requires a knowledge base to be bound before activation"`.

**AC-4 detail:** When creating from `TPL-CODE-V1`, config always includes `allowed_languages`, `execution_timeout_secs`, `memory_limit_mb` from the preset.

### Step 4 — Public API (`src/sandbox_app/api.py`)

Flat re-exports — tests import from one place:

```python
from .template_store import template_store
from .agent_store import agent_store
```

### Step 5 — Automated Tests

All under `tests/`, uses existing pytest + pythonpath config. Each test gets fresh stores.

#### `tests/test_templates.py` (AC-1, AC-5)

| Test | What it verifies |
|------|-----------------|
| `test_list_all_templates` | Three presets returned, each has correct id/name/type/keywords |
| `test_list_filter_by_keyword` | `keyword="rag"` returns only TPL-RAG-V1 |
| `test_list_filter_by_keyword_no_match` | `keyword="nonexistent"` returns empty items |
| `test_list_filter_by_agent_type` | `agent_type="LLM"` returns only TPL-LLM-V1 |
| `test_list_filter_combined` | keyword + type AND logic |
| `test_list_pagination` | `page_size=1` scrolls through 3 pages, `total=3` |
| `test_list_pagination_out_of_range` | page beyond last → empty items |
| `test_save_custom_template` | Register agent, save as template, verify it appears in list |
| `test_save_custom_duplicate_name` | Same tenant+name twice → ValueError |

#### `tests/test_agents.py` (AC-2, AC-3, AC-4, AC-6)

| Test | What it verifies |
|------|-----------------|
| `test_create_from_llm_template` | Agent.status=INACTIVE, agent_type=LLM, model_name/temperature present |
| `test_create_from_rag_template` | `needs_knowledge_base=True`, hint in config |
| `test_create_from_code_template` | `allowed_languages`, `execution_timeout_secs`, `memory_limit_mb` present |
| `test_create_from_unknown_template` | ValueError for bad template_id |
| `test_create_with_overrides` | `overrides={"temperature": 0.2}` deep-merges correctly |
| `test_register_vs_template_status` | register → ACTIVE; create_from_template → INACTIVE |
| `test_created_agent_shape_matches_register` | Both return Agent with same fields |
| `test_no_real_calls` | No subprocess, no urllib, no socket — verify stores are purely in-memory |

### Step 6 — Integration

- Update `src/sandbox_app/__init__.py`: add exports from `models`, `template_store`, `agent_store`
- **No changes** to `pyproject.toml` (zero new dependencies)
- **No changes** to `.github/workflows/ci.yml`

---

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `src/sandbox_app/models.py` | **NEW** | Dataclasses + enums matching PRD spec |
| `src/sandbox_app/template_store.py` | **NEW** | Presets, list/filter/page, custom save |
| `src/sandbox_app/agent_store.py` | **NEW** | register, create_from_template, save_as_template |
| `src/sandbox_app/api.py` | **NEW** | Public re-exports |
| `src/sandbox_app/__init__.py` | **EDIT** | Wire new modules |
| `tests/test_templates.py` | **NEW** | AC-1, AC-5 |
| `tests/test_agents.py` | **NEW** | AC-2, AC-3, AC-4, AC-6 |

---

## Acceptance Criteria Mapping

| AC | Implementation |
|----|---------------|
| AC-1: Pre-seed, list, filter by keyword/type, paginate | `TemplateStore.list()` with keyword + agent_type + page/page_size |
| AC-2: Create from LLM/RAG/CODE, INACTIVE, same shape as register | `AgentStore.create_from_template()` returns Agent(status=INACTIVE) |
| AC-3: RAG → needs_knowledge_base marker | `needs_knowledge_base=True` on Agent + `_hint` in config |
| AC-4: CODE → language/timeout/memory defaults | `TPL-CODE-V1.default_config` keys always present in created Agent |
| AC-5: Save Agent as custom template, tenant-unique name | `AgentStore.save_as_template()` → `TemplateStore.save_custom()` |
| AC-6: Automated tests for list, create, duplicate-name error | `test_templates.py` + `test_agents.py` |
| AC-7: No real LLM/sandbox calls | Pure in-memory dicts, zero network or subprocess I/O |
