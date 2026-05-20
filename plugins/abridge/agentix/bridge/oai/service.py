"""Sandbox-side OpenAI-shaped service — exposes `/v1/chat/completions`
and forwards each call verbatim to the host via `/abridge-openai`.

No translation is needed: the agent already speaks OpenAI; we just
relay the request body to the host and pass the response straight
back. Use this when your agent SDK is OpenAI-compatible (the OpenAI
SDK itself, LiteLLM, instructor, ...).

Flow:

  agent → POST /v1/chat/completions →
  abridge sandbox emits `openai_complete` on `/abridge-openai` →
  host's `Gateway.on_openai_complete` calls AsyncOpenAI →
  emits `openai_complete:result` → sandbox returns the body to agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

import agentix

logger = logging.getLogger("agentix.bridge.oai.service")

NAMESPACE = "/abridge-openai"


# ── namespace ────────────────────────────────────────────────────


class _SandboxNamespace(agentix.Namespace):
    namespace = NAMESPACE


_namespace_singleton: _SandboxNamespace | None = None


def _get_namespace() -> _SandboxNamespace:
    global _namespace_singleton
    if _namespace_singleton is None:
        _namespace_singleton = _SandboxNamespace()
        agentix.register_namespace(_namespace_singleton)
    return _namespace_singleton


# ── service ──────────────────────────────────────────────────────


@dataclass
class ServiceHandle:
    id: str
    url: str
    port: int


_running: dict[str, _RunningService] = {}


@dataclass
class _RunningService:
    handle: ServiceHandle
    server: uvicorn.Server
    task: asyncio.Task


async def start_service(
    *,
    response_model: str,
    host: str = "127.0.0.1",
    port: int = 0,
    request_timeout: float = 600.0,
) -> ServiceHandle:
    """Start the OpenAI-shaped HTTP proxy inside the sandbox.

    `response_model` is the model id the proxy echoes back to the
    agent. The actual upstream model is the host gateway's concern.
    """
    ns = _get_namespace()
    app = _build_app(
        ns=ns,
        response_model=response_model,
        request_timeout=request_timeout,
    )
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    for _ in range(200):
        if server.started and server.servers:
            break
        await asyncio.sleep(0.05)
    else:
        raise RuntimeError("abridge service did not start within 10s")

    bound_port = port
    for s in server.servers:
        for sock in s.sockets:
            bound_port = sock.getsockname()[1]
            break
        if bound_port:
            break

    import uuid as _uuid

    sid = _uuid.uuid4().hex
    handle = ServiceHandle(
        id=sid,
        url=f"http://{host}:{bound_port}",
        port=bound_port,
    )
    _running[sid] = _RunningService(handle=handle, server=server, task=task)
    logger.info("abridge openai service %s started at %s", sid, handle.url)
    return handle


async def stop_service(handle: ServiceHandle) -> None:
    rec = _running.pop(handle.id, None)
    if rec is None:
        return
    rec.server.should_exit = True
    try:
        await asyncio.wait_for(rec.task, timeout=5.0)
    except TimeoutError:
        rec.server.force_exit = True
        await rec.task


# ── FastAPI app ──────────────────────────────────────────────────


def _build_app(
    *,
    ns: _SandboxNamespace,
    response_model: str,
    request_timeout: float,
) -> FastAPI:
    app = FastAPI()

    @app.get("/")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "abridge",
            "shape": "openai",
            "response_model": response_model,
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        body = await request.json()
        stream_requested = bool(body.pop("stream", False))

        try:
            resp = await ns.request("openai_complete", body, timeout=request_timeout)
        except agentix.RemoteSioError as exc:
            return JSONResponse(
                status_code=502,
                content={"error": {"type": exc.type, "message": exc.message}},
            )
        except Exception as exc:
            logger.exception("abridge openai request failed")
            return JSONResponse(
                status_code=500,
                content={"error": {"type": type(exc).__name__, "message": str(exc)}},
            )

        if not isinstance(resp, dict):
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "type": "BadGateway",
                        "message": "host gateway returned non-dict response",
                    }
                },
            )

        # Rewrite the response model to what the agent expects.
        resp = dict(resp)
        resp["model"] = response_model

        if stream_requested:
            return StreamingResponse(
                _openai_sse_chunks(resp),
                media_type="text/event-stream",
            )
        return JSONResponse(content=resp)

    return app


async def _openai_sse_chunks(resp: dict):
    """Replay a non-streaming OpenAI response as a single-chunk SSE
    stream — the same buffer-and-replay strategy we use for Anthropic.
    """
    choice = (resp.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = message.get("content") or ""
    model = resp.get("model", "")
    chunk_id = resp.get("id") or "chatcmpl-buffered"

    first = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": text},
                "finish_reason": None,
            }
        ],
    }
    last = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": choice.get("finish_reason", "stop"),
            }
        ],
        "usage": resp.get("usage"),
    }
    yield f"data: {json.dumps(first)}\n\n".encode()
    yield f"data: {json.dumps(last)}\n\n".encode()
    yield b"data: [DONE]\n\n"


__all__ = [
    "NAMESPACE",
    "ServiceHandle",
    "start_service",
    "stop_service",
]
