"""Domain models for the Agent Template Marketplace.

Uses plain stdlib dataclasses — no Pydantic dependency needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentType(str, Enum):
    """Supported agent archetypes."""

    LLM = "LLM"
    RAG = "RAG"
    CODE = "CODE"


class AgentStatus(str, Enum):
    """Lifecycle status of a created agent."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


@dataclass
class AgentTemplate:
    """Pre-seeded or custom template that describes how to create an Agent."""

    id: str
    name: str
    agent_type: AgentType
    description: str
    keywords: list[str]
    is_preset: bool
    default_config: dict


@dataclass
class Agent:
    """A concrete agent instance — created from a template or registered directly."""

    id: str
    name: str
    agent_type: AgentType
    status: AgentStatus
    config: dict
    template_id: str | None = None
    needs_knowledge_base: bool = False
