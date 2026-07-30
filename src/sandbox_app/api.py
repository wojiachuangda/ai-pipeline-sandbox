"""Flat re-export surface for the agent template marketplace.

Tests import from *one* place; internal consumers import from here as well.
"""

from __future__ import annotations

from .agent_store import AgentStore, agent_store
from .models import Agent, AgentStatus, AgentTemplate, AgentType
from .template_store import TemplateStore, template_store

__all__ = [
    "Agent",
    "AgentStatus",
    "AgentStore",
    "AgentTemplate",
    "AgentType",
    "TemplateStore",
    "agent_store",
    "template_store",
]
