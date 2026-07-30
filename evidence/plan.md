# Implementation Plan: 知识库注册、导入与检索测试 (T-014)

**源**: goal.md SUB-43～45 | **存根**: docs/goal-split/stubs/T-014.md

---

## 1. Context & Current State

| Item | Detail |
|------|--------|
| Language | Python 3.11+, setuptools |
| Test framework | pytest ≥8.0, conftest autouse fixtures for store isolation |
| Linter | ruff, line-length=100 |
| Existing code | `src/sandbox_app/` — `health()`, `ping()` only; no KB code anywhere |
| CI | GitHub Actions: ruff check + pytest |
| Project conventions | dataclass models (no Pydantic), in-memory dict stores, error dicts `{"code": "..."}` not exceptions, `__init__.py` re-exports |

## 2. Acceptance Criteria → Implementation Mapping

| AC | What to Build | Key Files |
|----|--------------|-----------|
| AC-1: 注册知识库 | `register_kb()` → `KnowledgeBase` dataclass, `status="INITIALIZED"` | `src/sandbox_app/kb/models.py`, `src/sandbox_app/kb/service.py` |
| AC-2: 文档导入 | `import_documents()` → `ImportJob` dataclass, state machine QUEUED→COMPLETED (sync) | same files |
| AC-3: 检索测试 API | `search()` → results sorted by `score` desc, `latency_ms`, `KB_NOT_ACTIVE` error dict | `src/sandbox_app/kb/service.py` |
| AC-4: 内存向量/假 embedding | `FakeEmbedder` + `InMemoryVectorStore` — zero external deps | `src/sandbox_app/kb/embedding.py`, `vector_store.py` |
| AC-5: 测试覆盖 | pytest: 注册、导入、检索、未激活错误、embedder determinism | `tests/test_kb.py`, `tests/conftest.py` |

## 3. File Plan (Minimal Diff)

```
src/sandbox_app/
├── __init__.py              # (no change — re-exports optional)
├── core.py                  # (no change)
└── kb/                      # (new package)
    ├── __init__.py           # re-exports: register_kb, import_documents, search
    ├── models.py             # KnowledgeBase, ImportJob, SearchResult dataclasses
    ├── embedding.py          # FakeEmbedder class
    ├── vector_store.py       # InMemoryVectorStore class
    └── service.py            # register_kb, import_documents, search functions

tests/
├── conftest.py               # (edit) add kb_store reset fixture
└── test_kb.py               # (new) tests for all 5 ACs
```

## 4. Models (`src/sandbox_app/kb/models.py`)

```python
from dataclasses import dataclass, field
from uuid import uuid4

@dataclass
class KnowledgeBase:
    name: str
    embedding_model: str
    chunk_strategy: str
    vector_db_config: dict
    id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "INITIALIZED"

@dataclass
class ImportJob:
    kb_id: str
    source_type: str     # "FILE"
    source_path: str
    id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "QUEUED"

@dataclass
class SearchResult:
    doc_id: str
    chunk_text: str
    score: float
```

## 5. Embedding (`src/sandbox_app/kb/embedding.py`)

`FakeEmbedder` class — deterministic hash-based pseudo-vectors:
- `__init__(self, dim: int = 128)` — configurable dimension
- `embed(self, text: str) -> list[float]` — hash each character with position, normalize to [-1, 1], pad to `dim`
- Same text → same vector (deterministic), different texts → different vectors
- Zero external dependencies

## 6. Vector Store (`src/sandbox_app/kb/vector_store.py`)

`InMemoryVectorStore` class — dict-backed cosine-similarity search:
- `add(self, id: str, vector: list[float], metadata: dict) -> None`
- `search(self, query_vector: list[float], top_k: int = 5) -> list[tuple[str, float, dict]]` — returns `(id, score, metadata)` sorted by cosine similarity descending
- `clear(self) -> None` — for test isolation
- All in-memory, no persistence

## 7. Service Layer (`src/sandbox_app/kb/service.py`)

### Error convention (match project pattern)
```python
def _error(code: str, detail: str = "") -> dict:
    return {"code": code, "detail": detail}
```
Business errors are returned as dicts, NOT raised.

### `register_kb(name, embedding_model, chunk_strategy, vector_db_config) -> KnowledgeBase | dict`
- Create `KnowledgeBase` with `status="INITIALIZED"`, persist to `_kb_store`
- Return the dataclass object

