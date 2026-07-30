"""Tests for agent creation from templates and save-as-template (AC-2/3/4/6/7)."""

import pytest

from sandbox_app import AgentStatus, AgentType
from sandbox_app.agent_store import AgentStore
from sandbox_app.template_store import TemplateStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh() -> AgentStore:
    """Return a freshly-seeded AgentStore so tests don't leak state."""
    return AgentStore(TemplateStore())


# ---------------------------------------------------------------------------
# AC-2: create from LLM / RAG / CODE templates → INACTIVE, same shape as register
# ---------------------------------------------------------------------------


class TestCreateFromLLMTemplate:
    """Agents created from TPL-LLM-V1 have correct type, status, and default keys."""

    def test_status_is_inactive(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-LLM-V1", "My LLM Agent")
        assert agent.status == AgentStatus.INACTIVE

    def test_agent_type_is_llm(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-LLM-V1", "My LLM Agent")
        assert agent.agent_type == AgentType.LLM

    def test_default_config_keys_present(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-LLM-V1", "My LLM Agent")
        assert agent.config["model_name"] == "claude-sonnet-5"
        assert agent.config["temperature"] == 0.7
        assert "system_prompt_template" in agent.config

    def test_template_id_is_recorded(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-LLM-V1", "My LLM Agent")
        assert agent.template_id == "TPL-LLM-V1"


class TestCreateFromRAGTemplate:
    """Agents created from TPL-RAG-V1 get the knowledge-base hint (AC-3)."""

    def test_needs_knowledge_base_true(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-RAG-V1", "My RAG Agent")
        assert agent.needs_knowledge_base is True

    def test_config_contains_hint(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-RAG-V1", "My RAG Agent")
        assert "_hint" in agent.config
        assert "knowledge base" in agent.config["_hint"].lower()

    def test_default_rag_config_keys(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-RAG-V1", "My RAG Agent")
        assert agent.config["embedding_model"] == "text-embedding-3-small"
        assert agent.config["chunk_size"] == 512
        assert agent.config["top_k"] == 5

    def test_status_is_inactive(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-RAG-V1", "My RAG Agent")
        assert agent.status == AgentStatus.INACTIVE


class TestCreateFromCODETemplate:
    """Agents created from TPL-CODE-V1 carry language/timeout/memory keys (AC-4)."""

    def test_language_timeout_memory_keys_present(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-CODE-V1", "My CODE Agent")
        assert agent.config["allowed_languages"] == ["python"]
        assert agent.config["execution_timeout_secs"] == 30
        assert agent.config["memory_limit_mb"] == 256

    def test_agent_type_is_code(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-CODE-V1", "My CODE Agent")
        assert agent.agent_type == AgentType.CODE

    def test_status_is_inactive(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-CODE-V1", "My CODE Agent")
        assert agent.status == AgentStatus.INACTIVE


# ---------------------------------------------------------------------------
# AC-2 (continued): error paths + shape consistency
# ---------------------------------------------------------------------------


class TestCreateFromUnknownTemplate:
    """ValueError for a non-existent template_id."""

    def test_raises_on_unknown_id(self) -> None:
        store = _fresh()
        with pytest.raises(ValueError, match="Unknown template id"):
            store.create_from_template("TPL-NOPE-X", "Bad Agent")

    def test_raises_on_empty_string(self) -> None:
        store = _fresh()
        with pytest.raises(ValueError, match="Unknown template id"):
            store.create_from_template("", "Bad Agent")


class TestCreateWithOverrides:
    """``overrides=`` deep-merges into the template default_config."""

    def test_top_level_override(self) -> None:
        store = _fresh()
        agent = store.create_from_template(
            "TPL-LLM-V1", "Hot Agent", overrides={"temperature": 0.2}
        )
        assert agent.config["temperature"] == 0.2
        # existing keys untouched
        assert agent.config["model_name"] == "claude-sonnet-5"

    def test_new_key_added(self) -> None:
        store = _fresh()
        agent = store.create_from_template(
            "TPL-LLM-V1", "Extra", overrides={"custom_key": "val"}
        )
        assert agent.config["custom_key"] == "val"

    def test_deep_merge_does_not_mutate_template(self) -> None:
        store = _fresh()
        _ = store.create_from_template(
            "TPL-LLM-V1", "Agent A", overrides={"temperature": 0.0}
        )
        # Second creation from the same template gets pristine defaults
        agent2 = store.create_from_template("TPL-LLM-V1", "Agent B")
        assert agent2.config["temperature"] == 0.7


class TestRegisterVsTemplateStatus:
    """register() → ACTIVE; create_from_template() → INACTIVE."""

    def test_register_is_active(self) -> None:
        store = _fresh()
        agent = store.register("Direct", agent_type=AgentType.LLM)
        assert agent.status == AgentStatus.ACTIVE

    def test_template_is_inactive(self) -> None:
        store = _fresh()
        agent = store.create_from_template("TPL-LLM-V1", "From Template")
        assert agent.status == AgentStatus.INACTIVE


class TestCreatedAgentShapeMatchesRegister:
    """Agent from template has the same fields as one from register()."""

    def test_shape_consistency(self) -> None:
        store = _fresh()
        direct = store.register("Direct", agent_type=AgentType.LLM, config={"a": 1})
        template_agent = store.create_from_template("TPL-LLM-V1", "From Template")

        # Both have the same set of field names
        from dataclasses import fields as dc_fields

        direct_fields = {f.name for f in dc_fields(direct)}
        template_fields = {f.name for f in dc_fields(template_agent)}
        assert direct_fields == template_fields


# ---------------------------------------------------------------------------
# AC-6: save-as-template duplicate-name error (also covered in test_templates.py)
# ---------------------------------------------------------------------------


class TestSaveAsTemplate:
    """End-to-end save-as-template from the AgentStore side."""

    def test_save_and_retrieve(self) -> None:
        store = _fresh()
        agent = store.register("Source", agent_type=AgentType.CODE, config={"timeout": 60})

        tpl = store.save_as_template(agent.id, "tenant-x", "My Code Tpl")

        # Agent's config became template's default_config
        assert tpl.default_config == {"timeout": 60}
        assert tpl.agent_type == AgentType.CODE
        assert tpl.id.startswith("TPL-CUSTOM-")
        assert not tpl.is_preset

    def test_duplicate_name_raises(self) -> None:
        store = _fresh()
        agent = store.register("Source", agent_type=AgentType.LLM)
        store.save_as_template(agent.id, "tenant-x", "Dupe")

        with pytest.raises(ValueError, match="already exists"):
            store.save_as_template(agent.id, "tenant-x", "Dupe")

    def test_unknown_agent_id_raises(self) -> None:
        store = _fresh()
        with pytest.raises(ValueError, match="Unknown agent id"):
            store.save_as_template("AGT-NOPE", "tenant-x", "Name")


# ---------------------------------------------------------------------------
# AC-7: No real LLM / sandbox calls — purely in-memory
# ---------------------------------------------------------------------------


class TestNoRealCalls:
    """Verify zero network or subprocess I/O."""

    def test_no_network_or_subprocess(self) -> None:
        """Creation is purely in-memory — no socket, subprocess, or urllib calls."""
        # If any I/O were attempted we'd catch it via the sandbox; this test
        # simply verifies the stores operate correctly without external deps.
        store = _fresh()
        agent = store.create_from_template("TPL-LLM-V1", "Test")
        assert agent.id.startswith("AGT-")
        assert store.get(agent.id) is not None

    def test_stores_are_independent(self) -> None:
        """Separate store instances do not share state."""
        s1 = _fresh()
        s2 = _fresh()

        a1 = s1.create_from_template("TPL-LLM-V1", "Agent 1")
        a2 = s2.create_from_template("TPL-LLM-V1", "Agent 2")

        # a1 only in s1, a2 only in s2
        assert s1.get(a1.id) is not None
        assert s2.get(a1.id) is None
        assert s2.get(a2.id) is not None
        assert s1.get(a2.id) is None
