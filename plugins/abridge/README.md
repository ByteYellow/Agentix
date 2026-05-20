# abridge

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**abridge** is [Agentix](https://github.com/Agentiix/Agentix)'s
host-side bridge from agent rollouts to RL training. Every LLM call,
tool invocation, and reward emitted from inside an Agentix rollout
container flows out as a structured trace; abridge consumes that
stream, correlates events into per-rollout records, and hands them to
whatever sink your RL framework uses.

Analogous to [mbridge](https://github.com/ISEEKYAN/mbridge)
(HuggingFace ↔ Megatron-Core for models): abridge is Agentix ↔ RL
trainers for agents.

```
Agentix runtime              abridge (this package)            adapter (separate)
─────────────────            ─────────────────────             ──────────────────
trace.emit(...)      ──►   tap → correlate → Rollout   ──►   YourSink.push(...)
```

## Relationship to Agentix

abridge is an Agentix extension, not a competitor. It depends on the
Agentix runtime client and plugs in via plain Python — host-side hooks
(`agentix.trace.subscribe`, `RuntimeClient.traces()`), not the
`agentix.deployment` entry-point axis that Agentix reserves for
sandbox-provisioning backends. The framework only hands out
entry-point discovery for axes that cross the host↔container boundary;
everything else stays plain Python, and abridge follows that rule.

## What's in scope

- **Trace tap**: connect to an Agentix runtime, subscribe to its
  `TraceEvent` stream over Socket.IO.
- **Correlator**: join `llm_request` / `llm_response`,
  `tool_call` / `tool_result`, and terminal `reward` / `rollout_end`
  events by `call_id` into one `Rollout` per agent run.
- **Sink Protocol**: one async method (`push(rollout)`); framework
  adapters implement it and ship as separate packages.

## What's not in scope

- **Framework-specific wiring.** Sinks for any particular RL trainer
  live in their own adapter packages so abridge's dependency surface
  stays free of CUDA, Megatron, Ray, and similar heavy native deps.
  abridge defines the `Rollout` shape and the `Sink` Protocol;
  adapters depend on abridge to consume the first and implement the
  second.
- **LLM-call interception.** That's the in-tree
  `agentix.runtime.server.llm_proxy` reverse-proxy; abridge consumes
  the traces it emits but doesn't re-host it.

## Install

```bash
pip install abridge
```

## Quick start — local inspection

```bash
# In one shell: a running Agentix rollout container emitting traces
agentix deploy local --image my-agent:0.1.0
# → runtime_url=http://localhost:8000

# In another: ship every closed rollout to a JSONL file
abridge tap http://localhost:8000 --writer jsonl --out rollouts.jsonl
```

Each line of `rollouts.jsonl` is one `Rollout`:

```json
{
  "call_id": "01HXY...",
  "status": "closed",
  "llm_turns": [{"provider": "anthropic", "path": "/v1/messages", ...}],
  "tool_calls": [{"name": "bash", "arguments": {"command": "ls"}, "result": "..."}],
  "reward": 1.0,
  "steps": [...]
}
```

## Quick start — RL training pipeline

```python
import asyncio
import abridge

class MySink:
    async def push(self, rollout: abridge.Rollout) -> None:
        # Translate rollout into your framework's training-sample shape
        # and append to its buffer. The adapter package for your
        # framework, if one exists, ships a ready-made implementation.
        ...

asyncio.run(abridge.run("http://localhost:8000", MySink()))
```

## The `Rollout` shape

| Field        | Meaning                                                          |
|--------------|------------------------------------------------------------------|
| `call_id`    | The Agentix rollout correlation key                              |
| `status`     | `"closed"` once a terminal `reward` / `rollout_end` arrived      |
| `llm_turns`  | LLM round-trips, request paired with response                    |
| `tool_calls` | Tool invocations, call paired with result (by `id` if present)   |
| `reward`     | Terminal reward, if sandbox-side code emitted one                |
| `steps`      | Raw `TraceEvent`s, preserved verbatim                            |

`request_body` / `response_body` keep the provider's native shape —
Anthropic Messages vs OpenAI Chat-Completions look different on the
wire. abridge does **not** normalize across providers because every
training framework normalizes differently; the adapter does that
translation in `push(...)`.

## Writing a framework adapter

A framework adapter is a separate package that depends on `abridge`,
implements `abridge.Sink`, and (optionally) ships its own console
script. The whole adapter is usually one file:

```python
# my_framework_abridge/__init__.py
import abridge
from my_framework import DataBuffer    # framework-specific

class MySink:
    def __init__(self, buffer: DataBuffer):
        self.buffer = buffer

    async def push(self, rollout: abridge.Rollout) -> None:
        sample = _to_framework_sample(rollout)
        await self.buffer.append(sample)
```

## Why a separate package

- **Dependency hygiene.** Agentix is the agent-runtime framework; its
  install footprint should not pull in any RL trainer. Conversely, a
  framework adapter pulls in the trainer but should not pull in the
  entire sandbox/runtime stack. abridge sits in the middle: the small
  layer both sides depend on.
- **Independent release cadence.** Agentix's wire layout and the
  rollout / sink Protocol move at different speeds. Pinning them in
  the same package would force users into lock-step upgrades.

## License

[MIT](LICENSE)
