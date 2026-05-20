"""agentix.bridge.anthropic — Anthropic-shaped sandbox service.

Pair a sandbox `start_service` with a host `*Gateway`. The Gateway
suffix names the upstream provider:

    # Anthropic interface ← OpenAI upstream
    import agentix.bridge.anthropic as anthropic
    gateway = anthropic.OpenAIGateway(
        client=openai.AsyncOpenAI(base_url=..., api_key=...),
        upstream_model="anthropic/claude-3.5-sonnet",
    )
    client.register_namespace(gateway)

    svc = await c.remote(
        anthropic.start_service,
        response_model="claude-3-5-sonnet-latest",
    )
    # svc.url → set agent's ANTHROPIC_BASE_URL to this.
"""

from __future__ import annotations

from .gateway import OpenAIGateway
from .service import (
    NAMESPACE,
    ServiceHandle,
    start_service,
    stop_service,
)

__all__ = [
    "NAMESPACE",
    "OpenAIGateway",
    "ServiceHandle",
    "start_service",
    "stop_service",
]
