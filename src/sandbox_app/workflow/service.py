"""Workflow service — CRUD orchestration, version management, and templates.

This module ties together DSL parsing/validation, domain models, and
in-memory repositories.  Every public function is a stand-alone business
operation that can be called directly from test or application code.
"""

from __future__ import annotations

from typing import Any

from .dsl import WorkflowDsl
# Error types are used indirectly via the repo methods called below.
from .errors import (  # noqa: F401
    InvalidWorkflowDslError,
    VersionNotFoundError,
    WorkflowNotFoundError,
)
from .models import (
    Workflow,
    WorkflowRepository,
    WorkflowTemplate,
    WorkflowTemplateRepository,
    WorkflowVersion,
    WorkflowVersionRepository,
)

# ═══════════════════════════════════════════════════════════════════════
#  Singleton repositories (process‑local)
# ═══════════════════════════════════════════════════════════════════════

_workflow_repo = WorkflowRepository()
_version_repo = WorkflowVersionRepository()
_template_repo = WorkflowTemplateRepository()


# ═══════════════════════════════════════════════════════════════════════
#  Workflow CRUD
# ═══════════════════════════════════════════════════════════════════════


def create_workflow(
    dsl_dict: dict[str, Any],
    name: str = "",
    description: str = "",
) -> Workflow:
    """Parse and validate *dsl_dict*, then persist a new workflow with an
    initial version (v1).

    Returns:
        Workflow: the newly created workflow.

    Raises:
        InvalidWorkflowDslError: if the DSL is structurally invalid.
        CircularWorkflowError: if a disallowed cycle is detected.
    """
    dsl = WorkflowDsl.from_dict(dsl_dict)
    workflow = _workflow_repo.create(name=name, description=description, dsl=dsl)
    _version_repo.create_version(
        workflow_id=workflow.id, dsl=dsl, label="Initial version"
    )
    return workflow


def get_workflow(workflow_id: str) -> Workflow:
    """Return the workflow identified by *workflow_id*.

    Raises:
        WorkflowNotFoundError: if no such workflow exists.
    """
    return _workflow_repo.get(workflow_id)


def list_workflows() -> list[Workflow]:
    """Return every workflow in the store."""
    return _workflow_repo.list()


def update_workflow(
    workflow_id: str,
    dsl_dict: dict[str, Any],
) -> Workflow:
    """Validate *dsl_dict* and update the workflow's current DSL, creating a
    new version snapshot automatically.

    The version number is incremented by the repository layer; this function
    also records the version snapshot so it appears in the history.

    Returns:
        Workflow: the updated workflow.

    Raises:
        WorkflowNotFoundError: if *workflow_id* does not exist.
        InvalidWorkflowDslError: if the new DSL is invalid.
        CircularWorkflowError: if the new DSL contains a disallowed cycle.
    """
    dsl = WorkflowDsl.from_dict(dsl_dict)

    # Snapshot the *new* DSL at the next version number.
    current = _workflow_repo.get(workflow_id)
    next_version = current.current_version + 1

    workflow = _workflow_repo.update(workflow_id, dsl)
    _version_repo.create_version(
        workflow_id=workflow_id, dsl=dsl, label=f"Update to v{next_version}"
    )
    return workflow


# ═══════════════════════════════════════════════════════════════════════
#  Version management
# ═══════════════════════════════════════════════════════════════════════


def create_workflow_version(
    workflow_id: str,
    label: str = "",
) -> WorkflowVersion:
    """Take an explicit snapshot of the workflow's current DSL.

    This is useful for tagging named milestones (e.g. "before-refactor")
    without changing the DSL itself.
    """
    workflow = _workflow_repo.get(workflow_id)
    return _version_repo.create_version(
        workflow_id=workflow_id, dsl=workflow.dsl, label=label
    )


def list_workflow_versions(workflow_id: str) -> list[WorkflowVersion]:
    """Return all version snapshots for *workflow_id*, oldest first."""
    # Verify the workflow exists first.
    _workflow_repo.get(workflow_id)
    return _version_repo.list_versions(workflow_id)


def rollback_workflow(
    workflow_id: str,
    version_number: int,
) -> Workflow:
    """Restore the workflow's current DSL to the snapshot captured at
    *version_number*, then record a new version so the rollback itself is
    an auditable event.

    Returns:
        Workflow: the workflow after rollback.

    Raises:
        WorkflowNotFoundError: if *workflow_id* does not exist.
        VersionNotFoundError: if *version_number* does not exist.
    """
    # Verify both entities exist.
    _workflow_repo.get(workflow_id)
    target = _version_repo.get_version(workflow_id, version_number)

    # Replace the DSL *without* bumping the counter yet — we'll bump
    # explicitly through a new version snapshot.
    _workflow_repo.set_dsl(workflow_id, target.dsl)

    # Create a new version to record the rollback.
    new_version = _version_repo.create_version(
        workflow_id=workflow_id,
        dsl=target.dsl,
        label=f"Rollback to v{version_number}",
    )
    _workflow_repo._set_current_version(workflow_id, new_version.version_number)

    return _workflow_repo.get(workflow_id)


# ═══════════════════════════════════════════════════════════════════════
#  Templates
# ═══════════════════════════════════════════════════════════════════════


def save_as_template(
    workflow_id: str,
    template_name: str,
    visibility: str = "PRIVATE",
) -> WorkflowTemplate:
    """Snapshot the current DSL of *workflow_id* as a reusable template.

    Args:
        workflow_id: source workflow.
        template_name: display name for the template.
        visibility: ``"PRIVATE"`` (default) or ``"TENANT"``.

    Returns:
        WorkflowTemplate: the saved template.

    Raises:
        WorkflowNotFoundError: if *workflow_id* does not exist.
        ValueError: if *visibility* is not ``PRIVATE`` or ``TENANT``.
    """
    workflow = _workflow_repo.get(workflow_id)
    return _template_repo.save_template(
        name=template_name,
        description=workflow.description,
        dsl=workflow.dsl,
        visibility=visibility,
        source_workflow_id=workflow_id,
    )


def list_templates(
    visibility: str | None = None,
) -> list[WorkflowTemplate]:
    """Return templates, optionally filtered by *visibility*."""
    return _template_repo.list_templates(visibility)


def get_template(template_id: str) -> WorkflowTemplate:
    """Return a single template by ID.

    Raises:
        TemplateNotFoundError: if *template_id* does not exist.
    """
    return _template_repo.get_template(template_id)
