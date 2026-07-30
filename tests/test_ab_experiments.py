"""Tests for A/B experiment CRUD, validation, and lifecycle."""

import pytest

from sandbox_app import (
    Experiment,
    ExperimentStatus,
    ExperimentStore,
    VALID_METRICS,
    Variant,
)


# ---------------------------------------------------------------------------
# AC-4: Experiment creation & validation
# ---------------------------------------------------------------------------

class TestCreateExperiment:
    """AC-4: Variant weights must sum to 100; metrics must be in VALID_METRICS."""

    def test_create_experiment_success(self) -> None:
        store = ExperimentStore()
        exp = store.create(
            name="summarization-style",
            variants=[
                Variant(template_id="t1", weight=70),
                Variant(template_id="t2", weight=30),
            ],
            metrics=["response_time", "user_rating"],
        )
        assert exp.id
        assert exp.name == "summarization-style"
        assert exp.status == ExperimentStatus.SCHEDULED
        assert len(exp.variants) == 2

    def test_create_fails_on_weight_not_100(self) -> None:
        store = ExperimentStore()
        with pytest.raises(ValueError, match="must sum to 100"):
            store.create(
                name="bad-weights",
                variants=[
                    Variant(template_id="t1", weight=60),
                    Variant(template_id="t2", weight=30),
                ],
                metrics=["response_time"],
            )

    def test_create_fails_on_invalid_metric(self) -> None:
        store = ExperimentStore()
        with pytest.raises(ValueError, match="Invalid metric"):
            store.create(
                name="bad-metric",
                variants=[
                    Variant(template_id="t1", weight=50),
                    Variant(template_id="t2", weight=50),
                ],
                metrics=["fantasy_metric"],
            )


# ---------------------------------------------------------------------------
# AC-4: Status lifecycle
# ---------------------------------------------------------------------------

class TestStatusLifecycle:
    """AC-4: SCHEDULED → RUNNING → COMPLETED; invalid transitions rejected."""

    def test_valid_transitions(self) -> None:
        store = ExperimentStore()
        exp = store.create(
            name="lifecycle-test",
            variants=[Variant(template_id="t1", weight=100)],
            metrics=["token_usage"],
        )
        assert exp.status == ExperimentStatus.SCHEDULED

        exp = store.update_status(exp.id, ExperimentStatus.RUNNING)
        assert exp.status == ExperimentStatus.RUNNING

        exp = store.update_status(exp.id, ExperimentStatus.COMPLETED)
        assert exp.status == ExperimentStatus.COMPLETED

    def test_cancelled_from_scheduled(self) -> None:
        store = ExperimentStore()
        exp = store.create(
            name="cancel-test",
            variants=[Variant(template_id="t1", weight=100)],
            metrics=["conversion_rate"],
        )
        exp = store.update_status(exp.id, ExperimentStatus.CANCELLED)
        assert exp.status == ExperimentStatus.CANCELLED

    def test_cancelled_from_running(self) -> None:
        store = ExperimentStore()
        exp = store.create(
            name="cancel-running",
            variants=[Variant(template_id="t1", weight=100)],
            metrics=["response_time"],
        )
        store.update_status(exp.id, ExperimentStatus.RUNNING)
        exp = store.update_status(exp.id, ExperimentStatus.CANCELLED)
        assert exp.status == ExperimentStatus.CANCELLED

    def test_terminal_cannot_transition(self) -> None:
        store = ExperimentStore()
        exp = store.create(
            name="terminal-test",
            variants=[Variant(template_id="t1", weight=100)],
            metrics=["user_rating"],
        )
        store.update_status(exp.id, ExperimentStatus.RUNNING)
        store.update_status(exp.id, ExperimentStatus.COMPLETED)

        with pytest.raises(ValueError, match="Cannot transition"):
            store.update_status(exp.id, ExperimentStatus.RUNNING)

    def test_scheduled_cannot_jump_to_completed(self) -> None:
        store = ExperimentStore()
        exp = store.create(
            name="jump-test",
            variants=[Variant(template_id="t1", weight=100)],
            metrics=["token_usage"],
        )
        with pytest.raises(ValueError, match="Cannot transition"):
            store.update_status(exp.id, ExperimentStatus.COMPLETED)

    def test_update_nonexistent_raises(self) -> None:
        store = ExperimentStore()
        with pytest.raises(LookupError, match="not found"):
            store.update_status("nope", ExperimentStatus.RUNNING)


# ---------------------------------------------------------------------------
# Store operations
# ---------------------------------------------------------------------------

class TestExperimentStoreOps:
    """Basic store get/list."""

    def test_list_and_get(self) -> None:
        store = ExperimentStore()
        exp1 = store.create(
            name="e1",
            variants=[Variant(template_id="a", weight=100)],
            metrics=["response_time"],
        )
        exp2 = store.create(
            name="e2",
            variants=[Variant(template_id="b", weight=100)],
            metrics=["token_usage"],
        )
        all_exps = store.list()
        assert len(all_exps) == 2

        fetched = store.get(exp1.id)
        assert fetched is not None
        assert fetched.name == "e1"

    def test_get_missing_returns_none(self) -> None:
        store = ExperimentStore()
        assert store.get("bogus") is None


# ---------------------------------------------------------------------------
# VALID_METRICS integrity
# ---------------------------------------------------------------------------

class TestValidMetrics:
    """The VALID_METRICS set defines the accepted metric names."""

    def test_expected_metrics_present(self) -> None:
        assert "response_time" in VALID_METRICS
        assert "token_usage" in VALID_METRICS
        assert "user_rating" in VALID_METRICS
        assert "conversion_rate" in VALID_METRICS

    def test_rejects_random_strings(self) -> None:
        assert "nonsense" not in VALID_METRICS
