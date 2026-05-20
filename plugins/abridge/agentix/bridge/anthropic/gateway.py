"""Host-side gateways for the Anthropic-shaped sandbox service.

Each Gateway is a different *upstream* backend. The sandbox always
speaks Anthropic's `/v1/messages`; the Gateway is what translates and
forwards on the host side.

Today:

- `OpenAIGateway` — Anthropic interface backed by OpenAI Chat
  Completions (any OpenAI-compatible endpoint: OpenRouter, model-eval,
  vLLM, the real OpenAI API, ...).

Future:

- `GeminiGateway` — Anthropic interface backed by Google Gemini.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agentix import AsyncClientNamespace

from .service import NAMESPACE
from .translate import (
    anthropic_to_openai_body,
    openai_to_anthropic_response,
)

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger("agentix.bridge.anthropic.gateway")


class OpenAIGateway(AsyncClientNamespace):
    """Anthropic-shaped sandbox service → OpenAI host backend.

    The sandbox emits `anthropic_complete` with the raw Anthropic body.
    This gateway translates that body to OpenAI Chat-Completions shape,
    calls `client.chat.completions.create(**body)`, translates the
    response back to Anthropic shape, and emits
    `anthropic_complete:result`.

    `upstream_model` overrides the agent's requested model on the
    upstream call. (The sandbox echoes the agent-requested model back
    in `response.model`, so the agent doesn't see the substitution.)
    """

    def __init__(self, client: AsyncOpenAI, *, upstream_model: str) -> None:
        super().__init__(NAMESPACE)
        self._client = client
        self._upstream_model = upstream_model

    async def on_anthropic_complete(self, payload: dict[str, Any]) -> None:
        req_id = payload.get("request_id")
        anthropic_body = payload.get("data") or {}
        if not isinstance(req_id, str):
            logger.warning("abridge anthropic: dropped anthropic_complete with no request_id")
            return

        try:
            openai_body = anthropic_to_openai_body(
                anthropic_body,
                upstream_model=self._upstream_model,
            )
            openai_body.pop("stream", None)
            resp = await self._client.chat.completions.create(**openai_body)
            anthropic_resp = openai_to_anthropic_response(
                resp.model_dump(),
                response_model=anthropic_body.get("model", ""),
            )
        except Exception as exc:
            logger.exception("abridge anthropic: anthropic_complete failed")
            await self.emit(
                "anthropic_complete:error",
                {
                    "request_id": req_id,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                },
            )
            return

        await self.emit(
            "anthropic_complete:result",
            {"request_id": req_id, "value": anthropic_resp},
        )


__all__ = ["OpenAIGateway"]
