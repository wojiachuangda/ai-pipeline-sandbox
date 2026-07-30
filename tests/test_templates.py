"""Tests for template listing, filtering, pagination, and custom save (AC-1, AC-5)."""

import pytest

from sandbox_app import AgentType
from sandbox_app.template_store import TemplateStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_store() -> TemplateStore:
    """Return a freshly-seeded store so tests don't leak state."""
    return TemplateStore()


# ---------------------------------------------------------------------------
# AC-1: list + filter + paginate
# ---------------------------------------------------------------------------


class TestListAll:
    """Pre-seeded presets are returned with correct metadata."""

    def test_count(self) -> None:
        store = _fresh_store()
        result = store.list()
        assert result["total"] == 3
        assert len(result["items"]) == 3

    def test_each_preset_has_correct_fields(self) -> None:
        store = _fresh_store()
        result = store.list()
        ids = {t.id for t in result["items"]}
        assert ids == {"TPL-LLM-V1", "TPL-RAG-V1", "TPL-CODE-V1"}

        by_id = {t.id: t for t in result["items"]}

        llm = by_id["TPL-LLM-V1"]
        assert llm.name == "LLM Agent"
        assert llm.agent_type == AgentType.LLM
        assert llm.is_preset is True

        rag = by_id["TPL-RAG-V1"]
        assert rag.name == "RAG Agent"
        assert rag.agent_type == AgentType.RAG
        assert rag.is_preset is True

        code = by_id["TPL-CODE-V1"]
        assert code.name == "Code Execution Agent"
        assert code.agent_type == AgentType.CODE
        assert code.is_preset is True


class TestListFilterByKeyword:
    """``keyword=`` is a case-insensitive substring match on name + keywords."""

    def test_exact_keyword_match(self) -> None:
        store = _fresh_store()
        result = store.list(keyword="rag")
        assert result["total"] == 1
        assert result["items"][0].id == "TPL-RAG-V1"

    def test_keyword_matches_name(self) -> None:
        store = _fresh_store()
        # "code" appears in name of TPL-CODE-V1 ("Code Execution Agent")
        result = store.list(keyword="code")
        assert result["total"] >= 1
        ids = {t.id for t in result["items"]}
        assert "TPL-CODE-V1" in ids

    def test_keyword_matches_keyword_list(self) -> None:
        store = _fresh_store()
        # "chat" is a keyword for LLM
        result = store.list(keyword="chat")
        assert result["total"] == 1
        assert result["items"][0].id == "TPL-LLM-V1"

    def test_keyword_case_insensitive(self) -> None:
        store = _fresh_store()
        # "RETRIEVAL" is a lowercase-insensitive match for the RAG keyword "retrieval"
        result = store.list(keyword="RETRIEVAL")
        assert result["total"] == 1
        assert result["items"][0].id == "TPL-RAG-V1"

    def test_keyword_no_match(self) -> None:
        store = _fresh_store()
        result = store.list(keyword="nonexistent")
        assert result["total"] == 0
        assert result["items"] == []


class TestListFilterByAgentType:
    """``agent_type=`` filters by exact AgentType match."""

    def test_llm_type(self) -> None:
        store = _fresh_store()
        result = store.list(agent_type=AgentType.LLM)
        assert result["total"] == 1
        assert result["items"][0].id == "TPL-LLM-V1"

    def test_rag_type(self) -> None:
        store = _fresh_store()
        result = store.list(agent_type=AgentType.RAG)
        assert result["total"] == 1
        assert result["items"][0].id == "TPL-RAG-V1"

    def test_code_type(self) -> None:
        store = _fresh_store()
        result = store.list(agent_type=AgentType.CODE)
        assert result["total"] == 1
        assert result["items"][0].id == "TPL-CODE-V1"

    def test_string_passthrough(self) -> None:
        """Passing a plain string works too."""
        store = _fresh_store()
        result = store.list(agent_type="LLM")
        assert result["total"] == 1
        assert result["items"][0].id == "TPL-LLM-V1"


