"""Knowledge base service layer — register, import, search with in-memory stores."""

from __future__ import annotations

import time

from .embedding import FakeEmbedder
from .models import ImportJob, KnowledgeBase, SearchResult
from .vector_store import InMemoryVectorStore

# ── Module-level stores ──────────────────────────────────────────────────────

_kb_store: dict[str, KnowledgeBase] = {}
_job_store: dict[str, ImportJob] = {}
_vector_store = InMemoryVectorStore()
_embedder = FakeEmbedder(dim=128)


def reset() -> None:
    """Clear all stores (used for test isolation)."""
    _kb_store.clear()
    _job_store.clear()
    _vector_store.clear()


# ── Error helper ─────────────────────────────────────────────────────────────


def _error(code: str, detail: str = "") -> dict:
    return {"code": code, "detail": detail}


# ── Public API ───────────────────────────────────────────────────────────────


def register_kb(
    name: str,
    embedding_model: str,
    chunk_strategy: str,
    vector_db_config: dict,
) -> KnowledgeBase:
    """Register a new knowledge base — returns it with ``status="INITIALIZED"``."""
    kb = KnowledgeBase(
        name=name,
        embedding_model=embedding_model,
        chunk_strategy=chunk_strategy,
        vector_db_config=vector_db_config,
    )
    _kb_store[kb.id] = kb
    return kb


def import_documents(
    kb_id: str,
    source_type: str,
    source_path: str,
) -> ImportJob | dict:
    """Import documents from *source_path* into the knowledge base *kb_id*.

    Currently only ``"FILE"`` source type is supported.  The file is read,
    chunked by blank-line-separated paragraphs, embedded, and stored in the
    vector store.  Processing is synchronous — the job transitions from
    ``QUEUED`` to ``COMPLETED`` within the same call.
    """
    kb = _kb_store.get(kb_id)
    if kb is None:
        return _error("KB_NOT_FOUND", f"knowledge base '{kb_id}' not found")

    if source_type != "FILE":
        return _error("UNSUPPORTED_SOURCE_TYPE", f"source_type '{source_type}' not supported")

    job = ImportJob(kb_id=kb_id, source_type=source_type, source_path=source_path)
    _job_store[job.id] = job

    # ── Synchronous processing ───────────────────────────────────────────
    try:
        with open(source_path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return _error("FILE_READ_ERROR", f"cannot read '{source_path}'")

    # Chunk by blank-line-separated paragraphs
    chunks = _chunk_text(text)
    if not chunks:
        chunks = [text.strip()] if text.strip() else ["(empty)"]

    for i, chunk in enumerate(chunks):
        chunk_id = f"{job.id}:chunk:{i}"
        vector = _embedder.embed(chunk)
        _vector_store.add(chunk_id, vector, {"text": chunk, "kb_id": kb_id, "job_id": job.id})

    job.status = "COMPLETED"
    kb.status = "ACTIVE"
    return job


def search(
    kb_id: str,
    query_text: str,
    top_k: int = 5,
) -> dict:
    """Search the knowledge base *kb_id* with *query_text*.

    Returns a dict with ``"results"`` (list of ``SearchResult`` sorted by score
    descending) and ``"latency_ms"``, or an error dict.
    """
    kb = _kb_store.get(kb_id)
    if kb is None:
        return _error("KB_NOT_FOUND", f"knowledge base '{kb_id}' not found")

    if kb.status != "ACTIVE":
        return _error("KB_NOT_ACTIVE", f"knowledge base '{kb_id}' status is '{kb.status}'")

    start = time.perf_counter()

    query_vector = _embedder.embed(query_text)
    hits = _vector_store.search(query_vector, top_k=top_k)

    results = [
        SearchResult(doc_id=vid, chunk_text=meta.get("text", ""), score=round(score, 6))
        for vid, score, meta in hits
    ]

    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    return {"results": results, "latency_ms": latency_ms}


# ── Internal helpers ─────────────────────────────────────────────────────────


def _chunk_text(text: str) -> list[str]:
    """Split *text* into chunks by blank-line-separated paragraphs."""
    parts = text.split("\n\n")
    return [p.strip() for p in parts if p.strip()]
