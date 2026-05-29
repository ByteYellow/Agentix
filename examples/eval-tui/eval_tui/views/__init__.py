"""TUI view widgets, one per Agentix surface."""

from __future__ import annotations

from .catalog import CatalogView
from .observability import ObservabilityView
from .overview import OverviewView
from .placeholder import PlaceholderView
from .rollouts import RolloutsView
from .sandboxes import SandboxesView

__all__ = [
    "CatalogView",
    "ObservabilityView",
    "OverviewView",
    "PlaceholderView",
    "RolloutsView",
    "SandboxesView",
]