class TestListFilterCombined:
    """Keyword + agent_type combined use AND logic."""

    def test_both_match(self) -> None:
        store = _fresh_store()
        result = store.list(keyword="sandbox", agent_type=AgentType.CODE)
        assert result["total"] == 1
        assert result["items"][0].id == "TPL-CODE-V1"

    def test_keyword_matches_but_wrong_type(self) -> None:
        store = _fresh_store()
        # "python" is a keyword for CODE, but type filter is LLM
        result = store.list(keyword="python", agent_type=AgentType.LLM)
        assert result["total"] == 0


class TestListPagination:
    """Pagination works with page + page_size."""

    def test_page_size_1_scrolls_through_all(self) -> None:
        store = _fresh_store()
        page1 = store.list(page=1, page_size=1)
        assert page1["total"] == 3
        assert len(page1["items"]) == 1

        page2 = store.list(page=2, page_size=1)
        assert len(page2["items"]) == 1
        assert page2["items"][0].id != page1["items"][0].id

        page3 = store.list(page=3, page_size=1)
        assert len(page3["items"]) == 1

        page4 = store.list(page=4, page_size=1)
        assert len(page4["items"]) == 0

        # All ids are distinct
        all_ids = {page1["items"][0].id, page2["items"][0].id, page3["items"][0].id}
        assert len(all_ids) == 3

    def test_page_metadata_is_correct(self) -> None:
        store = _fresh_store()
        result = store.list(page=2, page_size=2)
        assert result["page"] == 2
        assert result["page_size"] == 2
        assert result["total"] == 3
        assert len(result["items"]) == 1  # only 1 item left on page 2

    def test_page_out_of_range(self) -> None:
        store = _fresh_store()
        result = store.list(page=999, page_size=20)
        assert result["items"] == []
        assert result["total"] == 3


# ---------------------------------------------------------------------------
# AC-5: save custom template
# ---------------------------------------------------------------------------


class TestSaveCustomTemplate:
    """Save an existing Agent as a custom template."""

    def test_basic_save_and_list(self) -> None:
        from sandbox_app.agent_store import AgentStore

        store = _fresh_store()
        agent_store = AgentStore(store)

        # Register an agent first
        agent = agent_store.register("My Custom", agent_type=AgentType.LLM, config={"x": 1})

        # Save as custom template
        tpl = agent_store.save_as_template(agent.id, "tenant-1", "My Custom Template")

        assert tpl.id.startswith("TPL-CUSTOM-")
        assert tpl.name == "My Custom Template"
        assert tpl.is_preset is False
        assert tpl.default_config == {"x": 1}

        # Template now appears in list
        result = store.list()
        assert result["total"] == 4  # 3 presets + 1 custom

    def test_tenant_scoped_unique_name(self) -> None:
        from sandbox_app.agent_store import AgentStore

        store = _fresh_store()
        agent_store = AgentStore(store)

        agent = agent_store.register("A1", agent_type=AgentType.LLM)
        agent_store.save_as_template(agent.id, "tenant-1", "My Tpl")

        # Same tenant, same name (case-insensitive) → error
        with pytest.raises(ValueError, match="already exists"):
            agent_store.save_as_template(agent.id, "tenant-1", "My Tpl")

        with pytest.raises(ValueError, match="already exists"):
            agent_store.save_as_template(agent.id, "tenant-1", "  my tpl  ")

    def test_different_tenants_same_name_ok(self) -> None:
        from sandbox_app.agent_store import AgentStore

        store = _fresh_store()
        agent_store = AgentStore(store)

        agent = agent_store.register("A1", agent_type=AgentType.LLM)

        # Same name, different tenants → OK
        tpl1 = agent_store.save_as_template(agent.id, "tenant-1", "Shared Name")
        tpl2 = agent_store.save_as_template(agent.id, "tenant-2", "Shared Name")

        assert tpl1.id != tpl2.id
        assert store.list()["total"] == 5  # 3 presets + 2 customs
