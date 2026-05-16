# Agentix

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/Agentiix/Agentix)](https://github.com/Agentiix/Agentix)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docs](https://img.shields.io/badge/docs-agentiix.github.io-blue)](https://agentiix.github.io/)

**Agentix** is a sandbox framework for agentic RL training and evaluation,
providing three core capabilities:

1. **Sandboxed agent execution**: Each rollout runs inside an isolated
   container. Built-in backends: `local` (Docker), `daytona`, `e2b`.
   Adding another is `pip install agentix-deployment-<name>`.
2. **Pip-installable agent / dataset / tool extensions**: Each
   extension is a standalone Python wheel with one entry-point block.
   The framework discovers it via `importlib.metadata` — no YAML,
   no decorator, no per-framework registry call.
3. **Typed remote dispatch**: Compose namespaces in your trainer or
   evaluator with `c.remote(fn, ...)`; Pyright infers return types
   end-to-end from `fn`'s signature.

Agentix ships **bash** and **files** as in-tree primitives. The
[agentix-cookbook](https://github.com/Agentiix/agentix-cookbook)
repository provides working recipes for:

- **Claude Code** — `pip install agentix-claude-code` wraps the
  Anthropic CLI as a typed namespace.
- **SWE-bench Verified** — `pip install agentix-swebench` wraps the
  official [`swebench`](https://github.com/swe-bench/SWE-bench) package
  (test specs, log parsers, `get_eval_report`) and exposes
  `score(instance, patch)` as a single remote call.

Agentix integrates with the following RL post-training frameworks via
[agentix-llm-proxy](https://github.com/Agentiix/agentix-llm-proxy)
(the LLM-call interception layer that emits Agentix trace events
from any agent CLI):

- [**slime**](https://github.com/THUDM/slime) — traces fan into
  slime's data buffer for on-policy rollouts.

## Table of Contents

- [End-to-end example](#end-to-end-example)
- [Architecture](#architecture)
- [Install](#install)
- [CLI](#cli)
- [Write a namespace](#write-a-namespace)
- [Two plugin axes](#two-plugin-axes)
- [Links](#links)

## End-to-end example

A SWE-bench Verified rollout — clone the repo, run Claude Code, score
the patch — composed from three pip-installed namespaces:

```python
from datasets import load_dataset
from agentix import RuntimeClient, bash, claude_code, swebench

inst = dict(load_dataset("princeton-nlp/SWE-bench_Verified", split="test")[0])

async with RuntimeClient(sandbox.runtime_url) as c:
    await c.remote(
        bash.run,
        command=(
            f"git clone https://github.com/{inst['repo']}.git /testbed && "
            f"cd /testbed && git checkout {inst['base_commit']}"
        ),
    )
    cc = await c.remote(
        claude_code.run,
        instruction=inst["problem_statement"],
        workdir="/testbed",
        env={"ANTHROPIC_API_KEY": api_key},
    )
    diff = await c.remote(
        bash.run, command="cd /testbed && git add -A && git diff --cached",
    )
    s = await c.remote(swebench.score, instance=inst, patch=diff.stdout)
```

## Architecture

```
Orchestrator ──HTTP /_remote──► Runtime Server ──fork──► Namespace worker (per ns)
   (trainer)                       (multiplexer)            (own venv, own PATH)
                                        ▲
            Socket.IO /socket.io/ ◄──────┴──── streams, bidi, logs, traces
```

**Components:**

- **Runtime server**: one process per sandbox. Routes `POST /_remote`
  (unary) and Socket.IO events (streams / bidi / logs / traces) to
  per-namespace workers spawned lazily on first dispatch.
- **Namespace worker**: subprocess that imports the namespace package
  using its own venv interpreter. PATH is prepended with
  `/nix/<short>/bin/` so user code calls `subprocess.run("git", ...)`
  without absolute paths.
- **Deployment**: host-side backend (`local`, `daytona`, `e2b`, or a
  third-party `agentix-deployment-*` wheel) that creates the sandbox
  container and returns its `runtime_url`.

Discovery is via `importlib.metadata.entry_points`, lazy at first
call. A broken namespace fails its own calls but never blocks
sandbox boot.

## Install

```bash
pip install agentix agentix-bash agentix-files
```

Cookbook recipes (Claude Code + SWE-bench scorer):

```bash
git clone https://github.com/Agentiix/agentix-cookbook
pip install ./agentix-cookbook/claude-code ./agentix-cookbook/swebench
```

Framework development:

```bash
git clone https://github.com/Agentiix/Agentix && cd Agentix
pip install -e '.[dev]'
pip install -e primitives/bash -e primitives/files
```

## CLI

```bash
agentix build primitives/bash                              # one namespace image
agentix build bash files claude-code -o my-agent:0.1.0     # bundle several
agentix deploy local --image my-agent:0.1.0                # run a sandbox
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

`pip install agentix-myagent` is the entire setup. Caller-side:

```python
from agentix import myagent
result = await c.remote(myagent.run, instruction="...")
```

Three call shapes are auto-detected from your function signature:
`async def → T` is unary, `yield T` is server-streaming Socket.IO,
adding a `Channel[U]` parameter is bidi.

## Two plugin axes

Only things that cross the host↔sandbox boundary go through
entry-point discovery:

| Axis | Entry-point group | What it ships | Built-ins |
|---|---|---|---|
| Namespaces | `agentix.namespace` | code that runs **inside the sandbox** | (third-party only) |
| Deployments | `agentix.deployment` | backend that **provisions** the sandbox | `local`, `daytona`, `e2b` |

Host-side hooks (trace pub/sub, spec resolvers, CLI verbs) are plain
Python — `import` and call. `agentix.trace.subscribe(fn)` is the
single line that ships every namespace's `trace.emit(...)` events
into OpenTelemetry, Sentry, or your own bus.

## Links

- **Docs site**: [agentiix.github.io](https://agentiix.github.io/)
- **Cookbook**: [github.com/Agentiix/agentix-cookbook](https://github.com/Agentiix/agentix-cookbook)
- **LLM-proxy / RL bridge**: [github.com/Agentiix/agentix-llm-proxy](https://github.com/Agentiix/agentix-llm-proxy)
- **Roadmap**: [ROADMAP.md](ROADMAP.md)
- **Contributing**: [docs/development.mdx](docs/development.mdx); conventions in [CLAUDE.md](CLAUDE.md)

## License

[MIT](LICENSE)
