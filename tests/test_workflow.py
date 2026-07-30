"""Tests for the workflow DSL module.

Covers all acceptance criteria:
- AC-1: create / get / list workflows, DSL validation
- AC-2: cycle detection with/without loop nodes
- AC-3: version creation, listing, and rollback
- AC-4: template save & list (PRIVATE / TENANT)
- AC-5: test coverage across create, cycle, version, template
- AC-6: no UI — pure Python API + JSON DSL
"""

from __future__ import annotations

import pytest

from sandbox_app.workflow import (
    CircularWorkflowError,
    InvalidWorkflowDslError,
    TemplateNotFoundError,
    VersionNotFoundError,
    Workflow,
    WorkflowDsl,
    WorkflowNotFoundError,
    WorkflowTemplate,
    create_workflow,
    create_workflow_version,
    get_template,
    get_workflow,
    list_templates,
    list_workflow_versions,
    list_workflows,
    rollback_workflow,
    save_as_template,
    update_workflow,
)

# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════


def _valid_dsl() -> dict:
    """Return the smallest valid DSL (start → task → end)."""
    return {
        "nodes": [
            {"id": "n1", "type": "start"},
            {"id": "n2", "type": "task", "label": "处理步骤"},
            {"id": "n3", "type": "end"},
        ],
        "edges": [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
        ],
    }


def _dsl_with_decision() -> dict:
    """Valid DSL with a decision (branching) node."""
    return {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "d1", "type": "decision", "label": "审批?"},
            {"id": "task_a", "type": "task"},
            {"id": "task_b", "type": "task"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "d1"},
            {"source": "d1", "target": "task_a"},
            {"source": "d1", "target": "task_b"},
            {"source": "task_a", "target": "end"},
            {"source": "task_b", "target": "end"},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════
#  AC-1: create / get / list workflows & DSL validation
# ═══════════════════════════════════════════════════════════════════════


class TestCreateWorkflow:
    """Happy-path and error-path tests for workflow creation."""

    def test_create_with_valid_dsl(self) -> None:
        wf = create_workflow(_valid_dsl(), name="test", description="desc")
        assert isinstance(wf, Workflow)
        assert wf.name == "test"
        assert wf.description == "desc"
        assert wf.current_version == 1
        # DSL was persisted
        assert len(wf.dsl.nodes) == 3

    def test_create_auto_generates_id(self) -> None:
        wf = create_workflow(_valid_dsl())
        assert len(wf.id) == 32  # uuid4 hex

    def test_zero_nodes_raises(self) -> None:
        with pytest.raises(InvalidWorkflowDslError, match="at least 1 node"):
            create_workflow({"nodes": [], "edges": []})

    def test_no_start_node_raises(self) -> None:
        dsl = {
            "nodes": [
                {"id": "a", "type": "task"},
                {"id": "b", "type": "end"},
            ],
            "edges": [],
        }
        with pytest.raises(InvalidWorkflowDslError, match="exactly 1 'start'"):
            create_workflow(dsl)

    def test_multiple_start_nodes_raises(self) -> None:
        dsl = {
            "nodes": [
                {"id": "a", "type": "start"},
                {"id": "b", "type": "start"},
                {"id": "c", "type": "end"},
            ],
            "edges": [],
        }
        with pytest.raises(InvalidWorkflowDslError, match="exactly 1 'start'"):
            create_workflow(dsl)

    def test_no_end_node_raises(self) -> None:
        dsl = {
            "nodes": [
                {"id": "a", "type": "start"},
                {"id": "b", "type": "task"},
            ],
            "edges": [],
        }
        with pytest.raises(InvalidWorkflowDslError, match="at least 1 'end'"):
            create_workflow(dsl)

    def test_edge_references_unknown_source(self) -> None:
        dsl = {
            "nodes": [
                {"id": "n1", "type": "start"},
                {"id": "n2", "type": "end"},
            ],
            "edges": [{"source": "ghost", "target": "n2"}],
        }
        with pytest.raises(InvalidWorkflowDslError, match="unknown node"):
            create_workflow(dsl)

    def test_edge_references_unknown_target(self) -> None:
        dsl = {
            "nodes": [
                {"id": "n1", "type": "start"},
                {"id": "n2", "type": "end"},
            ],
            "edges": [{"source": "n1", "target": "ghost"}],
        }
        with pytest.raises(InvalidWorkflowDslError, match="unknown node"):
            create_workflow(dsl)

    def test_duplicate_node_ids_raises(self) -> None:
        dsl = {
            "nodes": [
                {"id": "n1", "type": "start"},
                {"id": "n1", "type": "end"},
            ],
            "edges": [],
        }
        with pytest.raises(InvalidWorkflowDslError, match="Duplicate node IDs"):
            create_workflow(dsl)

    def test_invalid_node_type_raises(self) -> None:
        dsl = {
            "nodes": [
                {"id": "n1", "type": "start"},
                {"id": "n2", "type": "magic"},
                {"id": "n3", "type": "end"},
            ],
            "edges": [],
        }
        with pytest.raises(InvalidWorkflowDslError, match="Unknown node type"):
            create_workflow(dsl)

    def test_missing_node_id_raises(self) -> None:
        with pytest.raises(InvalidWorkflowDslError, match="'id' and 'type'"):
            create_workflow({"nodes": [{"type": "start"}], "edges": []})

    def test_nodes_not_a_list(self) -> None:
        with pytest.raises(InvalidWorkflowDslError, match="'nodes' \\(list\\)"):
            create_workflow({"nodes": "bad", "edges": []})


