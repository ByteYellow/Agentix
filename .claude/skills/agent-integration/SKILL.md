---
name: agent-integration
description: Use this skill when the user wants to add a new agent closure to Agentix-Agents-Hub, a new dataset/verifier closure to Agentix-Datasets, or port an existing integration from harbor (harbor-framework/harbor) or llm-agents.nix (numtide/llm-agents.nix) into Agentix's closure convention. Triggers include phrases like "add <name> to agents-hub", "migrate <name> from harbor", "port <name> from llm-agents.nix", "wrap the <cli> CLI as an Agentix closure", "integrate <tool> as a closure service", or any mention of building/adapting a new CLI-driven agent or evaluation harness to run inside an Agentix sandbox.
version: 1.0.0
---

# Agent Integration

Guide for packaging an external CLI-based agent (or a dataset/verifier) into an **Agentix closure service** — a Docker image that satisfies the closure convention and plugs into any Agentix sandbox by name.

Source material lives in two upstream repos at sibling paths:

- **harbor** — Python service logic: how to install, env-configure, and invoke the CLI. Path: `../harbor` (relative to the Agentix repo root).
- **llm-agents.nix** — Nix binary packaging: how to pin versions and produce a hermetic `bin/<cli>`. Path: `../llm-agents.nix`.

This skill fuses the two into the Agentix closure shape described below.

## When to activate

- "add claude-code / aider / opencode / gemini-cli / qwen-code ... to agents-hub"
- "migrate <name> from harbor" — harbor is the source of truth for CLI invocation and env.
- "port <name> from llm-agents.nix" — llm-agents.nix is the source of truth for the derivation.
- "wrap the <X> CLI as an Agentix closure"
- "add a new dataset closure (e.g. humaneval, mbpp, livecodebench) to Agentix-Datasets"
- The user references either repo as a reference / starting point for a new closure.

Do **not** use this skill for tasks that only touch `Agentix` core (runtime server, deployment, closure protocol). Those are core-substrate edits, not integrations.

## The Agentix closure ABI (non-negotiable)

The final image must satisfy:

- `VOLUME /nix`
- `/nix/store/<hash>-*/` — content-addressed Nix deps for everything the closure needs.
- `/nix/entry/bin/start` — executable entry point, invoked with **no CLI args**.
- `/nix/entry/manifest.json` — `ClosureManifest` JSON with `abi == AGENTIX_CLOSURE_ABI`. This file is what marks `/mnt/<ns>` as a closure; without it the runtime ignores the mount. Emit it from your build (e.g. `agentix.closure.write_manifest(...)` or a `postInstall` `cat > $out/manifest.json`).

At runtime, Agentix forks `start` with `AGENTIX_SOCKET=/tmp/agentix/<ns>.sock` in env. `start` must bind a Unix-socket HTTP server on that path and serve the agent's endpoints. `GET /` should return the same manifest JSON (runtime uses it only as a readiness probe); `POST /run` (or similar) is where the agent actually does work.

See `docs/closure-protocol.md` in Agentix for the full protocol.

## Each closure is self-contained

Every closure directory is an **independently maintained unit**. This is deliberately the opposite of llm-agents.nix's monorepo-with-blueprint organization.

- Own `Dockerfile`. No shared template file referenced across closures — if two closures need the same build steps, each keeps its own copy.
- Own `default.nix`. No `import ../<other>/` across closure boundaries, no shared `lib/` or `overlays/` at the repo root.
- Own version pins. Two closures can run different versions of the same CLI — that's fine.
- Own lifecycle: build, test, bump, ship without touching siblings.

A single `default.nix` per closure is preferred (inline the binary derivation as a `let` binding); only split into a separate `package.nix` when the file gets unwieldy. The cross-closure prohibition is absolute: no sharing between closures via a repo-level `lib/` or `import ../`. Reference material in the Agentix core repo (e.g. `tests/closure-docker/Dockerfile`) is meant to be **copy-pasted as a starting point**, not referenced at build time via `-f ../../Agentix/tests/closure-docker/Dockerfile`.

