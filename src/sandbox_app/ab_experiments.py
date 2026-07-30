"""A/B experiment management — variants, metrics, and lifecycle."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExperimentStatus(Enum):
    """Legal statuses for an A/B experiment."""

    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


# Allowed transitions
_TRANSITIONS: dict[ExperimentStatus, set[ExperimentStatus]] = {
    ExperimentStatus.SCHEDULED:  {ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED},
    ExperimentStatus.RUNNING:    {ExperimentStatus.COMPLETED, ExperimentStatus.CANCELLED},
    ExperimentStatus.COMPLETED:  set(),   # terminal
    ExperimentStatus.CANCELLED:  set(),   # terminal
}

# ---------------------------------------------------------------------------
# Valid metrics — the only metric names accepted by create()
# ---------------------------------------------------------------------------

VALID_METRICS: set[str] = {
    "response_time",
    "token_usage",
    "user_rating",
    "conversion_rate",
}


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------

@dataclass
class Variant:
    """A treatment arm in an A/B experiment."""

    template_id: str
    weight: int          # percentage point, 0–100
    config: dict = field(default_factory=dict)


@dataclass
class Experiment:
    """An A/B experiment tracking variant performance."""

    name: str
    variants: list[Variant]
    metrics: list[str]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: ExperimentStatus = ExperimentStatus.SCHEDULED


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class ExperimentStore:
    """In-memory store for :class:`Experiment` objects with validation."""

    def __init__(self) -> None:
        self._experiments: dict[str, Experiment] = {}

    # -- Validation helpers --------------------------------------------------

    @staticmethod
    def _validate_variants(variants: list[Variant]) -> None:
        total = sum(v.weight for v in variants)
        if total != 100:
            raise ValueError(
                f"Variant weights must sum to 100, got {total}"
            )

    @staticmethod
    def _validate_metrics(metrics: list[str]) -> None:
        invalid = [m for m in metrics if m not in VALID_METRICS]
        if invalid:
            raise ValueError(
                f"Invalid metric(s): {', '.join(invalid)}. "
                f"Allowed: {', '.join(sorted(VALID_METRICS))}"
            )

    # -- CRUD ----------------------------------------------------------------

    def create(
        self,
        name: str,
        variants: list[Variant],
        metrics: list[str],
    ) -> Experiment:
        """Create and store an experiment.

        Raises :exc:`ValueError` when:
        - variant weights do not sum to 100
        - any metric is not in :data:`VALID_METRICS`
        """
        self._validate_variants(variants)
        self._validate_metrics(metrics)
        exp = Experiment(name=name, variants=variants, metrics=metrics)
        self._experiments[exp.id] = exp
        return exp

    def get(self, experiment_id: str) -> Experiment | None:
        """Return the experiment with *experiment_id*, or *None*."""
        return self._experiments.get(experiment_id)

    def list(self) -> list[Experiment]:
        """Return all experiments."""
        return list(self._experiments.values())

    # -- Lifecycle -----------------------------------------------------------

    def update_status(self, experiment_id: str, new_status: ExperimentStatus) -> Experiment:
        """Transition *experiment_id* to *new_status*.

        Raises :exc:`ValueError` for illegal transitions, :exc:`LookupError`
        when the experiment does not exist.
        """
        exp = self._experiments.get(experiment_id)
        if exp is None:
            raise LookupError(f"Experiment '{experiment_id}' not found")

        allowed = _TRANSITIONS.get(exp.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from {exp.status.value} to {new_status.value}"
            )
        exp.status = new_status
        return exp
