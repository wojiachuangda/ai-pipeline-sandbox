"""In-memory template store with pre-seeded presets and custom template support."""

from __future__ import annotations

import copy
import uuid
from typing import Optional

from .models import Agent, AgentTemplate, AgentType

# ---------------------------------------------------------------------------
# Pre-seeded presets (per PRD naming convention)
# ---------------------------------------------------------------------------

_PRESETS: list[AgentTemplate] = [
    AgentTemplate(
        id="TPL-LLM-V1",
        name="LLM Agent",
        agent_type=AgentType.LLM,
        description="General-purpose LLM agent for chat, text generation, and assistance.",
        keywords=["llm", "chat", "assistant", "text"],
        is_preset=True,
        default_config={
            "model_name": "claude-sonnet-5",
            "system_prompt_template": "",
            "temperature": 0.7,
        },
    ),
    AgentTemplate(
        id="TPL-RAG-V1",
        name="RAG Agent",
        agent_type=AgentType.RAG,
        description="Retrieval-augmented generation agent with knowledge base integration.",
        keywords=["rag", "retrieval", "knowledge", "search"],
        is_preset=True,
        default_config={
            "embedding_model": "text-embedding-3-small",
            "chunk_size": 512,
            "top_k": 5,
        },
    ),
    AgentTemplate(
        id="TPL-CODE-V1",
        name="Code Execution Agent",
        agent_type=AgentType.CODE,
        description="Sandboxed code execution agent for running snippets safely.",
        keywords=["code", "sandbox", "execute", "python"],
        is_preset=True,
        default_config={
            "allowed_languages": ["python"],
            "execution_timeout_secs": 30,
            "memory_limit_mb": 256,
        },
    ),
]


class TemplateStore:
    """Thread-safe in-memory store for agent templates.

    Pre-seeded with three presets (LLM, RAG, CODE).  Supports listing
    with keyword / agent_type filtering and pagination, plus saving
    custom templates on-the-fly with tenant-scoped name uniqueness.
    """

    def __init__(self) -> None:
        # Seed with deep copies so mutations in one store don't leak
        self._templates: dict[str, AgentTemplate] = {
            t.id: copy.deepcopy(t) for t in _PRESETS
        }
        # Track custom-template name uniqueness: key = (tenant_id, name_lower)
        self._custom_names: set[tuple[str, str]] = set()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list(
        self,
        keyword: Optional[str] = None,
        agent_type: Optional[AgentType | str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Return filtered + paginated templates.

        Parameters
        ----------
        keyword:
            Case-insensitive substring match against template name *and*
            keyword list.  ``None`` means no keyword filter.
        agent_type:
            Exact match on ``AgentType``.  Accepts a string (e.g. ``"LLM"``)
            or an ``AgentType`` enum value.  ``None`` means no type filter.
        page:
            1-indexed page number.
        page_size:
            Items per page (≥ 1).

        Returns
        -------
        dict
            ``{"items": [...], "total": int, "page": int, "page_size": int}``
        """
        items = list(self._templates.values())

        # -- keyword filter ---------------------------------------------------
        if keyword is not None:
            kw_lower = keyword.lower()

            def _matches_keyword(t: AgentTemplate) -> bool:
                if kw_lower in t.name.lower():
                    return True
                return any(kw_lower in k.lower() for k in t.keywords)

            items = [t for t in items if _matches_keyword(t)]

        # -- agent_type filter ------------------------------------------------
        if agent_type is not None:
            if isinstance(agent_type, str):
                agent_type = AgentType(agent_type)
            items = [t for t in items if t.agent_type == agent_type]

        # -- pagination -------------------------------------------------------
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        paged = items[start:end]

        return {
            "items": paged,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get(self, template_id: str) -> AgentTemplate | None:
        """Return a single template by id, or *None*."""
        return self._templates.get(template_id)

    # ------------------------------------------------------------------
    # Custom templates
    # ------------------------------------------------------------------

    def save_custom(
        self, tenant_id: str, name: str, source_agent: Agent
    ) -> AgentTemplate:
        """Save an existing Agent as a reusable custom template.

        Parameters
        ----------
        tenant_id:
            Tenant that owns the custom template.
        name:
            Human-readable name — must be unique within the tenant (case-
            insensitive).
        source_agent:
            The Agent whose config will become the template's default_config.

        Returns
        -------
        AgentTemplate
            The newly-created custom template.

        Raises
        ------
        ValueError
            If *name* is already taken within *tenant_id*.
        """
        key = (tenant_id, name.strip().lower())
        if key in self._custom_names:
            raise ValueError(
                f"Template name '{name}' already exists for tenant '{tenant_id}'"
            )

        template_id = f"TPL-CUSTOM-{uuid.uuid4().hex[:8].upper()}"
        template = AgentTemplate(
            id=template_id,
            name=name.strip(),
            agent_type=source_agent.agent_type,
            description=f"Custom template from agent '{source_agent.name}'",
            keywords=[],
            is_preset=False,
            default_config=copy.deepcopy(source_agent.config),
        )
        self._templates[template_id] = template
        self._custom_names.add(key)
        return template


# Module-level singleton — tests get fresh instances by constructing directly
template_store = TemplateStore()