## Target service layout

Every migrated closure lives at `Agentix-Agents-Hub/<name>/` (agents) or `Agentix-Datasets/<name>/` (datasets) with this shape:

```
<name>/
├── start.sh          # shell entry — substituted at nix build, installed as bin/start
├── service.py        # FastAPI app; POST /run invokes the CLI, returns structured result
├── default.nix       # single-file Nix: binary derivation(s) + python env + start, composed via symlinkJoin
└── Dockerfile        # closure image: nix-build → copy /nix/store → emit Agentix-shaped layer
```

`start.sh` and `default.nix` are the two mandatory files. `service.py` is mandatory for agents (they need HTTP dispatch on `/run`); for very thin passthroughs you can inline into start.sh, but the Python service is the default.

**Prefer a single `default.nix`.** Inline the binary derivation as a `let` binding (`claude = pkgs.stdenv.mkDerivation { ... }`) rather than splitting into a separate `package.nix`. The split is a llm-agents.nix pattern driven by Blueprint's `perSystem`/`flake` arg injection — we have no such injection and no Blueprint. Only split into `package.nix` if the file genuinely becomes unwieldy (100+ lines); otherwise keep it all in `default.nix` so a reader sees the whole graph in one place.

## Source mapping

**The governing principle: locate → extract, don't copy.** Both upstream repos carry a lot of machinery we don't use (trajectory parsing, Blueprint flakes, Pydantic config, overlays, custom lib hooks, update scripts). For each new closure you only need a few facts out of each source file — everything else goes straight in the bin.

### From harbor — lift the CLI invocation

Open `harbor/src/harbor/agents/installed/<name>.py` and lift just these:

- **argv** that `run()` builds for the CLI (e.g. `claude -p <prompt> --output-format=stream-json --permission-mode=bypassPermissions --print --`). Port it literally into `service.py`'s subprocess call.
- **fixed env** the agent hardcodes (`DISABLE_AUTOUPDATER=1`, `IS_SANDBOX=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, …). Put these in `start.sh`.
- **caller-provided env** the agent reads at runtime (`ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, model selection, …). Expose via `POST /run` body's `env` field; orchestrator passes them per-request.

Ignore the rest: `BaseInstalledAgent` / `CliFlag` / `EnvVar` / Pydantic descriptors, `populate_context_post_run` + ATIF trajectory conversion, `exec_as_agent`/`exec_as_root` wrappers, multi-backend (Docker/Modal/E2B/…) abstraction, the `install()` `apt-get`/`npm install` commands (Nix replaces them).

**Skills / memory / MCP registration** (harbor copies from host-side paths like `~/.claude/skills`, `self.skills_dir`, `self.memory_dir`): port this as **request-body data dicts**, not filesystem paths. A closure has no "host" — the orchestrator ships content inline. Pattern:

```json
{
  "skills":  {"skill-a/SKILL.md": "...", "skill-a/refs/x.md": "..."},
  "memory":  {"MEMORY.md": "...", "user.md": "..."},
  "mcp_servers": [{"name": "fs", "transport": "stdio", "command": "npx", "args": ["..."]}]
}
```

