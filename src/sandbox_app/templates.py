"""Prompt template CRUD, variable interpolation, and token estimation."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class MissingTemplateVariableError(Exception):
    """Raised when a required template variable is not supplied at render time."""

    CODE: ClassVar[str] = "MISSING_TEMPLATE_VARIABLE"

    def __init__(self, var_name: str) -> None:
        self.var_name = var_name
        super().__init__(
            f"{self.CODE}: required variable '{var_name}' was not provided."
        )


# ---------------------------------------------------------------------------
# Variable extraction
# ---------------------------------------------------------------------------

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def extract_variables(body: str) -> set[str]:
    """Return the set of ``{{var_name}}`` markers found in *body*.

    Only ``{{word_chars}}`` forms are matched; ``{{% … %}}`` and other
    non-variable constructs are ignored.
    """
    return set(_VAR_RE.findall(body))


# ---------------------------------------------------------------------------
# Safety validation – reject executable / template-code injection
# ---------------------------------------------------------------------------

_FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"\{\%", "template tag '{%' is not allowed"),
    (r"__\w+__", "dunder pattern looks like executable code"),
    (r"\bexec\s*\(", "exec() call is not allowed"),
    (r"\beval\s*\(", "eval() call is not allowed"),
]


def validate_no_executable(body: str) -> list[str]:
    """Return a list of error messages if *body* contains forbidden patterns.

    An empty list means the body is safe.
    """
    errors: list[str] = []
    for pattern, message in _FORBIDDEN_PATTERNS:
        if re.search(pattern, body):
            errors.append(message)
    return errors


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_tokens(body: str) -> int:
    """Return a rough estimate of token count for *body*.

    Uses a simple word-count heuristic (``len(body.split())``) which
    approximates the tokeniser behaviour of common LLM APIs within a
    reasonable margin.  This is NOT an exact count — for precise billing
    use a model-specific tokenizer.
    """
    if not body.strip():
        return 0
    return len(body.split())


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------

@dataclass
class PromptTemplate:
    """A reusable prompt template with ``{{var}}`` interpolation markers."""

    name: str
    body: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    required_vars: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Store (in-memory CRUD)
# ---------------------------------------------------------------------------

class TemplateStore:
    """In-memory store for :class:`PromptTemplate` objects."""

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}

    # -- CRUD ----------------------------------------------------------------

    def create(self, name: str, body: str, required_vars: list[str] | None = None) -> PromptTemplate:
        """Create and store a new template.

        Raises :exc:`ValueError` if *body* contains forbidden patterns.
        """
        errors = validate_no_executable(body)
        if errors:
            raise ValueError("; ".join(errors))

        vars_in_body = extract_variables(body)
        effective_required = required_vars if required_vars is not None else sorted(vars_in_body)

        template = PromptTemplate(
            name=name,
            body=body,
            required_vars=effective_required,
        )
        self._templates[template.id] = template
        return template

    def get(self, template_id: str) -> PromptTemplate | None:
        """Return the template with *template_id*, or *None*."""
        return self._templates.get(template_id)

    def update(
        self,
        template_id: str,
        *,
        name: str | None = None,
        body: str | None = None,
        required_vars: list[str] | None = None,
    ) -> PromptTemplate:
        """Update an existing template and bump ``updated_at``.

        Raises :exc:`ValueError` if the new body fails the safety check, or
        :exc:`LookupError` when the template does not exist.
        """
        template = self._templates.get(template_id)
        if template is None:
            raise LookupError(f"Template '{template_id}' not found")

        if body is not None:
            errors = validate_no_executable(body)
            if errors:
                raise ValueError("; ".join(errors))
            template.body = body

        if name is not None:
            template.name = name

        if required_vars is not None:
            template.required_vars = required_vars

        template.updated_at = datetime.now(timezone.utc)
        return template

    def delete(self, template_id: str) -> bool:
        """Remove the template.  Returns *True* if it existed, *False* otherwise."""
        if template_id in self._templates:
            del self._templates[template_id]
            return True
        return False

    def list(self) -> list[PromptTemplate]:
        """Return all templates (no particular ordering)."""
        return list(self._templates.values())


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render(template: PromptTemplate, variables: dict[str, str]) -> str:
    """Interpolate ``{{var}}`` markers with values from *variables*.

    Raises :exc:`MissingTemplateVariableError` when a variable listed in
    ``template.required_vars`` is absent from *variables*.
    """
    missing = [v for v in template.required_vars if v not in variables]
    if missing:
        raise MissingTemplateVariableError(missing[0])

    result = template.body
    for var_name in extract_variables(template.body):
        result = result.replace(f"{{{{{var_name}}}}}", variables.get(var_name, ""))

    return result
