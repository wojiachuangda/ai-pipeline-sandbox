"""Shared test fixtures."""

from __future__ import annotations

import pytest

from sandbox_app.kb.service import reset as kb_reset


@pytest.fixture(autouse=True)
def _clear_kb_store() -> None:
    """Automatically reset kb stores before every test."""
    kb_reset()