`service.py` materializes these under `$CLAUDE_CONFIG_DIR` (or the agent's config dir) right before invoking the CLI. Reject keys that are absolute or contain `..`. Skip the whole mechanism if your agent doesn't use any of it.

### From llm-agents.nix — lift the source descriptor

Open `llm-agents.nix/packages/<name>/{package.nix,hashes.json}` and lift just these:

- **source descriptor** (URL template + platform map, `fetchFromGitHub` args, or npm tarball URL).
- **version + hash values** (merge `hashes.json` contents into the derivation — no side-car).
- **wrap env / PATH additions** from `postFixup` / `postInstall` (only those the agent actually needs).

Ignore the rest: Blueprint flake auto-discovery, `overlays/default.nix`, custom hooks (`wrapBuddy`, `versionCheckHook`, `versionCheckHomeHook`, `fetchNpmDepsWithPackuments` — drop these or substitute plain nixpkgs equivalents), `__noChroot`, `passthru.category`, `update.py`.

Three derivation shapes cover ~95% of cases. Each uses `rec` so the version appears exactly once and the URL reuses it:

**Binary blob** (claude-code, gemini-cli, …):
```nix
{ lib, stdenv, fetchurl, makeWrapper }:
stdenv.mkDerivation (finalAttrs: {
  pname = "<name>";
  version = "2.1.114";
  src = fetchurl {
    url  = "https://<cdn>/${finalAttrs.version}/linux-x64/<binary>";
    hash = "sha256-...";
  };
  dontUnpack = true;
  nativeBuildInputs = [ makeWrapper ];
  installPhase = ''install -Dm755 $src $out/bin/<binary>'';
  postFixup = ''wrapProgram $out/bin/<binary> --set DISABLE_AUTOUPDATER 1'';
})
```
For multi-platform, extend with `src = fetchurl (platformMap.${stdenv.hostPlatform.system})`. Keep the platform table inline.

**npm package** (pi, opencode, …):
```nix
{ buildNpmPackage, fetchurl }:
buildNpmPackage (finalAttrs: {
  pname = "<name>";
  version = "0.67.68";
  src = fetchurl {
    url  = "https://registry.npmjs.org/<pkg>/-/<pkg>-${finalAttrs.version}.tgz";
    hash = "sha256-...";
  };
  npmDepsHash = "sha256-...";
  dontNpmBuild = true;
})
```

**Rust from source** (code, agent-browser, …):
```nix
{ rustPlatform, fetchFromGitHub }:
rustPlatform.buildRustPackage (finalAttrs: {
  pname = "<name>";
  version = "0.6.93";
  src = fetchFromGitHub {
    owner = "..."; repo = "..."; tag = "v${finalAttrs.version}";
    hash = "sha256-...";
  };
  cargoHash = "sha256-...";
})
```

## Migration playbook

### 1. Locate source files

```
harbor/src/harbor/agents/installed/<name>.py
llm-agents.nix/packages/<name>/{package.nix,hashes.json}
```

Read both before writing anything. You're not going to copy either file verbatim — you're going to lift 2-3 specific pieces from each (see "source mapping" above) and stitch them together.

### 2. Binary derivation (inline in `default.nix`)

Write the binary derivation as a `let` binding inside `default.nix`. Pick the builder shape (blob / npm / Rust) that matches upstream; use the `finalAttrs` form so `version` appears once, and inline the hash values. See the three templates in the llm-agents.nix section above — they are the target shape.

If the binary already exists as `pkgs.<name>` in nixpkgs, skip the custom derivation entirely and reference `pkgs.<name>` directly in the `symlinkJoin` paths.

### 3. `service.py`

Port harbor's CLI invocation. Strip everything else. Structure:

```python
"""<name> agent closure — Agentix ABI."""
from __future__ import annotations
import asyncio, os, shlex
import uvicorn
from fastapi import FastAPI, Request

app = FastAPI(title="<name>", version="0.1.0")

MANIFEST = {
    "name": "<name>",
    "version": "0.1.0",
    "kind": "agent",
    "description": "...",
    "endpoints": [{"method": "POST", "path": "/run", "description": "..."}],
}

@app.get("/")
async def manifest(): return MANIFEST

@app.post("/run")
async def run(req: Request):
    data = await req.json()
    instruction = data.get("instruction", "")
    workdir = data.get("workdir", "/testbed")
    timeout = float(data.get("timeout") or 600)

    env = {**os.environ}
    for k, v in (data.get("env") or {}).items():
        env[k] = v

    cmd_parts = [
        "<cli>",
        # port argv from harbor's run() method literally
        "--foo", "bar",
        "-p", shlex.quote(instruction),
    ]
    cmd = " ".join(cmd_parts)

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workdir,
        env=env,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"exit_code": -1, "stdout": "", "stderr": f"Timed out after {timeout}s", "patch": ""}

    # Capture everything as a git diff — works for any code-modifying agent.
    diff_cmd = f"cd {shlex.quote(workdir)} && git add -A && git diff --cached"
    diff_proc = await asyncio.create_subprocess_shell(
        diff_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    diff_out, _ = await diff_proc.communicate()

    return {
        "exit_code": proc.returncode or 0,
        "stdout": out_b.decode(errors="replace"),
        "stderr": err_b.decode(errors="replace"),
        "patch": diff_out.decode(errors="replace"),
    }

def main() -> None:
    uvicorn.run(app, uds=os.environ["AGENTIX_SOCKET"], log_level="warning")
```

Do not name this file `__main__.py` and do not create one. Use `service.py` with `def main()` and run it as `python3 <service.py>` from start.sh.

### 4. `start.sh`

Template with `@var@` placeholders substituted by Nix:

```sh
#!/bin/sh
set -e

# fixed env (ported from harbor's run() env dict)
export DISABLE_AUTOUPDATER=1
export IS_SANDBOX=1
export DISABLE_TELEMETRY=1

# agent binary is on PATH via the Agentix runtime fork (PATH=/mnt/<ns>/entry/bin:...)
# service.py binds AGENTIX_SOCKET; Nix substitutes the interpreter + service paths.
exec @python@/bin/python3 @service@
```

Keep start.sh short. If the agent needs pre-serving work (write a config file, copy skills dir, symlink caches), put it here above the `exec` — it's cheaper and clearer than doing it in Python before uvicorn starts.

### 5. `default.nix`

Composition, using `substitute` to fill `@python@` / `@service@`:

```nix
{ pkgs ? import <nixpkgs> {} }:
let
  binary = pkgs.stdenv.mkDerivation (finalAttrs: {
    pname = "<name>"; version = "X.Y.Z";
    src = pkgs.fetchurl { url = "..."; hash = "sha256-..."; };
    # ... installPhase, postFixup, etc.
  });
  python = pkgs.python312.withPackages (ps: [ ps.fastapi ps.uvicorn ]);
  service = ./service.py;
  start = pkgs.runCommand "<name>-start" { } ''
    mkdir -p $out/bin
    substitute ${./start.sh} $out/bin/start \
      --subst-var-by python ${python} \
      --subst-var-by service ${./service.py}
    chmod +x $out/bin/start
  '';
in
pkgs.symlinkJoin {
  name = "agentix-closure-<name>";
  paths = [ binary start ];
}
```

The derivation output has `bin/<cli>` (from `binary`) and `bin/start` (from `start`). `start` references `${python}/bin/python3` and the service.py file by absolute `/nix/store/...` paths that are content-addressed — they resolve inside the sandbox because the runtime's symlink forest at `/nix/store` exposes every closure's store entries.

### 6. `Dockerfile`

Copy `Agentix/tests/closure-docker/Dockerfile` into the closure dir as a starting point. **Context = the closure dir itself** (`<name>/`) — closures are self-contained, so Docker doesn't need to see sibling dirs or a repo-level flake.

If the closure needs a flake input (e.g. `numtide/llm-agents.nix` for the `claude` binary), put a local `flake.nix` + `flake.lock` *inside the closure dir* and build with `nix build .#<name>` inside the Dockerfile's builder stage. Don't rely on a shared repo-root flake.

Labels worth adding: `LABEL org.agentix.closure=1`, `LABEL org.agentix.closure.kind=agent` (or `dataset`), `LABEL org.agentix.closure.name=<name>`.

### 7. No registration step

There's no repo-level registry to update. Each closure's identity is its built Docker image ref (`agentix-hub/<name>:0.1.0`). Callers reference it by tag in `SandboxConfig(closures={...})`.

If a parent repo (Agents-Hub, Datasets) currently has a repo-root `flake.nix` listing closures, treat that as legacy scaffolding — prefer moving flake-using closures to their own local flakes over time, and drop the shared one.

### 8. Build and smoke-test

```bash
docker build -t agentix-hub/<name>:0.1.0 <name>/    # context = the closure dir
# in a tiny script (or the Python REPL):
import asyncio
from agentix import DockerDeployment, RuntimeClient, SandboxConfig
async def check():
    cfg = SandboxConfig(
        image="ubuntu:24.04",
        runtime="agentix/runtime:0.1.0",
        closures={"agent": "agentix-hub/<name>:0.1.0"},
    )
    async with DockerDeployment().session(cfg) as sb:
        async with RuntimeClient(sb.runtime_url) as c:
            print(await c.call("agent", "", method="GET"))   # manifest
            print(await c.call("agent", "run", {"instruction": "..."}))
asyncio.run(check())
```

Verify the manifest, exit code, stdout, patch. Then add an end-to-end test against a known task (e.g. a SWE-bench instance) before declaring done.

## Common pitfalls

- **`__main__.py`** — don't create one. Use `service.py` + `start.sh` `exec python3 service.py`. This is a durable preference across the Agentix ecosystem.
- **Hard-coded `/usr/bin/python3`** in start.sh — breaks hermeticity. Always reference `@python@/bin/python3` (substituted at build) so every path resolves inside `/nix/store`.
- **Agent binary not on PATH** — the Agentix runtime forks closures with `PATH=/mnt/<ns>/entry/bin:<scrubbed>`. Your derivation's `symlinkJoin` must produce `bin/<cli>`. `nix-build && ls result/bin/` to verify.
- **Trajectory overload** — resist porting harbor's ATIF JSON conversion. Return `{exit_code, stdout, stderr, patch}` and let callers opt in to richer formats via dedicated endpoints.
- **System deps at runtime** — don't add `apt-get install git` in the Dockerfile runtime stage. Put `pkgs.git` in the derivation (or better: use `--prefix PATH` via `wrapProgram`). The task image usually has `git` already.
- **Scrubbed env** — Agentix scrubs `LD_LIBRARY_PATH`, `PYTHONPATH`, `PYTHONHOME`, `NIX_*`, etc. from `/exec` subprocesses — and the closure fork inherits them from the runtime's own env. Don't rely on them; if you need them, set them yourself in start.sh or service.py before invoking the CLI.
- **Flake lives in the closure dir** — if the closure needs a flake input, put the `flake.nix` / `flake.lock` in that closure's own directory and build with `nix build .#<name>` inside the Dockerfile. Don't depend on a shared flake at the repo root — that couples closures that should be independent.
- **Version bumps** — llm-agents.nix uses `hashes.json` + `update.py` for upgrades. We inline everything in `package.nix`; bumping a version is a manual edit of the `version = ...` and matching hash lines. Accept the manual step; don't re-introduce the JSON sidecar.

## Datasets variation

For `Agentix-Datasets/<name>/`, the layout is the same but:

- `service.py` exposes `POST /setup` (normalize an instance record → `{instruction, workdir, instance_id}`) and `POST /verify` (apply patch, run tests, return `{pass, reason, details}`) instead of `/run`.
- There's rarely an external binary to vendor — most datasets only need Python + test tooling. `package.nix`/`hashes.json` are usually unnecessary; `default.nix` depends on `<nixpkgs>` directly.
- `start.sh` is often a one-liner: `exec @python@/bin/python3 @service@`.

See `Agentix-Datasets/swebench/` for a working reference.

## Worked example pointer

- Harbor source: `harbor/src/harbor/agents/installed/claude_code.py`
- llm-agents.nix source: `llm-agents.nix/packages/claude-code/{package.nix,hashes.json}`
- Agentix target: `Agentix-Agents-Hub/claude-code/`

When migrating a *new* agent, diff your work against claude-code's target — it's the canonical reference.
