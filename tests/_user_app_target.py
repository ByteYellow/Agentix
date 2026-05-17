"""Stands in for a user's own module — NO entry-point declaration.

Lives in tests/ so the worker subprocess can `import _user_app_target`
after we add tests/ to PYTHONPATH. This module deliberately does NOT
register under `agentix.namespace` anywhere — its presence in the
multiplexer's routing table happens entirely through the on-demand
auto-register path on first dispatch.
"""

from __future__ import annotations


async def greet(name: str) -> str:
    return f"hello {name}"


async def add(a: int, b: int) -> int:
    return a + b
