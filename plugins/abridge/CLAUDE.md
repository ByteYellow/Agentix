# agentix-bridge (`plugins/abridge`)

Workspace member of the Agentix monorepo. PyPI name `agentix-bridge`;
import path `agentix.bridge`. Repo-wide conventions (uv, typing, no
back-compat shims) live in the root `CLAUDE.md` — this file is only
the bridge-specific design.

## Scope

An **Anthropic / OpenAI-shaped HTTP proxy** for OpenAI-compatible
providers, bridged across the agentix sandbox boundary.

The agent (claude CLI, anthropic SDK, ...) inside the sandbox sees a
normal HTTP endpoint. The actual provider call lives on the **host**
— the sandbox-side service forwards the request over a Socket.IO
namespace; the host owns the credentials and the `AsyncOpenAI` client.

## Layout — one subpackage per provider-shape

```
agentix/bridge/
├── anthropic/     /v1/messages          service + OpenAIGateway + translate
└── oai/           /v1/chat/completions  service + OpenAIGateway (pass-through)
```

Each subpackage exports the same surface: `start_service` (sandbox-side,
invoked via `c.remote`), `stop_service`, a `*Gateway` host-side
`AsyncClientNamespace`, and `NAMESPACE`.

`oai` (not `openai`) avoids shadowing the upstream `openai` package.

## Bridge shape

- **Sandbox side** (`service.py`): FastAPI + uvicorn, an
  `agentix.Namespace` subclass. Ships the raw request body to the host;
  no LLM-vocabulary translation in the sandbox.
- **Host side** (`gateway.py`): an `agentix.AsyncClientNamespace` that
  owns the `AsyncOpenAI` client, does any translation, and answers.
- **`translate.py`**: pure Anthropic ↔ OpenAI converters, no I/O.

Gateways are named by upstream backend: `anthropic.OpenAIGateway` =
"Claude-shaped interface, OpenAI upstream". Future: `GeminiGateway`.

## Reserved namespaces

`/abridge-anthropic`, `/abridge-openai`. Round-trip events follow the
`agentix.Namespace.request(...)` convention: `<op>` /  `<op>:result` /
`<op>:error`, correlated by `request_id`.

## Streaming

`stream=true` is served by buffering the upstream non-stream response
and replaying it as SSE. True chunk-by-chunk streaming over SIO is a
backlog item.
