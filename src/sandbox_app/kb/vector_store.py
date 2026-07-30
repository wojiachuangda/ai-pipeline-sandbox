"""In-memory vector store backed by a dict — cosine-similarity search, zero deps."""

from __future__ import annotations


class InMemoryVectorStore:
    """Dict-backed vector store with cosine-similarity nearest-neighbour search."""

    def __init__(self) -> None:
        self._vectors: dict[str, list[float]] = {}
        self._metadata: dict[str, dict] = {}

    def add(self, id: str, vector: list[float], metadata: dict) -> None:
        """Store a vector and its metadata under *id*."""
        self._vectors[id] = vector
        self._metadata[id] = metadata

    def search(
        self, query_vector: list[float], top_k: int = 5
    ) -> list[tuple[str, float, dict]]:
        """Return up to *top_k* results as ``(id, score, metadata)`` sorted by
        cosine similarity descending.
        """
        scores: list[tuple[str, float, dict]] = []
        for vid, vec in self._vectors.items():
            score = _cosine_similarity(query_vector, vec)
            scores.append((vid, score, self._metadata[vid]))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def clear(self) -> None:
        """Remove all entries (used for test isolation)."""
        self._vectors.clear()
        self._metadata.clear()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(ai * bi for ai, bi in zip(a, b))
    norm_a = sum(ai * ai for ai in a) ** 0.5
    norm_b = sum(bi * bi for bi in b) ** 0.5
    denom = norm_a * norm_b
    if denom == 0:
        return 0.0
    return dot / denom
