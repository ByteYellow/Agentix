"""agentix.bridge.oai — OpenAI-shaped sandbox service.

Pair a sandbox `start_service` with a host `*Gateway`. The Gateway
suffix names the upstream provider:

    # OpenAI interface ← OpenAI upstream (pass-through, credentials host-side)
    import agentix.bridge.oai as openai_bridge
    gateway = openai_bridge.OpenAIGateway(
        client=openai.AsyncOpenAI(base_url=..., api_key=...),
        upstream_model="gpt-4o-mini",
    )
    client.register_namespace(gateway)

    svc = await c.remote(
        openai_bridge.start_service,
        response_model="gpt-4o-mini",
    )
    # svc.url → set agent's OPENAI_BASE_URL to this.
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
