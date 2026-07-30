"""Tests for knowledge base registration, import, search, and embedder determinism.

Covers AC-1 through AC-5.
"""

from __future__ import annotations

from sandbox_app.kb import (
    FakeEmbedder,
    InMemoryVectorStore,
    import_documents,
    register_kb,
    search,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

VALID_KB_ARGS = ("test-kb", "fake-embedding/v1", "fixed-size-256", {"type": "in_memory", "dim": 128})


def _prepare_active_kb(tmp_path, content: str = "Hello world\n\nThis is a test document."):
    """Register a KB, write a temp file, import it, return (kb, job)."""
    kb = register_kb(*VALID_KB_ARGS)
    doc = tmp_path / "doc.txt"
    doc.write_text(content, encoding="utf-8")
    job = import_documents(kb.id, "FILE", str(doc))
    return kb, job


# ═══════════════════════════════════════════════════════════════════════════════
# AC-1: 注册知识库
# ═══════════════════════════════════════════════════════════════════════════════


def test_register_kb_returns_initialized():
    kb = register_kb(*VALID_KB_ARGS)
    assert kb.status == "INITIALIZED"
    assert kb.name == "test-kb"
    assert kb.embedding_model == "fake-embedding/v1"
    assert kb.chunk_strategy == "fixed-size-256"
    assert kb.vector_db_config["type"] == "in_memory"


def test_register_kb_generates_unique_id():
    kb1 = register_kb("a", "m1", "s1", {})
    kb2 = register_kb("b", "m2", "s2", {})
    assert kb1.id != kb2.id


def test_register_kb_default_status_is_initialized():
    kb = register_kb("x", "y", "z", {})
    assert kb.status == "INITIALIZED"


# ═══════════════════════════════════════════════════════════════════════════════
# AC-2: 文档导入
# ═══════════════════════════════════════════════════════════════════════════════


def test_import_documents_file_source(tmp_path):
    kb = register_kb(*VALID_KB_ARGS)
    doc = tmp_path / "notes.txt"
    doc.write_text("Chunk A\n\nChunk B\n\nChunk C", encoding="utf-8")

    job = import_documents(kb.id, "FILE", str(doc))

    assert job.source_type == "FILE"
    assert job.status == "COMPLETED"


def test_import_documents_transitions_kb_to_active(tmp_path):
    kb, _ = _prepare_active_kb(tmp_path)
    assert kb.status == "ACTIVE"


def test_import_documents_nonexistent_kb():
    result = import_documents("nonexistent", "FILE", "/x.txt")
    assert result["code"] == "KB_NOT_FOUND"


def test_import_documents_unsupported_source_type():
    kb = register_kb(*VALID_KB_ARGS)
    result = import_documents(kb.id, "URL", "https://example.com/doc.txt")
    assert result["code"] == "UNSUPPORTED_SOURCE_TYPE"


def test_import_documents_missing_file():
    kb = register_kb(*VALID_KB_ARGS)
    result = import_documents(kb.id, "FILE", "/nonexistent/path.txt")
    assert result["code"] == "FILE_READ_ERROR"


def test_import_documents_empty_file_becomes_single_chunk(tmp_path):
    kb = register_kb(*VALID_KB_ARGS)
    doc = tmp_path / "empty.txt"
    doc.write_text("", encoding="utf-8")
    job = import_documents(kb.id, "FILE", str(doc))
    # Should complete without error; empty file gets a sentinel chunk
    assert job.status == "COMPLETED"


def test_import_documents_creates_multiple_chunks(tmp_path):
    kb = register_kb(*VALID_KB_ARGS)
    doc = tmp_path / "multi.txt"
    doc.write_text("A\n\nB\n\nC\n\nD\n\nE", encoding="utf-8")

    job = import_documents(kb.id, "FILE", str(doc))
    assert job.status == "COMPLETED"
    # 5 chunks should be present in search
    resp = search(kb.id, "something")
    assert len(resp["results"]) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# AC-3: 检索测试 API
# ═══════════════════════════════════════════════════════════════════════════════


def test_search_returns_results_sorted_by_score(tmp_path):
    kb = register_kb(*VALID_KB_ARGS)
    doc = tmp_path / "doc.txt"
    # Write paragraphs so the embedder produces different vectors
    doc.write_text(
        "The quick brown fox jumps over the lazy dog\n\n"
        "Python is a great programming language\n\n"
        "Machine learning is transforming the world\n\n"
        "Knowledge bases store structured information",
        encoding="utf-8",
    )
    import_documents(kb.id, "FILE", str(doc))

    resp = search(kb.id, "machine learning and python programming")

    assert "results" in resp
    assert "latency_ms" in resp
    assert resp["latency_ms"] >= 0

    results = resp["results"]
    assert len(results) > 0

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True), "results must be sorted by score desc"


