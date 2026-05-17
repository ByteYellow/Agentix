"""Entry-point discovery for the `agentix.namespace` plugin group.

Every namespace dist declares one entry under `agentix.namespace` in its
`pyproject.toml`:

    [project.entry-points."agentix.namespace"]
    bash = "agentix.bash"

The framework reads this at startup via `importlib.metadata.entry_points`.
This is one of the two host-side plugin axes (the other is
`agentix.deployment`, which goes through `agentix.deployment._plugin.Registry`).
The namespace axis uses bespoke discovery here instead of `Registry[T]`
because the multiplexer needs the raw `EntryPoint` objects to introspect
the dist's installed venv before importing — `Registry` would have
loaded everything eagerly.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

NAMESPACE_ENTRY_POINT_GROUP = "agentix.namespace"


def discover_entry_points() -> list[Any]:
    """Return every installed `agentix.namespace` entry point.

    Cheap: walks `importlib.metadata` dist metadata; nothing is imported.
    The multiplexer uses this in dev/test mode to know which namespaces
    exist without paying the import cost of every namespace.
    """
    eps = importlib.metadata.entry_points()
    # Python 3.10+: SelectableGroups with .select(); earlier: dict.
    if hasattr(eps, "select"):
        return list(eps.select(group=NAMESPACE_ENTRY_POINT_GROUP))
    return list(eps.get(NAMESPACE_ENTRY_POINT_GROUP, []))  # type: ignore[attr-defined]


__all__ = ["NAMESPACE_ENTRY_POINT_GROUP", "discover_entry_points"]
