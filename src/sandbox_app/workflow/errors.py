"""Workflow error types.

Each error maps to a specific failure mode in the workflow DSL lifecycle.
"""

from __future__ import annotations


class WorkflowError(Exception):
    """Base exception for all workflow-related errors."""


class InvalidWorkflowDslError(WorkflowError):
    """Raised when the DSL definition fails structural or semantic validation.

    Corresponds to error code INVALID_WORKFLOW_DSL.
    """


class CircularWorkflowError(WorkflowError):
    """Raised when a cycle is detected in a workflow graph that has no loop-control node.

    Corresponds to error code CIRCULAR_WORKFLOW.
    """


class WorkflowNotFoundError(WorkflowError):
    """Raised when a workflow with the given ID does not exist."""


class VersionNotFoundError(WorkflowError):
    """Raised when a workflow version with the given number does not exist."""


class TemplateNotFoundError(WorkflowError):
    """Raised when a template with the given ID does not exist."""
