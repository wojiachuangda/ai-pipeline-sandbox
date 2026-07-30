"""Workflow DSL — node / edge / graph definitions, validation, and cycle detection.

The DSL is expressed as pure Python dataclasses that can be parsed from JSON-
compatible dicts.  No third-party dependencies are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import CircularWorkflowError, InvalidWorkflowDslError

# ---------------------------------------------------------------------------
# Node / Edge definitions
# ---------------------------------------------------------------------------

_VALID_NODE_TYPES = frozenset({"start", "end", "task", "decision", "loop"})
"""Recognised node types.  ``loop`` is the only type that exempts a node from
cycle detection (it represents an explicit loop-control construct)."""


@dataclass
class NodeDef:
    """A single node inside a workflow graph."""

    id: str
    type: str
    label: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise InvalidWorkflowDslError("Node id must not be empty.")
        if self.type not in _VALID_NODE_TYPES:
            raise InvalidWorkflowDslError(
                f"Unknown node type '{self.type}' for node '{self.id}'. "
                f"Valid types: {sorted(_VALID_NODE_TYPES)}"
            )


@dataclass
class EdgeDef:
    """A directed edge connecting two nodes."""

    source: str
    target: str


# ---------------------------------------------------------------------------
# Graph container
# ---------------------------------------------------------------------------


@dataclass
class WorkflowDsl:
    """Validated workflow graph definition.

    A valid DSL MUST:
    * contain at least one node
    * have exactly one ``start`` node
    * have at least one ``end`` node
    * reference only existing node IDs in every edge
    * be free of cycles unless a ``loop`` node is on the cycle
    """

    nodes: list[NodeDef] = field(default_factory=list)
    edges: list[EdgeDef] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowDsl:
        """Parse a JSON-compatible dict into a validated ``WorkflowDsl``."""
        raw_nodes: list[dict[str, Any]] = data.get("nodes", [])
        raw_edges: list[dict[str, Any]] = data.get("edges", [])

        if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
            raise InvalidWorkflowDslError("DSL requires 'nodes' (list) and 'edges' (list).")

        nodes = [_node_from_dict(n) for n in raw_nodes]
        edges = [_edge_from_dict(e) for e in raw_edges]
        instance = cls(nodes=nodes, edges=edges)
        instance.validate()
        return instance

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Run all structural / semantic checks.

        Raises:
            InvalidWorkflowDslError: on structural failures.
            CircularWorkflowError: when a disallowed cycle is detected.
        """
        self._validate_nodes()
        self._validate_edges()
        self._detect_cycles()

    def _validate_nodes(self) -> None:
        if not self.nodes:
            raise InvalidWorkflowDslError("Workflow must contain at least 1 node.")

        node_ids = {n.id for n in self.nodes}
        start_nodes = [n for n in self.nodes if n.type == "start"]
        end_nodes = [n for n in self.nodes if n.type == "end"]

        if len(start_nodes) != 1:
            raise InvalidWorkflowDslError(
                f"Workflow must have exactly 1 'start' node; found {len(start_nodes)}."
            )
        if not end_nodes:
            raise InvalidWorkflowDslError("Workflow must have at least 1 'end' node.")

        if len(node_ids) != len(self.nodes):
            raise InvalidWorkflowDslError("Duplicate node IDs detected.")

    def _validate_edges(self) -> None:
        node_ids = {n.id for n in self.nodes}

        for i, edge in enumerate(self.edges):
            if edge.source not in node_ids:
                raise InvalidWorkflowDslError(
                    f"Edge[{i}]: source '{edge.source}' references an unknown node."
                )
            if edge.target not in node_ids:
                raise InvalidWorkflowDslError(
                    f"Edge[{i}]: target '{edge.target}' references an unknown node."
                )

    # ------------------------------------------------------------------
    # Cycle detection (DFS three-colour)
    # ------------------------------------------------------------------

    def _detect_cycles(self) -> None:
        """Run DFS-based cycle detection, exempting edges that enter a ``loop`` node.

        Raises:
            CircularWorkflowError: when a cycle is found in the non-exempt sub-graph.
        """
        exempt_ids = {n.id for n in self.nodes if n.type == "loop"}

        # Build adjacency list, skipping edges whose *target* is exempt.
        adj: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for edge in self.edges:
            if edge.target in exempt_ids:
                continue
            adj[edge.source].append(edge.target)

        # Three-colour DFS
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {n.id: WHITE for n in self.nodes}

        def _dfs(v: str) -> None:
            color[v] = GRAY
            for neighbor in adj.get(v, []):
                if color[neighbor] == GRAY:
                    raise CircularWorkflowError(
                        f"Cycle detected: back-edge from '{v}' to '{neighbor}'."
                    )
                if color[neighbor] == WHITE:
                    _dfs(neighbor)
            color[v] = BLACK

        for node in self.nodes:
            if color[node.id] == WHITE:
                _dfs(node.id)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Export the DSL back to a JSON-compatible dict.

        Only includes ``label`` on nodes when the value is non-empty, matching
        the input convention so that round-trips are exact.
        """
        nodes: list[dict[str, Any]] = []
        for n in self.nodes:
            d: dict[str, Any] = {"id": n.id, "type": n.type}
            if n.label:
                d["label"] = n.label
            nodes.append(d)
        return {
            "nodes": nodes,
            "edges": [{"source": e.source, "target": e.target} for e in self.edges],
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _node_from_dict(d: dict[str, Any]) -> NodeDef:
    if not isinstance(d, dict):
        raise InvalidWorkflowDslError("Each node must be a JSON object.")
    if "id" not in d or "type" not in d:
        raise InvalidWorkflowDslError("Each node requires 'id' and 'type' fields.")
    return NodeDef(id=d["id"], type=d["type"], label=d.get("label", ""))


def _edge_from_dict(d: dict[str, Any]) -> EdgeDef:
    if not isinstance(d, dict):
        raise InvalidWorkflowDslError("Each edge must be a JSON object.")
    if "source" not in d or "target" not in d:
        raise InvalidWorkflowDslError("Each edge requires 'source' and 'target' fields.")
    return EdgeDef(source=d["source"], target=d["target"])
