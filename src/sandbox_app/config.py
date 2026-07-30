"""Execution engine configuration.

All values can be overridden at runtime by setting the corresponding module-level
attribute so tests can tweak them without touching environment variables.
"""

from __future__ import annotations

# Maximum number of workflows that may execute concurrently.
# MVP default is 1 (sequential execution); the field is present so callers
# can read it and the value can be raised in future releases.
WORKFLOW_CONCURRENCY_LIMIT: int = 1

# Directory for snapshot JSON files.  None means a platform-appropriate
# temporary directory will be chosen at first use.
WORKFLOW_SNAPSHOT_DIR: str | None = None
