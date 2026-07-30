"""Knowledge base sub-package — registration, import, search."""

from .embedding import FakeEmbedder
from .models import ImportJob, KnowledgeBase, SearchResult
from .service import import_documents, register_kb, search
from .vector_store import InMemoryVectorStore

__all__ = [
    "FakeEmbedder",
    "ImportJob",
    "InMemoryVectorStore",
    "KnowledgeBase",
    "SearchResult",
    "import_documents",
    "register_kb",
    "search",
]