class TestGetWorkflow:
    def test_get_existing(self) -> None:
        wf = create_workflow(_valid_dsl())
        fetched = get_workflow(wf.id)
        assert fetched.id == wf.id
        assert fetched.name == wf.name

    def test_get_non_existent_raises(self) -> None:
        with pytest.raises(WorkflowNotFoundError):
            get_workflow("nonexistent-id")


class TestListWorkflows:
    def test_list_empty(self) -> None:
        # Each test gets a fresh repo (module-level singletons persist across
        # tests, but we can check the behaviour independently).
        result = list_workflows()
        assert isinstance(result, list)

    def test_list_returns_all(self) -> None:
        wf1 = create_workflow(_valid_dsl(), name="a")
        wf2 = create_workflow(_valid_dsl(), name="b")
        ids = {w.id for w in list_workflows()}
        assert wf1.id in ids
        assert wf2.id in ids


# ═══════════════════════════════════════════════════════════════════════
#  AC-2: cycle detection
# ═══════════════════════════════════════════════════════════════════════


class TestCycleDetection:
    def test_dag_succeeds(self) -> None:
        """A DAG without cycles should be accepted."""
        wf = create_workflow(_dsl_with_decision())
        assert wf.current_version == 1

    def test_simple_cycle_raises(self) -> None:
        """A→B→C→A with no loop node → CIRCULAR_WORKFLOW."""
        dsl = {
            "nodes": [
                {"id": "s", "type": "start"},
                {"id": "a", "type": "task"},
                {"id": "b", "type": "task"},
                {"id": "e", "type": "end"},
            ],
            "edges": [
                {"source": "s", "target": "a"},
                {"source": "a", "target": "b"},
                {"source": "b", "target": "a"},  # back-edge forming a cycle
                {"source": "a", "target": "e"},
            ],
        }
        with pytest.raises(CircularWorkflowError, match="Cycle detected"):
            create_workflow(dsl)

    def test_cycle_with_loop_node_allowed(self) -> None:
        """A cycle that goes through a `loop` node is allowed."""
        dsl = {
            "nodes": [
                {"id": "s", "type": "start"},
                {"id": "loop1", "type": "loop", "label": "重试循环"},
                {"id": "task_x", "type": "task"},
                {"id": "e", "type": "end"},
            ],
            "edges": [
                {"source": "s", "target": "loop1"},
                {"source": "loop1", "target": "task_x"},
                {"source": "task_x", "target": "loop1"},  # back to loop — OK
                {"source": "loop1", "target": "e"},
            ],
        }
        wf = create_workflow(dsl)
        assert wf.current_version == 1

    def test_cycle_outside_loop_node_still_forbidden(self) -> None:
        """If there is a loop node but the cycle does NOT involve it,
        the cycle should still be rejected."""
        dsl = {
            "nodes": [
                {"id": "s", "type": "start"},
                {"id": "loop1", "type": "loop"},
                {"id": "a", "type": "task"},
                {"id": "b", "type": "task"},
                {"id": "e", "type": "end"},
            ],
            "edges": [
                {"source": "s", "target": "a"},
                {"source": "a", "target": "b"},
                {"source": "b", "target": "a"},  # cycle between a and b (no loop)
                {"source": "a", "target": "loop1"},
                {"source": "loop1", "target": "e"},
            ],
        }
        with pytest.raises(CircularWorkflowError, match="Cycle detected"):
            create_workflow(dsl)

    def test_self_loop_without_loop_node_raises(self) -> None:
        """A node pointing to itself without loop type → cycle."""
        dsl = {
            "nodes": [
                {"id": "s", "type": "start"},
                {"id": "a", "type": "task"},
                {"id": "e", "type": "end"},
            ],
            "edges": [
                {"source": "s", "target": "a"},
                {"source": "a", "target": "a"},  # self-loop
                {"source": "a", "target": "e"},
            ],
        }
        with pytest.raises(CircularWorkflowError):
            create_workflow(dsl)

    def test_self_loop_on_loop_node_allowed(self) -> None:
        """A loop node with a self-loop is explicitly allowed."""
        dsl = {
            "nodes": [
                {"id": "s", "type": "start"},
                {"id": "lp", "type": "loop"},
                {"id": "e", "type": "end"},
            ],
            "edges": [
                {"source": "s", "target": "lp"},
                {"source": "lp", "target": "lp"},
                {"source": "lp", "target": "e"},
            ],
        }
        wf = create_workflow(dsl)
        assert wf.current_version == 1

    def test_cycle_detection_via_dsl_directly(self) -> None:
        """Verify that WorkflowDsl.validate() also catches cycles."""
        dsl = {
            "nodes": [
                {"id": "x", "type": "start"},
                {"id": "y", "type": "task"},
                {"id": "z", "type": "end"},
            ],
            "edges": [
                {"source": "x", "target": "y"},
                {"source": "y", "target": "x"},
            ],
        }
        with pytest.raises(CircularWorkflowError):
            WorkflowDsl.from_dict(dsl)


