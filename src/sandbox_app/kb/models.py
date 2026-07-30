"""Knowledge base models — dataclasses only."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class KnowledgeBase:
    name: str
    embedding_model: str
    chunk_strategy: str
    vector_db_config: dict
    id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "INITIALIZED"


@dataclass
class ImportJob:
    kb_id: str
    source_type: str  # "FILE"
    source_path: str
    id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "QUEUED"


@dataclass
class SearchResult:
    doc_id: str
    chunk_text: str
    score: float
