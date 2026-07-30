"""Domain models and in-memory repositories for workflows, versions, and templates.

Every repository is a process‑local dict so the module has zero external
dependencies beyond the standard library.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .dsl import WorkflowDsl
from .errors import (
    TemplateNotFoundError,
    VersionNotFoundError,
    WorkflowNotFoundError,
)

# ═══════════════════════════════════════════════════════════════════════
#  Workflow
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class Workflow:
    """A named, versioned workflow definition."""

    id: str
    name: str
    description: str
    dsl: WorkflowDsl
    created_at: str
    updated_at: str
    current_version: int = 1


@dataclass
class _WorkflowRow:
    """Internal storage row (mutable so repos can update fields in place)."""

    id: str
    name: str
    description: str
    dsl: WorkflowDsl
    created_at: str
    updated_at: str
    current_version: int
    # versions are stored separately in _WorkflowVersionRow, keyed by workflow_id


class WorkflowRepository:
    """In-memory store for :class:`Workflow` entities."""

    def __init__(self) -> None:
        self._store: dict[str, _WorkflowRow] = {}

    # -- CRUD ---------------------------------------------------------------

    def create(
        self, name: str, description: str, dsl: WorkflowDsl
    ) -> Workflow:
        now = _utcnow()
        row = _WorkflowRow(
            id=uuid.uuid4().hex,
            name=name,
            description=description,
            dsl=dsl,
            created_at=now,
            updated_at=now,
            current_version=1,
        )
        self._store[row.id] = row
        return _to_workflow(row)

    def get(self, workflow_id: str) -> Workflow:
        row = self._store.get(workflow_id)
        if row is None:
            raise WorkflowNotFoundError(
                f"Workflow '{workflow_id}' not found."
            )
        return _to_workflow(row)

    def list(self) -> list[Workflow]:
        return [_to_workflow(r) for r in self._store.values()]

    def update(self, workflow_id: str, dsl: WorkflowDsl) -> Workflow:
        row = self._store.get(workflow_id)
        if row is None:
            raise WorkflowNotFoundError(
                f"Workflow '{workflow_id}' not found."
            )
        row.dsl = dsl
        row.updated_at = _utcnow()
        row.current_version += 1
        return _to_workflow(row)

    def set_dsl(self, workflow_id: str, dsl: WorkflowDsl) -> Workflow:
        """Replace the DSL *without* bumping the version counter (used during
        rollback, where the caller already manages version metadata)."""
        row = self._get_row(workflow_id)
        row.dsl = dsl
        row.updated_at = _utcnow()
        return _to_workflow(row)

    # -- Internal -----------------------------------------------------------

    def _get_row(self, workflow_id: str) -> _WorkflowRow:
        row = self._store.get(workflow_id)
        if row is None:
            raise WorkflowNotFoundError(
                f"Workflow '{workflow_id}' not found."
            )
        return row

    def _set_current_version(self, workflow_id: str, version: int) -> None:
        self._get_row(workflow_id).current_version = version


# ═══════════════════════════════════════════════════════════════════════
#  WorkflowVersion
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class WorkflowVersion:
    """A point-in-time snapshot of a workflow's DSL (aligns with Agent
    version semantics)."""

    id: str
    workflow_id: str
    version_number: int
    dsl: WorkflowDsl
    created_at: str
    label: str


class WorkflowVersionRepository:
    """In-memory store for :class:`WorkflowVersion` snapshots."""

    def __init__(self) -> None:
        self._store: dict[str, list[_VersionRow]] = {}  # workflow_id → rows

    # -- API ----------------------------------------------------------------

    def create_version(
        self,
        workflow_id: str,
        dsl: WorkflowDsl,
        *,
        label: str = "",
    ) -> WorkflowVersion:
        rows = self._store.setdefault(workflow_id, [])
        version_number = len(rows) + 1
        now = _utcnow()
        row = _VersionRow(
            id=uuid.uuid4().hex,
            workflow_id=workflow_id,
            version_number=version_number,
            dsl=dsl,
            created_at=now,
            label=label,
        )
        rows.append(row)
        return _to_version(row)

    def list_versions(self, workflow_id: str) -> list[WorkflowVersion]:
        return sorted(
            [_to_version(r) for r in self._store.get(workflow_id, [])],
            key=lambda v: v.version_number,
        )

    def get_version(
        self, workflow_id: str, version_number: int
    ) -> WorkflowVersion:
        for r in self._store.get(workflow_id, []):
            if r.version_number == version_number:
                return _to_version(r)
        raise VersionNotFoundError(
            f"Version {version_number} not found for workflow '{workflow_id}'."
        )

    def get_latest_version(self, workflow_id: str) -> WorkflowVersion | None:
        rows = self._store.get(workflow_id, [])
        if not rows:
            return None
        return _to_version(rows[-1])


# ═══════════════════════════════════════════════════════════════════════
#  WorkflowTemplate
# ═══════════════════════════════════════════════════════════════════════

_VISIBILITY_VALUES = frozenset({"PRIVATE", "TENANT"})


@dataclass
class WorkflowTemplate:
    """A reusable workflow blueprint scoped to a visibility level."""

    id: str
    name: str
    description: str
    dsl: WorkflowDsl
    visibility: str  # "PRIVATE" | "TENANT"
    source_workflow_id: str
    created_at: str


class WorkflowTemplateRepository:
    """In-memory store for :class:`WorkflowTemplate` entities."""

    def __init__(self) -> None:
        self._store: dict[str, _TemplateRow] = {}

    # -- API ----------------------------------------------------------------

    def save_template(
        self,
        name: str,
        description: str,
        dsl: WorkflowDsl,
        visibility: str,
        source_workflow_id: str,
    ) -> WorkflowTemplate:
        if visibility not in _VISIBILITY_VALUES:
            raise ValueError(
                f"visibility must be 'PRIVATE' or 'TENANT', got '{visibility}'."
            )
        row = _TemplateRow(
            id=uuid.uuid4().hex,
            name=name,
            description=description,
            dsl=dsl,
            visibility=visibility,
            source_workflow_id=source_workflow_id,
            created_at=_utcnow(),
        )
        self._store[row.id] = row
        return _to_template(row)

    def get_template(self, template_id: str) -> WorkflowTemplate:
        row = self._store.get(template_id)
        if row is None:
            raise TemplateNotFoundError(
                f"Template '{template_id}' not found."
            )
        return _to_template(row)

    def list_templates(
        self, visibility: str | None = None
    ) -> list[WorkflowTemplate]:
        results = list(self._store.values())
        if visibility is not None:
            results = [r for r in results if r.visibility == visibility]
        return [_to_template(r) for r in results]


# ═══════════════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════════════


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _VersionRow:
    id: str
    workflow_id: str
    version_number: int
    dsl: WorkflowDsl
    created_at: str
    label: str


@dataclass
class _TemplateRow:
    id: str
    name: str
    description: str
    dsl: WorkflowDsl
    visibility: str
    source_workflow_id: str
    created_at: str


def _to_workflow(r: _WorkflowRow) -> Workflow:
    return Workflow(
        id=r.id,
        name=r.name,
        description=r.description,
        dsl=r.dsl,
        created_at=r.created_at,
        updated_at=r.updated_at,
        current_version=r.current_version,
    )


def _to_version(r: _VersionRow) -> WorkflowVersion:
    return WorkflowVersion(
        id=r.id,
        workflow_id=r.workflow_id,
        version_number=r.version_number,
        dsl=r.dsl,
        created_at=r.created_at,
        label=r.label,
    )


def _to_template(r: _TemplateRow) -> WorkflowTemplate:
    return WorkflowTemplate(
        id=r.id,
        name=r.name,
        description=r.description,
        dsl=r.dsl,
        visibility=r.visibility,
        source_workflow_id=r.source_workflow_id,
        created_at=r.created_at,
    )
