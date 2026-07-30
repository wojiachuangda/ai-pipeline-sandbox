"""Shared test fixtures."""

import pytest

from sandbox_app.store import reset


@pytest.fixture(autouse=True)
def _clear_store() -> None:
    """Reset the in-memory task store before each test for isolation."""
    reset()