# ═══════════════════════════════════════════════════════════════════════
#  AC-3: version management
# ═══════════════════════════════════════════════════════════════════════


class TestVersionManagement:
    def test_create_workflow_creates_v1(self) -> None:
        wf = create_workflow(_valid_dsl())
        versions = list_workflow_versions(wf.id)
        assert len(versions) == 1
        assert versions[0].version_number == 1
        assert versions[0].label == "Initial version"

    def test_update_workflow_creates_new_version(self) -> None:
        wf = create_workflow(_valid_dsl(), name="original")
        updated = update_workflow(wf.id, _dsl_with_decision())

        assert updated.current_version == 2
        versions = list_workflow_versions(wf.id)
        assert len(versions) == 2
        assert [v.version_number for v in versions] == [1, 2]
        assert versions[1].dsl.nodes[1].type == "decision"

    def test_create_workflow_version_with_label(self) -> None:
        wf = create_workflow(_valid_dsl())
        v = create_workflow_version(wf.id, label="milestone-a")
        assert v.label == "milestone-a"
        assert v.version_number > 0

    def test_list_versions_sorted(self) -> None:
        wf = create_workflow(_valid_dsl())
        update_workflow(wf.id, _dsl_with_decision())
        update_workflow(wf.id, _valid_dsl())
        versions = list_workflow_versions(wf.id)
        assert versions == sorted(versions, key=lambda v: v.version_number)

    def test_list_versions_for_unknown_workflow_raises(self) -> None:
        with pytest.raises(WorkflowNotFoundError):
            list_workflow_versions("unknown")

    def test_rollback_restores_dsl(self) -> None:
        wf = create_workflow(_valid_dsl(), name="rollback-test")
        update_workflow(wf.id, _dsl_with_decision())

        rolled = rollback_workflow(wf.id, 1)
        # DSL should be restored to the v1 snapshot (3 nodes: start/task/end)
        node_types = {n.type for n in rolled.dsl.nodes}
        assert node_types == {"start", "task", "end"}

    def test_rollback_creates_audit_version(self) -> None:
        wf = create_workflow(_valid_dsl())
        update_workflow(wf.id, _dsl_with_decision())

        before_count = len(list_workflow_versions(wf.id))
        rollback_workflow(wf.id, 1)
        after_count = len(list_workflow_versions(wf.id))
        assert after_count == before_count + 1

        versions = list_workflow_versions(wf.id)
        assert versions[-1].label.startswith("Rollback to v1")

    def test_rollback_then_update_increments_correctly(self) -> None:
        wf = create_workflow(_valid_dsl())
        update_workflow(wf.id, _dsl_with_decision())  # v2
        rollback_workflow(wf.id, 1)  # v3

        # Another update should produce v4.
        updated = update_workflow(wf.id, _dsl_with_decision())
        assert updated.current_version == 4

    def test_rollback_to_nonexistent_version_raises(self) -> None:
        wf = create_workflow(_valid_dsl())
        with pytest.raises(VersionNotFoundError):
            rollback_workflow(wf.id, 999)

    def test_rollback_nonexistent_workflow_raises(self) -> None:
        with pytest.raises(WorkflowNotFoundError):
            rollback_workflow("nonexistent", 1)


