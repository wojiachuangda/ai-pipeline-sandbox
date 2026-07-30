"""Triggers for task scheduling — Cron and Event."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Standard 5-field cron: minute hour day-of-month month day-of-week
# Each token can be *, N, */N, N-M, N-M/N, or comma-separated combinations.
_TOKEN = r"\*|\d+|\*/\d+|\d+-\d+(?:/\d+)?"
_FIELD = rf"{_TOKEN}(?:,{_TOKEN})*"

CRON_PATTERN = re.compile(rf"^({_FIELD}) ({_FIELD}) ({_FIELD}) ({_FIELD}) ({_FIELD})$")


def validate_cron(expression: str) -> None:
    """Raise ValueError if *expression* is not a valid 5-field cron string."""
    if not CRON_PATTERN.match(expression):
        raise ValueError(f"Invalid cron expression: {expression!r}")


@dataclass(frozen=True)
class CronTrigger:
    expression: str

    def __post_init__(self) -> None:
        validate_cron(self.expression)


@dataclass(frozen=True)
class EventTrigger:
    event_type: str


Trigger = CronTrigger | EventTrigger
