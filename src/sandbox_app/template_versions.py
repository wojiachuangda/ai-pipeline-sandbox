"""Template version snapshot, listing, and rollback."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .templates import PromptTemplate


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------

@dataclass
class TemplateVersion:
    """A frozen snapshot of a :class:`PromptTemplate` at a point in time."""

    template_id: str
    version: int
    body: str
    required_vars: list[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Versioned store
# ---------------------------------------------------------------------------

class VersionedTemplateStore:
    """Decorates a :class:`~.templates.TemplateStore` with version history.

    Call :meth:`save_version` **before** calling ``update`` on the
    underlying template store so the current state is captured.
    """

    def __init__(self) -> None:
        self._versions: dict[str, list[TemplateVersion]] = {}  # template_id → versions

    # ------------------------------------------------------------------

    def save_version(self, template: PromptTemplate) -> TemplateVersion:
        """Snapshot *template* as a new version and return it."""
        versions = self._versions.setdefault(template.id, [])
        next_version = len(versions) + 1
        tv = TemplateVersion(
            template_id=template.id,
            version=next_version,
            body=template.body,
            required_vars=list(template.required_vars),
        )
        versions.append(tv)
        return tv

    # ------------------------------------------------------------------

    def list_versions(self, template_id: str) -> list[TemplateVersion]:
        """Return all versions for *template_id*, newest last."""
        return list(self._versions.get(template_id, []))

    # ------------------------------------------------------------------

    def rollback(
        self, template_id: str, version: int, store: "TemplateStore"  # noqa: F821
    ) -> PromptTemplate:
        """Restore *template_id* to the given *version* snapshot.

        Returns the (now-updated) :class:`PromptTemplate`.
        """
        versions = self._versions.get(template_id, [])
        if not versions or version < 1 or version > len(versions):
            raise LookupError(
                f"Version {version} not found for template '{template_id}'"
            )
        tv = versions[version - 1]
        return store.update(
            template_id, body=tv.body, required_vars=list(tv.required_vars)
        )
