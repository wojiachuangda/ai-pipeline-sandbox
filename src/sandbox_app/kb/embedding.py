"""Fake embedder — deterministic hash-based pseudo-vectors, zero external deps."""

from __future__ import annotations


class FakeEmbedder:
    """Deterministic hash-based embedder for testing without real NLP models."""

    def __init__(self, dim: int = 128) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        """Produce a deterministic pseudo-vector from *text*.

        Each character contributes a sinusoidal component scaled by its ordinal
        and position.  Same text → same vector; different texts → different vectors.
        Values are normalised to [-1, 1].
        """
        vec = [0.0] * self.dim
        n = len(text)
        if n == 0:
            return vec
        for i, ch in enumerate(text):
            seed = ord(ch) + i * 31
            idx = (seed * 2654435761) % self.dim  # Knuth multiplicative hash
            val = (seed % 10000) / 5000.0 - 1.0  # map to [-1, 1]
            vec[idx] += val
        # Normalise to unit length (avoid division by zero)
        norm_sq = sum(v * v for v in vec)
        if norm_sq > 0:
            scale = n / (norm_sq**0.5)
            vec = [v * scale for v in vec]
        return vec
