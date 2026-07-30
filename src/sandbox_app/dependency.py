"""Task dependency graph with cycle detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DependencyType = Literal["NONE", "SEQUENTIAL", "AND_PARALLEL", "OR_PARALLEL"]


class CircularDependencyError(Exception):
    """Raised when adding a dependency would create a cycle."""

    def __init__(self, chain: list[str]) -> None:
        self.chain = chain
        super().__init__(f"Circular dependency detected: {' -> '.join(chain)}")


@dataclass
class DependencyGraph:
    type: DependencyType = "NONE"
    depends_on: list[str] = field(default_factory=list)

    def add_dependency(self, task_id: str, store_adjacency: dict[str, list[str]]) -> None:
        """Add *task_id* as a dependency and detect cycles."""
        self.depends_on.append(task_id)
        if _has_cycle(store_adjacency):
            self.depends_on.pop()
            raise CircularDependencyError(_find_cycle(store_adjacency))


def _has_cycle(adjacency: dict[str, list[str]]) -> bool:
    """Return True if *adjacency* contains a directed cycle (DFS)."""
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> bool:
        visiting.add(node)
        for neighbor in adjacency.get(node, []):
            if neighbor in visiting:
                return True
            if neighbor not in visited and dfs(neighbor):
                return True
        visiting.discard(node)
        visited.add(node)
        return False

    return any(node not in visited and dfs(node) for node in adjacency)


def _find_cycle(adjacency: dict[str, list[str]]) -> list[str]:
    """Return one cycle path as a list of node ids (for error reporting)."""
    visiting: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> list[str] | None:
        visiting.add(node)
        path.append(node)
        for neighbor in adjacency.get(node, []):
            if neighbor in visiting:
                idx = path.index(neighbor)
                path.append(neighbor)
                return path[idx:]
            result = dfs(neighbor)
            if result is not None:
                return result
        path.pop()
        visiting.discard(node)
        return None

    for node in adjacency:
        result = dfs(node)
        if result is not None:
            return result
    return []