def test_search_respects_top_k(tmp_path):
    kb = register_kb(*VALID_KB_ARGS)
    doc = tmp_path / "doc.txt"
    doc.write_text("A\n\nB\n\nC\n\nD\n\nE", encoding="utf-8")
    import_documents(kb.id, "FILE", str(doc))

    resp = search(kb.id, "query", top_k=3)
    assert len(resp["results"]) == 3


def test_search_unactivated_kb_returns_error():
    kb = register_kb(*VALID_KB_ARGS)  # never imported → stays INITIALIZED
    resp = search(kb.id, "query")
    assert resp["code"] == "KB_NOT_ACTIVE"


def test_search_nonexistent_kb():
    resp = search("nonexistent", "query")
    assert resp["code"] == "KB_NOT_FOUND"


def test_search_latency_ms_is_positive(tmp_path):
    kb, _ = _prepare_active_kb(tmp_path)
    resp = search(kb.id, "test")
    assert resp["latency_ms"] >= 0


def test_search_result_structure(tmp_path):
    kb = register_kb(*VALID_KB_ARGS)
    doc = tmp_path / "doc.txt"
    doc.write_text("First chunk content", encoding="utf-8")
    import_documents(kb.id, "FILE", str(doc))

    resp = search(kb.id, "First")
    assert len(resp["results"]) >= 1
    r = resp["results"][0]
    assert r.doc_id != ""
    assert isinstance(r.chunk_text, str)
    assert isinstance(r.score, float)


# ═══════════════════════════════════════════════════════════════════════════════
# AC-4: 内存向量/假 embedding
# ═══════════════════════════════════════════════════════════════════════════════


def test_fake_embedder_deterministic():
    e = FakeEmbedder(dim=64)
    v1 = e.embed("hello")
    v2 = e.embed("hello")
    assert v1 == v2


def test_fake_embedder_different_texts_different_vectors():
    e = FakeEmbedder(dim=64)
    v1 = e.embed("hello")
    v2 = e.embed("world")
    assert v1 != v2


def test_fake_embedder_correct_dimension():
    e = FakeEmbedder(dim=37)
    v = e.embed("anything")
    assert len(v) == 37


def test_fake_embedder_empty_string_returns_zero_vector():
    e = FakeEmbedder(dim=16)
    v = e.embed("")
    assert v == [0.0] * 16


def test_vector_store_search_returns_correct_order():
    store = InMemoryVectorStore()
    store.add("a", [1.0, 0.0], {"text": "aligned"})
    store.add("b", [0.0, 1.0], {"text": "orthogonal"})
    results = store.search([1.0, 0.0], top_k=2)
    assert results[0][0] == "a"  # highest cosine sim
    assert results[0][1] > results[1][1]  # scores descending


def test_vector_store_top_k_limit():
    store = InMemoryVectorStore()
    for i in range(10):
        store.add(str(i), [float(i), 0.0], {"idx": i})
    results = store.search([5.0, 0.0], top_k=3)
    assert len(results) == 3


def test_vector_store_clear():
    store = InMemoryVectorStore()
    store.add("x", [1.0, 0.0], {})
    store.clear()
    results = store.search([1.0, 0.0])
    assert results == []


def test_vector_store_metadata_preserved():
    store = InMemoryVectorStore()
    store.add("id1", [1.0, 0.0], {"text": "hello"})
    results = store.search([1.0, 0.0], top_k=1)
    assert results[0][2]["text"] == "hello"


# ═══════════════════════════════════════════════════════════════════════════════
# AC-5: 测试覆盖 — integration / edge cases
# ═══════════════════════════════════════════════════════════════════════════════


def test_full_pipeline_register_import_search(tmp_path):
    """End-to-end: register → import → search and verify reasonable results."""
    kb = register_kb("demo-kb", "fake-embed/v1", "para-split", {})
    assert kb.status == "INITIALIZED"

    doc = tmp_path / "demo.txt"
    doc.write_text(
        "Cats are small furry animals\n\n"
        "Dogs are loyal companions\n\n"
        "Birds can fly in the sky\n\n"
        "Fish swim in the water",
        encoding="utf-8",
    )
    job = import_documents(kb.id, "FILE", str(doc))
    assert job.status == "COMPLETED"
    assert kb.status == "ACTIVE"

    resp = search(kb.id, "animals and pets")
    assert len(resp["results"]) > 0
    assert resp["latency_ms"] >= 0


def test_stores_are_isolated_between_tests():
    """Conftest autouse reset should guarantee clean state."""
    # If previous tests leaked state these calls would find unexpected data
    kb = register_kb("iso", "m", "s", {})
    # No import done → searching should return KB_NOT_ACTIVE
    resp = search(kb.id, "anything")
    assert resp["code"] == "KB_NOT_ACTIVE"
