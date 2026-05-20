"""Anthropic ↔ OpenAI Chat-Completions translation helpers.

Pure functions — no HTTP, no I/O. The sandbox-side proxy uses these
to (a) shape the inbound Anthropic body for the host's AsyncOpenAI
call, and (b) shape the host's OpenAI response back into Anthropic.
"""

from __future__ import annotations

import json
import uuid
from typing import Any


def anthropic_to_openai_body(
    anthropic_body: dict,
    *,
    upstream_model: str,
) -> dict:
    """Convert an Anthropic `/v1/messages` body into OpenAI Chat-Completions
    shape, swapping the model id for `upstream_model`."""
    messages: list[dict] = []
    system = anthropic_body.get("system")
    if isinstance(system, str):
        messages.append({"role": "system", "content": system})
    elif isinstance(system, list):
        text = " ".join(b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text")
        if text:
            messages.append({"role": "system", "content": text})
    messages.extend(_anthropic_to_openai_messages(anthropic_body.get("messages", [])))

    body: dict = {
        "model": upstream_model,
        "messages": messages,
        "max_tokens": anthropic_body.get("max_tokens", 4096),
        "temperature": anthropic_body.get("temperature", 1.0),
    }
    openai_tools = _anthropic_to_openai_tools(anthropic_body.get("tools"))
    if openai_tools:
        body["tools"] = openai_tools
    return body


def openai_to_anthropic_response(openai_resp: dict, *, response_model: str) -> dict:
    """Convert a non-streaming OpenAI ChatCompletion dict into the
    Anthropic `/v1/messages` non-stream response shape."""
    choice = (openai_resp.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = openai_resp.get("usage") or {}

    content: list[dict] = []
    text = message.get("content")
    if text:
        content.append({"type": "text", "text": text})
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments", "{}"))
        except json.JSONDecodeError:
            args = {"_raw": fn.get("arguments", "")}
        content.append(
            {
                "type": "tool_use",
                "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                "name": fn.get("name", ""),
                "input": args,
            }
        )
    if not content:
        content.append({"type": "text", "text": ""})

    finish = choice.get("finish_reason", "")
    stop_reason = "end_turn"
    if finish == "tool_calls" or any(b["type"] == "tool_use" for b in content):
        stop_reason = "tool_use"
    elif finish == "length":
        stop_reason = "max_tokens"

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": response_model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


def anthropic_stream_sse(anthropic_response: dict) -> bytes:
    """Render a complete Anthropic response as a single buffered SSE
    stream. We don't pipe true OpenAI streaming chunks through SIO;
    instead the host returns the full OpenAI response and the sandbox
    fakes the SSE event sequence from it. claude CLI accepts this.
    """
    parts: list[bytes] = []
    msg_id = anthropic_response.get("id") or f"msg_{uuid.uuid4().hex[:24]}"
    model = anthropic_response.get("model", "")
    content = anthropic_response.get("content") or []
    usage = anthropic_response.get("usage") or {}
    stop_reason = anthropic_response.get("stop_reason", "end_turn")

    parts.append(
        _sse(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": 0,
                    },
                },
            },
        )
    )

    for idx, block in enumerate(content):
        if block.get("type") == "text":
            text = block.get("text", "")
            parts.append(
                _sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": idx,
                        "content_block": {"type": "text", "text": ""},
                    },
                )
            )
            if text:
                parts.append(
                    _sse(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": idx,
                            "delta": {"type": "text_delta", "text": text},
                        },
                    )
                )
            parts.append(
                _sse(
                    "content_block_stop",
                    {
                        "type": "content_block_stop",
                        "index": idx,
                    },
                )
            )
        elif block.get("type") == "tool_use":
            parts.append(
                _sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": idx,
                        "content_block": {
                            "type": "tool_use",
                            "id": block.get("id"),
                            "name": block.get("name", ""),
                            "input": {},
                        },
                    },
                )
            )
            input_json = json.dumps(block.get("input") or {})
            parts.append(
                _sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": idx,
                        "delta": {"type": "input_json_delta", "partial_json": input_json},
                    },
                )
            )
            parts.append(
                _sse(
                    "content_block_stop",
                    {
                        "type": "content_block_stop",
                        "index": idx,
                    },
                )
            )

    parts.append(
        _sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": usage.get("output_tokens", 0)},
            },
        )
    )
    parts.append(_sse("message_stop", {"type": "message_stop"}))
    return b"".join(parts)


# ── internal helpers ──────────────────────────────────────────────


def _anthropic_to_openai_messages(messages: list[dict]) -> list[dict]:
    result: list[dict] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            result.append({"role": role, "content": str(content)})
            continue

        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                result.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": block.get("id", str(uuid.uuid4())),
                                "type": "function",
                                "function": {
                                    "name": block.get("name", ""),
                                    "arguments": json.dumps(block.get("input", {})),
                                },
                            }
                        ],
                    }
                )
            elif block.get("type") == "tool_result":
                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": str(block.get("content", "")),
                    }
                )
        if parts:
            result.append({"role": role, "content": "\n".join(parts)})
    return result


def _anthropic_to_openai_tools(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        }
        for t in tools
    ]


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


__all__ = [
    "anthropic_stream_sse",
    "anthropic_to_openai_body",
    "openai_to_anthropic_response",
]
