"""Sandbox-side Anthropic service — exposes `/v1/messages` and ships
the raw Anthropic body to the host. No translation runs here.

The host's `Gateway` is what knows how to call OpenAI; it does the
Anthropic ↔ OpenAI conversion and returns an Anthropic-shaped
response that the sandbox renders straight back (as JSON or SSE).

Flow:

  agent → POST /v1/messages →
  sandbox emits `anthropic_complete` on `/abridge-anthropic` (raw body) →
  host's `Gateway.on_anthropic_complete` translates + calls AsyncOpenAI →
  emits `anthropic_complete:result` with an Anthropic-shaped dict →
  sandbox returns JSON, or renders SSE if `stream=true` was requested.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

import agentix

from .translate import anthropic_stream_sse

logger = logging.getLogger("agentix.bridge.anthropic.service")

NAMESPACE = "/abridge-anthropic"


# ── namespace ────────────────────────────────────────────────────


class _SandboxNamespace(agentix.Namespace):
    """Sandbox half. Owns one `anthropic_complete` request/reply
    round-trip per `/v1/messages` HTTP call."""

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
    """Start the Anthropic-shaped HTTP proxy inside the sandbox.

    `response_model` is what the proxy echoes back as `response.model`
    so the agent sees the model id it asked for. The actual upstream
    model id is the host's gateway concern.
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
    logger.info("abridge anthropic service %s started at %s", sid, handle.url)
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
            "shape": "anthropic",
            "response_model": response_model,
        }

    @app.post("/v1/messages/count_tokens")
    async def count_tokens(request: Request):
        body = await request.json()
        messages = body.get("messages", [])
        total = sum(len(str(m.get("content", ""))) for m in messages)
        return {"input_tokens": total // 4}

    @app.post("/v1/messages")
    async def messages(request: Request) -> Response:
        body = await request.json()
        stream_requested = bool(body.pop("stream", False))

        try:
            anthropic_resp = await ns.request(
                "anthropic_complete",
                body,
                timeout=request_timeout,
            )
        except agentix.RemoteSioError as exc:
            return JSONResponse(
                status_code=502,
                content={"error": {"type": exc.type, "message": exc.message}},
            )
        except Exception as exc:
            logger.exception("abridge anthropic request failed")
            return JSONResponse(
                status_code=500,
                content={"error": {"type": type(exc).__name__, "message": str(exc)}},
            )

        if not isinstance(anthropic_resp, dict):
            return JSONResponse(
                status_code=502,
                content={
                    "error": {
                        "type": "BadGateway",
                        "message": "host gateway returned non-dict response",
                    }
                },
            )

        # Force the response's model field to what the agent asked for.
        anthropic_resp = dict(anthropic_resp)
        anthropic_resp["model"] = response_model

        if stream_requested:
            sse_payload = anthropic_stream_sse(anthropic_resp)
            return StreamingResponse(
                _stream_bytes(sse_payload),
                media_type="text/event-stream",
            )
        return JSONResponse(content=anthropic_resp)

    return app


async def _stream_bytes(payload: bytes):
    yield payload


__all__ = [
    "NAMESPACE",
    "ServiceHandle",
    "start_service",
    "stop_service",
]
