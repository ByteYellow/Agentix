# Agentix

**Typed Python namespaces for sandbox-based agent workflows.**

Agentix lets you compose agents, datasets, and primitive tools into a sandbox and call them from your trainer or harness as if they were local typed Python:

```python
from agentix import RuntimeClient
from agentix.bash import Bash
from agentix.claude_code import ClaudeCode
from agentix.swebench import SWEBench

async with RuntimeClient(sandbox_url) as c:
    task   = await c.remote(SWEBench.get_task, idx=42)
    patch  = await c.remote(ClaudeCode.run, instruction=task.problem)
    reward = await c.remote(SWEBench.score, idx=42, patch=patch)
```

Every extension is a normal pip-installable distribution. No custom config file, no decorator at import time, no per-framework registry call. The user installs a wheel and the framework discovers it via Python entry points.

## What's here

<div class="grid cards" markdown>

-   **[Quick start](quick-start.md)** — Install, write your first namespace, run it inside a sandbox.

-   **[Writing namespaces](plugins.md#namespaces)** — The Namespace class pattern; `@staticmethod` methods; pyproject.toml setup.

-   **[Plugin authors guide](plugins.md)** — Reference for every extension axis: deployments, trace sinks, spec resolvers, wire patterns, CLI subcommands.

-   **[Architecture](architecture.md)** — How discovery / dispatch / wire patterns / the runtime server fit together.

-   **[Namespace protocol](namespace-protocol.md)** — The wire-format contract between caller and sandbox.

-   **[CLI](cli.md)** — `agentix build / install / deploy / check / plugins`.

</div>

## Six extension axes, one mechanism

Every axis discovers plugins via Python entry points:

| Axis | Entry-point group | Semantics |
|---|---|---|
| Namespaces | `agentix.namespace` | typed remote-callable surface |
| Deployments | `agentix.deployment` | sandbox lifecycle, select-one by name |
| Trace sinks | `agentix.trace_sink` | fan-out trace event consumers |
| Spec resolvers | `agentix.spec_resolver` | CLI input → namespace spec, chain |
| Wire patterns | `agentix.wire_pattern` | call-shape extensions |
| CLI subcommands | `agentix.cli` | `agentix <name>` discovery |

`pip install your-extension` plus one TOML block makes it live. `agentix plugins` lists every installed plugin across all six axes.

## Status

v0.1.0 — actively designed. Breaking changes are expected; the framework follows a strict no-backwards-compat policy. See [ROADMAP.md](https://github.com/Agentiix/Agentix/blob/master/ROADMAP.md) for what's coming.