### `import_documents(kb_id, source_type, source_path) -> ImportJob | dict`
- Lookup kb_id → if missing, return `{"code": "KB_NOT_FOUND"}`
- Create `ImportJob` with `status="QUEUED"`
- Synchronous processing: chunk text (split by `\n\n` paragraphs) → embed each chunk → store in vector store
- Transition job to `status="COMPLETED"`, transition kb to `status="ACTIVE"`
- Return the job

### `search(kb_id, query_text, top_k=5) -> dict`
- Lookup kb_id → if missing, return `{"code": "KB_NOT_FOUND"}`
- If kb.status != "ACTIVE" → return `{"code": "KB_NOT_ACTIVE"}`
- Record `start = time.perf_counter()`
- Embed query → vector store search → build `results: list[SearchResult]`, sorted by score desc
- Return `{"results": [...], "latency_ms": round((perf_counter() - start) * 1000, 2)}`

### Store & reset

```python
_kb_store: dict[str, KnowledgeBase] = {}
_job_store: dict[str, ImportJob] = {}
_vector_store = InMemoryVectorStore()

def reset() -> None:
    _kb_store.clear()
    _job_store.clear()
    _vector_store.clear()
```

## 8. Test Plan (`tests/test_kb.py`)

```python
import pytest
from sandbox_app.kb import register_kb, import_documents, search, reset
from sandbox_app.kb.embedding import FakeEmbedder

# ── AC-1: 注册知识库 ──

def test_register_kb_returns_initialized():
    kb = register_kb("test-kb", "fake-embedding/v1", "fixed-size-256",
                     {"type": "in_memory", "dim": 128})
    assert kb.status == "INITIALIZED"
    assert kb.name == "test-kb"
    assert kb.embedding_model == "fake-embedding/v1"
    assert kb.chunk_strategy == "fixed-size-256"
    assert kb.vector_db_config["type"] == "in_memory"

# ── AC-2: 文档导入 ──

def test_import_documents_file_source():
    kb = register_kb(...)
    job = import_documents(kb.id, "FILE", "/fakepath/doc.txt")
    assert job.source_type == "FILE"
    assert job.status == "COMPLETED"

def test_import_documents_nonexistent_kb():
    result = import_documents("nonexistent", "FILE", "/x.txt")
    assert result["code"] == "KB_NOT_FOUND"

# ── AC-3: 检索 ──

def test_search_returns_results_sorted_by_score():
    kb = register_kb(...)
    import_documents(kb.id, "FILE", "/doc.txt")
    resp = search(kb.id, "query text")
    assert "results" in resp
    assert "latency_ms" in resp
    scores = [r.score for r in resp["results"]]
    assert scores == sorted(scores, reverse=True)

def test_search_unactivated_kb_returns_error():
    kb = register_kb(...)  # never imported → INITIALIZED, not ACTIVE
    resp = search(kb.id, "query")
    assert resp["code"] == "KB_NOT_ACTIVE"

# ── AC-4: 内存向量/假 embedding ──

def test_fake_embedder_deterministic():
    e = FakeEmbedder(dim=64)
    assert e.embed("hello") == e.embed("hello")

def test_fake_embedder_different_texts_different_vectors():
    e = FakeEmbedder(dim=64)
    assert e.embed("hello") != e.embed("world")

def test_vector_store_search_returns_correct_order():
    store = InMemoryVectorStore()
    store.add("a", [1.0, 0.0], {"text": "aligned"})
    store.add("b", [0.0, 1.0], {"text": "orthogonal"})
    results = store.search([1.0, 0.0], top_k=2)
    assert results[0][0] == "a"  # highest cosine sim
    assert results[0][1] > results[1][1]  # scores descending

# ── AC-5: 综合覆盖 ──
# All of the above + conftest.py autouse reset fixture
```

## 9. Test Fixtures (`tests/conftest.py`)

```python
# Extend existing conftest.py (or create if absent):
import pytest
from sandbox_app.kb.service import reset as kb_reset

@pytest.fixture(autouse=True)
def _clear_kb_store() -> None:
    kb_reset()
```

## 10. Execution Order

| Step | Description | Verification |
|------|-------------|-------------|
| 1 | Create `src/sandbox_app/kb/` package: `models.py` → `embedding.py` → `vector_store.py` → `service.py` → `__init__.py` | `python -c "from sandbox_app.kb import register_kb"` |
| 2 | Wire `tests/conftest.py` with autouse reset fixture | — |
| 3 | Write `tests/test_kb.py` covering all ACs | — |
| 4 | Run `pytest -q` then `ruff check .` | all green |
| 5 | Commit | — |

**Estimated footprint**: ~220 lines src, ~120 lines tests. No new dependencies. No secrets.