# ═══════════════════════════════════════════════════════════════════════
#  AC-4: templates
# ═══════════════════════════════════════════════════════════════════════


class TestTemplates:
    def test_save_as_private_template(self) -> None:
        wf = create_workflow(_valid_dsl(), name="src")
        tpl = save_as_template(wf.id, "my-template", visibility="PRIVATE")
        assert isinstance(tpl, WorkflowTemplate)
        assert tpl.name == "my-template"
        assert tpl.visibility == "PRIVATE"
        assert tpl.source_workflow_id == wf.id

    def test_save_as_tenant_template(self) -> None:
        wf = create_workflow(_valid_dsl(), name="src")
        tpl = save_as_template(wf.id, "shared-tmpl", visibility="TENANT")
        assert tpl.visibility == "TENANT"

    def test_save_template_snapshots_current_dsl(self) -> None:
        wf = create_workflow(_valid_dsl())
        tpl = save_as_template(wf.id, "snap")
        assert len(tpl.dsl.nodes) == 3

    def test_list_templates_filtered(self) -> None:
        wf = create_workflow(_valid_dsl())
        save_as_template(wf.id, "p1", visibility="PRIVATE")
        save_as_template(wf.id, "t1", visibility="TENANT")

        private = list_templates(visibility="PRIVATE")
        assert all(t.visibility == "PRIVATE" for t in private)
        assert len(private) >= 1

        tenant = list_templates(visibility="TENANT")
        assert all(t.visibility == "TENANT" for t in tenant)
        assert len(tenant) >= 1

    def test_list_templates_unfiltered(self) -> None:
        wf = create_workflow(_valid_dsl())
        save_as_template(wf.id, "a", visibility="PRIVATE")
        save_as_template(wf.id, "b", visibility="TENANT")

        all_t = list_templates()
        assert len(all_t) >= 2

    def test_save_template_from_unknown_workflow_raises(self) -> None:
        with pytest.raises(WorkflowNotFoundError):
            save_as_template("unknown", "tmpl")

    def test_get_template(self) -> None:
        wf = create_workflow(_valid_dsl())
        saved = save_as_template(wf.id, "get-me")
        fetched = get_template(saved.id)
        assert fetched.name == "get-me"

    def test_get_template_not_found_raises(self) -> None:
        with pytest.raises(TemplateNotFoundError):
            get_template("no-such-template")

    def test_save_template_invalid_visibility_raises(self) -> None:
        wf = create_workflow(_valid_dsl())
        with pytest.raises(ValueError, match="visibility"):
            save_as_template(wf.id, "bad", visibility="PUBLIC")


# ═══════════════════════════════════════════════════════════════════════
#  DSL round-trip (serialisation)
# ═══════════════════════════════════════════════════════════════════════


class TestDslRoundTrip:
    def test_to_dict_round_trip(self) -> None:
        d = _valid_dsl()
        parsed = WorkflowDsl.from_dict(d)
        exported = parsed.to_dict()
        assert exported == d

    def test_to_dict_round_trip_with_decision(self) -> None:
        d = _dsl_with_decision()
        parsed = WorkflowDsl.from_dict(d)
        exported = parsed.to_dict()
        assert exported == d


# ═══════════════════════════════════════════════════════════════════════
#  Workflow update
# ═══════════════════════════════════════════════════════════════════════


class TestUpdateWorkflow:
    def test_update_changes_dsl_and_version(self) -> None:
        wf = create_workflow(_valid_dsl())
        updated = update_workflow(wf.id, _dsl_with_decision())
        assert updated.current_version == 2
        assert len(updated.dsl.nodes) == 5  # the decision DAG has 5 nodes

    def test_update_invalid_dsl_raises(self) -> None:
        wf = create_workflow(_valid_dsl())
        with pytest.raises(InvalidWorkflowDslError):
            update_workflow(wf.id, {"nodes": [], "edges": []})

    def test_update_unknown_workflow_raises(self) -> None:
        with pytest.raises(WorkflowNotFoundError):
            update_workflow("unknown", _valid_dsl())
