"""In-memory agent store — register, create-from-template, save-as-template."""

from __future__ import annotations

import copy
import uuid

from .models import Agent, AgentStatus, AgentTemplate, AgentType
from .template_store import TemplateStore, template_store


class AgentStore:
    """Thread-safe in-memory store for agent instances.

    Supports direct registration (T-002 compatibility) and creation from
    a template (the new T-003 functionality).  No real LLM / sandbox calls
    are made — everything is pure in-memory state.
    """

    def __init__(self, template_store: TemplateStore) -> None:
        self._store: dict[str, Agent] = {}
        self._templates = template_store

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        agent_type: AgentType | str,
        config: dict | None = None,
    ) -> Agent:
        """Register a new agent directly (T-002 semantics).

        Created agent is **ACTIVE** by default.
        """
        agent = Agent(
            id=f"AGT-{uuid.uuid4().hex[:8].upper()}",
            name=name,
            agent_type=AgentType(agent_type) if isinstance(agent_type, str) else agent_type,
            status=AgentStatus.ACTIVE,
            config=copy.deepcopy(config) if config else {},
        )
        self._store[agent.id] = agent
        return agent

    def get(self, agent_id: str) -> Agent | None:
        """Return a single agent by id, or *None*."""
        return self._store.get(agent_id)

    # ------------------------------------------------------------------
    # Template-based creation (T-003)
    # ------------------------------------------------------------------

    def create_from_template(
        self,
        template_id: str,
        name: str,
        overrides: dict | None = None,
    ) -> Agent:
        """Create an agent from a predefined or custom template.

        Parameters
        ----------
        template_id:
            The template to base this agent on (e.g. ``"TPL-LLM-V1"``).
        name:
            Display name for the new agent.
        overrides:
            Optional dict that will be deep-merged into the template's
            ``default_config`` (override keys win).

        Returns
        -------
        Agent
            The newly-created agent with ``status=INACTIVE``.

        Raises
        ------
        ValueError
            If *template_id* does not exist.
        """
        template = self._templates.get(template_id)
        if template is None:
            raise ValueError(f"Unknown template id: {template_id}")

        # Deep-copy default_config and merge overrides
        config = copy.deepcopy(template.default_config)
        if overrides:
            _deep_merge(config, overrides)

        # AC-3: RAG template → needs_knowledge_base marker
        needs_knowledge_base = False
        if template.agent_type == AgentType.RAG:
            needs_knowledge_base = True
            config["_hint"] = (
                "This agent requires a knowledge base to be bound before activation"
            )

        # AC-4: CODE template validation is inherent — config always carries the
        # allowed_languages / execution_timeout_secs / memory_limit_mb keys from
        # the preset.

        agent = Agent(
            id=f"AGT-{uuid.uuid4().hex[:8].upper()}",
            name=name,
            agent_type=template.agent_type,
            status=AgentStatus.INACTIVE,
            config=config,
            template_id=template_id,
            needs_knowledge_base=needs_knowledge_base,
        )
        self._store[agent.id] = agent
        return agent

    # ------------------------------------------------------------------
    # Save Agent as custom template (AC-5)
    # ------------------------------------------------------------------

    def save_as_template(
        self, agent_id: str, tenant_id: str, name: str
    ) -> AgentTemplate:
        """Snapshot an existing Agent as a reusable custom template.

        Delegates to ``TemplateStore.save_custom()`` so the tenant+name
        uniqueness rule is enforced.

        Raises
        ------
        ValueError
            If *agent_id* is unknown or the (tenant_id, name) pair is
            already taken.
        """
        agent = self._store.get(agent_id)
        if agent is None:
            raise ValueError(f"Unknown agent id: {agent_id}")
        return self._templates.save_custom(tenant_id, name, agent)


def _deep_merge(base: dict, overrides: dict) -> None:
    """In-place deep merge of *overrides* into *base*."""
    for key, value in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)


agent_store = AgentStore(template_store)
