"""Shared value types for the TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunSpec:
    """Everything the Rollouts view needs to drive `agentix.runner`."""

    dataset: Any
    agent: Any
    provider: Any
    bundle: str
    model: str | None = None
    instances: list[dict[str, Any]] = field(default_factory=list)
    n_concurrent: int = 4
