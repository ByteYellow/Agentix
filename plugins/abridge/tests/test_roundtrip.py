"""End-to-end abridge round-trip with a stub host gateway.

Boots an agentix server in-process, registers a stub `AnthropicGateway`
whose AsyncOpenAI-like client returns a canned response, then pokes
the sandbox-side abridge service via httpx. Verifies the response is
shaped like an Anthropic message and the stub gateway saw exactly one
upstream call.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket

import agentix.bridge.anthropic
import httpx
import pytest
import uvicorn

from agentix import RuntimeClient

# ── Stub OpenAI client (subset that Gateway needs) ──


class _StubResp:
    def __init__(self, model: str) -> None:
        self._model = model

    def model_dump(self) -> dict:
        return {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "model": self._model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "hello from stub"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11},
        }


class _StubChatCompletions:
    def __init__(self, model: str) -> None:
        self._model = model
        self.calls: list[dict] = []

    async def create(self, **body) -> _StubResp:
        self.calls.append(body)
        return _StubResp(model=body.get("model", self._model))


class _StubChat:
    def __init__(self, model: str) -> None:
        self.completions = _StubChatCompletions(model)


class _StubClient:
    def __init__(self, model: str = "stub-model") -> None:
        self.chat = _StubChat(model)


# ── server fixture ──────────────────────────────────────────────


@pytest.fixture
async def runtime_url():
    """Boot the agentix runtime server in-process and yield its URL."""
    # Fresh import: ensure a clean worker per test.
    import importlib
    import sys

    for mod in (
        "agentix.runtime.server.app",
        "agentix.runtime.server",
    ):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    from agentix.runtime import server

    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        port = sk.getsockname()[1]

    config = uvicorn.Config(
        server.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="on",
    )
    uv_server = uvicorn.Server(config)
    task = asyncio.create_task(uv_server.serve())
    for _ in range(200):
        if uv_server.started:
            break
        await asyncio.sleep(0.05)
    assert uv_server.started, "uvicorn never started"

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        uv_server.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(task, timeout=5)


# ── tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_messages_round_trip_non_streaming(runtime_url):
    stub = _StubClient(model="stub-model")
    gateway = agentix.bridge.anthropic.OpenAIGateway(client=stub, upstream_model="stub-model")

    client = RuntimeClient(runtime_url)
    client.register_namespace(gateway)
    async with client as c:
        svc = await c.remote(
            agentix.bridge.anthropic.start_service,
            response_model="claude-3-5-sonnet-latest",
        )
        async with httpx.AsyncClient(base_url=svc.url, timeout=10) as http:
            r = await http.post(
                "/v1/messages",
                json={
                    "model": "claude-3-5-sonnet-latest",
                    "max_tokens": 64,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["type"] == "message"
        assert body["model"] == "claude-3-5-sonnet-latest"
        assert body["content"][0]["text"] == "hello from stub"
        assert body["usage"]["input_tokens"] == 7
        assert body["usage"]["output_tokens"] == 4

        with contextlib.suppress(Exception):
            await c.remote(agentix.bridge.anthropic.stop_service, handle=svc)

    assert len(stub.chat.completions.calls) == 1
    assert stub.chat.completions.calls[0]["model"] == "stub-model"


@pytest.mark.asyncio
async def test_anthropic_messages_streaming_replays_as_sse(runtime_url):
    """When the agent asks for `stream=true`, abridge buffers the
    upstream non-stream response and replays it as Anthropic SSE."""
    stub = _StubClient(model="stub-model")
    gateway = agentix.bridge.anthropic.OpenAIGateway(client=stub, upstream_model="stub-model")

    client = RuntimeClient(runtime_url)
    client.register_namespace(gateway)
    async with client as c:
        svc = await c.remote(
            agentix.bridge.anthropic.start_service,
            response_model="claude-3-5-sonnet-latest",
        )
        async with httpx.AsyncClient(base_url=svc.url, timeout=10) as http:
            r = await http.post(
                "/v1/messages",
                json={
                    "model": "claude-3-5-sonnet-latest",
                    "max_tokens": 64,
                    "stream": True,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        assert r.status_code == 200
        text = r.text
        # Required Anthropic SSE event sequence.
        assert "event: message_start" in text
        assert "event: content_block_start" in text
        assert "event: content_block_delta" in text
        assert "text_delta" in text
        assert "hello from stub" in text
        assert "event: message_stop" in text

        with contextlib.suppress(Exception):
            await c.remote(agentix.bridge.anthropic.stop_service, handle=svc)
