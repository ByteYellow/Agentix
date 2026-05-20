"""Host-side gateways for the OpenAI-shaped sandbox service.

The sandbox speaks OpenAI Chat-Completions; the Gateway forwards to a
real upstream. No translation runs in either direction — the gateway
exists purely to keep credentials and the HTTP call host-side.

- `OpenAIGateway` — pass-through to any OpenAI-compatible endpoint.

Future:

- `GeminiGateway` — translate OpenAI → Gemini on the host.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agentix import AsyncClientNamespace

from .service import NAMESPACE

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger("agentix.bridge.oai.gateway")


class OpenAIGateway(AsyncClientNamespace):
    """OpenAI-shaped sandbox service → OpenAI host backend (pass-through).

    `upstream_model` overrides the agent's requested model on the call.
    """

    def __init__(self, client: AsyncOpenAI, *, upstream_model: str | None = None) -> None:
        super().__init__(NAMESPACE)
        self._client = client
        self._upstream_model = upstream_model

    async def on_openai_complete(self, payload: dict[str, Any]) -> None:
        req_id = payload.get("request_id")
        body = payload.get("data") or {}
        if not isinstance(req_id, str):
            logger.warning("abridge openai: dropped openai_complete with no request_id")
            return

        try:
            if self._upstream_model is not None:
                body["model"] = self._upstream_model
            body.pop("stream", None)
            resp = await self._client.chat.completions.create(**body)
            value = resp.model_dump()
        except Exception as exc:
            logger.exception("abridge openai: openai_complete failed")
            await self.emit(
                "openai_complete:error",
                {
                    "request_id": req_id,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                },
            )
            return

        await self.emit(
            "openai_complete:result",
            {"request_id": req_id, "value": value},
        )


__all__ = ["OpenAIGateway"]
