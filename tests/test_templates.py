"""Tests for prompt template CRUD, rendering, and versioning."""

import pytest

from sandbox_app import (
    MissingTemplateVariableError,
    PromptTemplate,
    TemplateStore,
    TemplateVersion,
    VersionedTemplateStore,
    estimate_tokens,
    extract_variables,
    render,
    validate_no_executable,
)


# ---------------------------------------------------------------------------
# AC-1: CRUD
# ---------------------------------------------------------------------------

class TestTemplateCRUD:
    """AC-1: Prompt template create, read, update, delete."""

    def test_create_and_get(self) -> None:
        store = TemplateStore()
        tmpl = store.create("greeting", "Hello {{name}}!")
        assert tmpl.name == "greeting"
        assert tmpl.body == "Hello {{name}}!"
        assert tmpl.id

        fetched = store.get(tmpl.id)
        assert fetched is not None
        assert fetched.id == tmpl.id

    def test_create_with_explicit_required_vars(self) -> None:
        store = TemplateStore()
        tmpl = store.create("test", "Hi {{first}} {{last}}", required_vars=["first"])
        assert tmpl.required_vars == ["first"]

    def test_update_body_and_name(self) -> None:
        store = TemplateStore()
        tmpl = store.create("old", "{{x}}")
        updated = store.update(tmpl.id, name="new", body="{{y}}")
        assert updated.name == "new"
        assert updated.body == "{{y}}"
        assert updated.updated_at > tmpl.created_at

    def test_update_nonexistent_raises(self) -> None:
        store = TemplateStore()
        with pytest.raises(LookupError, match="not found"):
            store.update("nope", body="{{x}}")

    def test_delete(self) -> None:
        store = TemplateStore()
        tmpl = store.create("x", "{{a}}")
        assert store.delete(tmpl.id) is True
        assert store.get(tmpl.id) is None
        assert store.delete(tmpl.id) is False

    def test_list(self) -> None:
        store = TemplateStore()
        store.create("a", "{{x}}")
        store.create("b", "{{y}}")
        assert len(store.list()) == 2


# ---------------------------------------------------------------------------
# AC-1: Safety validation
# ---------------------------------------------------------------------------

class TestSafetyValidation:
    """AC-1: Template body must reject executable patterns."""

    def test_create_rejects_template_tag(self) -> None:
        store = TemplateStore()
        with pytest.raises(ValueError, match="template tag"):
            store.create("bad", "{% raw %}")

    def test_create_rejects_dunder(self) -> None:
        store = TemplateStore()
        with pytest.raises(ValueError, match="dunder"):
            store.create("bad", "{{__import__}}")

    def test_create_rejects_exec_call(self) -> None:
        store = TemplateStore()
        with pytest.raises(ValueError, match="exec\\(\\)"):
            store.create("bad", "exec('rm -rf /')")

    def test_create_rejects_eval_call(self) -> None:
        store = TemplateStore()
        with pytest.raises(ValueError, match="eval\\(\\)"):
            store.create("bad", "eval('1+1')")

    def test_validate_no_executable_returns_errors(self) -> None:
        errors = validate_no_executable("hello {{% code %}} {{__foo__}}")
        assert len(errors) == 2

    def test_clean_body_passes(self) -> None:
        assert validate_no_executable("Hello {{name}}!") == []


# ---------------------------------------------------------------------------
# Variable extraction
# ---------------------------------------------------------------------------

class TestExtractVariables:
    """Variable discovery from template bodies."""

    def test_finds_simple_vars(self) -> None:
        assert extract_variables("{{greeting}} {{name}}!") == {"greeting", "name"}

    def test_ignores_non_var_markers(self) -> None:
        assert extract_variables("plain text") == set()

    def test_ignores_percent_style(self) -> None:
        # {{% … %}} is not matched by the var regex
        assert "greeting" not in extract_variables("{{% greeting %}}")


# ---------------------------------------------------------------------------
# AC-2: Render
# ---------------------------------------------------------------------------

class TestRender:
    """AC-2: Variable interpolation and missing-variable detection."""

    def test_render_success(self) -> None:
        store = TemplateStore()
        tmpl = store.create("hello", "Hello {{name}}, welcome to {{place}}!")
        result = render(tmpl, {"name": "Alice", "place": "Wonderland"})
        assert result == "Hello Alice, welcome to Wonderland!"

    def test_render_missing_required_variable(self) -> None:
        store = TemplateStore()
        tmpl = store.create("hello", "Hello {{name}}!", required_vars=["name"])
        with pytest.raises(MissingTemplateVariableError) as exc_info:
            render(tmpl, {"other": "x"})
        assert exc_info.value.var_name == "name"
        assert MissingTemplateVariableError.CODE in str(exc_info.value)

    def test_render_optional_var_becomes_empty(self) -> None:
        store = TemplateStore()
        tmpl = store.create("x", "{{a}} {{b}}", required_vars=["a"])
        result = render(tmpl, {"a": "present"})
        assert result == "present "


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

class TestEstimateTokens:
    """AC-2: Token count approximation."""

    def test_returns_positive_int(self) -> None:
        n = estimate_tokens("Hello world, this is a test sentence.")
        assert isinstance(n, int)
        assert n > 0

    def test_empty_string_zero(self) -> None:
        assert estimate_tokens("") == 0
        assert estimate_tokens("   ") == 0


# ---------------------------------------------------------------------------
# AC-3: Version list and rollback
# ---------------------------------------------------------------------------

class TestVersionListAndRollback:
    """AC-3: Version snapshots, listing, and rollback."""

    def test_save_and_list_versions(self) -> None:
        t_store = TemplateStore()
        v_store = VersionedTemplateStore()

        tmpl = t_store.create("vtest", "v1 body")
        v_store.save_version(tmpl)  # v1

        t_store.update(tmpl.id, body="v2 body")
        v_store.save_version(tmpl)  # v2

        t_store.update(tmpl.id, body="v3 body")
        v_store.save_version(tmpl)  # v3

        versions = v_store.list_versions(tmpl.id)
        assert len(versions) == 3
        assert [v.version for v in versions] == [1, 2, 3]
        assert [v.body for v in versions] == ["v1 body", "v2 body", "v3 body"]

    def test_rollback_restores_body_and_vars(self) -> None:
        t_store = TemplateStore()
        v_store = VersionedTemplateStore()

        tmpl = t_store.create("rtest", "original {{a}}", required_vars=["a"])
        v_store.save_version(tmpl)  # v1

        t_store.update(tmpl.id, body="changed {{b}}", required_vars=["b"])
        v_store.save_version(tmpl)  # v2

        # Rollback to v1
        restored = v_store.rollback(tmpl.id, version=1, store=t_store)
        assert restored.body == "original {{a}}"
        assert restored.required_vars == ["a"]

    def test_rollback_invalid_version_raises(self) -> None:
        t_store = TemplateStore()
        v_store = VersionedTemplateStore()

        tmpl = t_store.create("x", "body")
        v_store.save_version(tmpl)

        with pytest.raises(LookupError, match="not found"):
            v_store.rollback(tmpl.id, version=99, store=t_store)

    def test_list_versions_empty_for_unknown(self) -> None:
        v_store = VersionedTemplateStore()
        assert v_store.list_versions("unknown") == []
