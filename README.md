<div align="center">

# Agentix

**The pip ecosystem for sandboxed agents.**
Compose agents, tools, and benchmarks into a sandbox you can call as typed Python.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/Agentiix/Agentix)](https://github.com/Agentiix/Agentix)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docs](https://img.shields.io/badge/docs-agentiix.github.io-blue)](https://agentiix.github.io/)

</div>

## A SWE-bench rollout, end-to-end

```python
from agentix import RuntimeClient, bash, claude_code, swebench

async with RuntimeClient(sandbox_url) as c:
    await c.remote(bash.run, command=f"git clone {url} /testbed")
    cc = await c.remote(
        claude_code.run, instruction=task, workdir="/testbed",
    )
    s = await c.remote(swebench.score, instance=inst, patch=cc.patch)
```

Three pip-installed namespaces, composed in your trainer. Pyright
infers every return type. No YAML config, no codegen, no per-framework
registry call.

## What you get

| | |
|---|---|
| **Pip the agent** | `pip install agentix-claude-code` ships Claude Code as a typed namespace. Every integration is a regular Python wheel. |
| **Sandboxed by default** | Each `RuntimeClient` is an isolated Docker container. Let the agent `rm -rf`; your host is untouched. |
| **Typed remote calls** | `c.remote(fn, ...)` reads `fn`'s signature — Pyright infers return types end-to-end. Write `cc.patch`, not `cc["patch"]`. |
| **Per-namespace venvs** | Mix Aider, OpenHands, and your custom tool in one sandbox without resolving deps across them. |
| **Three call shapes, auto-detected** | `async def → T` is unary. `yield T` is streaming. Add `Channel[U]` for bidi. The wire follows your signature. |
| **Swappable backends** | `local` (Docker), `daytona`, `e2b` — pick one with `agentix deploy <name>`. `pip install agentix-deployment-*` adds another. |

## Install

```bash
pip install agentix agentix-bash agentix-files
```

Plus recipes from the [cookbook](https://github.com/Agentiix/agentix-cookbook):

```bash
git clone https://github.com/Agentiix/agentix-cookbook
pip install ./agentix-cookbook/claude-code ./agentix-cookbook/swebench
```

For framework development:

```bash
git clone https://github.com/Agentiix/Agentix && cd Agentix
pip install -e '.[dev]'
pip install -e primitives/bash -e primitives/files
```

## CLI

```bash
agentix build primitives/bash                              # build one namespace image
agentix build bash files claude-code -o my-agent:0.1.0     # bundle several namespaces
agentix deploy local --image my-agent:0.1.0                # run a sandbox + connect
agentix check                                              # smoke-import every installed namespace
```

## Write a namespace

```python
# src/agentix/myagent/__init__.py
async def run(instruction: str) -> str:
    return f"did: {instruction}"
```

```toml
# pyproject.toml
[project]
name = "agentix-myagent"
version = "0.1.0"

[project.entry-points."agentix.namespace"]
myagent = "agentix.myagent"

[tool.hatch.build.targets.wheel]
packages = ["src/agentix"]
```

`pip install agentix-myagent` and your users can do
`from agentix import myagent` → `await c.remote(myagent.run, ...)`.
The framework discovers the entry point at sandbox startup; the first
`c.remote(...)` call to your namespace spawns its worker.

## Two plugin axes

Only things that cross the host↔sandbox boundary go through entry-point
discovery:

| Axis | Entry-point group | What it ships | Built-ins |
|---|---|---|---|
| Namespaces | `agentix.namespace` | code that runs **inside the sandbox** | (third-party) |
| Deployments | `agentix.deployment` | backend that **provisions** the sandbox | `local` / `daytona` / `e2b` |

Everything else is host-side Python you import and call:

- **Trace pub/sub** — `agentix.trace.subscribe(fn)` to fan trace
  events into OTel, Sentry, or your own bus.
- **Spec resolvers, wire patterns, CLI verbs** — in-tree code; ship a
  separate `console_scripts` binary if you want a custom verb.

## Architecture

```
Orchestrator ──HTTP /_remote──► Runtime Server ──in-process call──► Namespace impl
                  (or)                            (Dispatcher)
            Socket.IO /socket.io/  ◄─── streams, bidi, logs, traces ───►
```

Discovery is lazy — one broken namespace doesn't block sandbox boot.
See [docs/reference/architecture.mdx](docs/reference/architecture.mdx)
and [docs/reference/namespace-protocol.mdx](docs/reference/namespace-protocol.mdx)
for protocol details.

## Links

- **Docs site:** [agentiix.github.io](https://agentiix.github.io/)
- **Cookbook:** [Agentiix/agentix-cookbook](https://github.com/Agentiix/agentix-cookbook)
- **Roadmap:** [ROADMAP.md](ROADMAP.md)
- **Contributing:** [docs/development.mdx](docs/development.mdx); conventions in [CLAUDE.md](CLAUDE.md)

## License

[MIT](LICENSE)
