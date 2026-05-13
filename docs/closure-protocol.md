# Closure Protocol (v0.1.0)

A **closure** is a Docker image satisfying the Agentix closure convention. Inside a sandbox, the deployment mounts one closure per namespace at `/mnt/<ns>`; the runtime server forks each closure's entry point and reverse-proxies HTTP requests to it over a Unix socket.

## Image convention

A closure image MUST:

1. Declare `VOLUME /nix` (so Docker's volume-init-from-image rule populates a named volume on first attach).
2. Contain `/nix/store/<hash>-*/` — the content-addressed Nix dependencies (typically the full transitive closure of the derivation).
3. Contain `/nix/entry/bin/start` — an executable entry point.
4. Contain `/nix/entry/manifest.json` — a `ClosureManifest` JSON file with `abi == AGENTIX_CLOSURE_ABI`. **This is the marker that identifies the mount as a closure**; the runtime ignores any `/mnt/<ns>` whose manifest is missing, malformed, or carries an incompatible abi.

Beyond that, the image's base layer and other contents are irrelevant — the runtime only reads what's under `/nix`.

## `start` ABI

The runtime invokes `start` with **no CLI arguments**. Contract:

- Read `AGENTIX_SOCKET` from env — the absolute path where `start` must bind a Unix-socket HTTP server.
- Bind, listen, serve. On shutdown the loader sends `SIGTERM` first, then `SIGKILL` after a short grace period — a well-behaved closure exits on `SIGTERM` to avoid dropped in-flight requests.
- MAY expose `GET /` returning the same manifest JSON. Optional but recommended; the loader probes `GET /` only as a readiness signal (any non-5xx response counts).

Everything else — routes, request/response schemas, streaming semantics, error conventions — is the closure's choice. The runtime just proxies bytes.

## Manifest

`/nix/entry/manifest.json` is read by the runtime at mount-discovery time, **before** the closure is forked. Use `agentix.closure.write_manifest(...)` from your build script to emit it.

```json
{
  "abi": 1,
  "name": "my-closure",
  "version": "1.0.0",
  "kind": "tool",
  "description": "Short blurb",
  "endpoints": [
    {"method": "POST", "path": "/do",  "description": "Do the thing"}
  ]
}
```

| Field | Required | Purpose |
|---|---|---|
| `abi` | yes | Must equal `AGENTIX_CLOSURE_ABI` (currently `1`). Runtime skips mismatches with a warning. |
| `name` | yes | Human-readable name |
| `version` | yes | Semantic version |
| `description` | no | Short description |
| `kind` | no | Free-form tag for tooling; runtime ignores |
| `endpoints` | no | Declared surface — informational only; `[]` if omitted |

Extra fields are allowed and preserved.

## Sandbox-side placement

After the deployment puts each closure's Nix content into a per-image named volume and mounts each at `/mnt/<ns>:ro`, a sandbox sees:

```
/mnt/<ns>/
├── store/<hash>-*/         ← Nix deps (used by the symlink forest)
└── entry/
    ├── bin/start           ← the entry point
    └── manifest.json       ← ClosureManifest, marks this mount as a closure
```

and

```
/nix/
└── store/<hash>-*/         ← tmpfs, symlinked from /mnt/*/store/*
```

Every Nix binary's absolute `/nix/store/<hash>` reference resolves through the symlink forest.

## Runtime lifecycle

```
Sandbox boot
    │
    ├─ tmpfs /nix
    ├─ mkdir /nix/store
    ├─ ln -sfn /mnt/*/store/*  /nix/store/
    └─ exec /mnt/runtime/entry/bin/start
           │
           └─ lifespan: scan /mnt/* (skip `runtime`)
                for each /mnt/<ns>/entry/manifest.json (valid + matching abi):
                    fork: exec `start` with
                          AGENTIX_SOCKET=/tmp/agentix/<ns>.sock
                          PATH=/mnt/<ns>/entry/bin:<scrubbed>
                wait for socket, GET / as readiness probe
```

Closures are **fixed at sandbox create time**; change the set by recreating the sandbox.

## Reverse proxy

`ANY /{namespace}/{path*}` on the runtime forwards to the closure at `/tmp/agentix/<namespace>.sock`:

- Status code, body, and non-hop-by-hop headers forwarded verbatim.
- Response streamed (`httpx.stream` → `StreamingResponse`) — SSE and chunked responses pass through.
- Hop-by-hop headers (`Host`, `Transfer-Encoding`, `Content-Length`, `Content-Encoding`) stripped on both sides.
- `502` only when the closure process is missing / dead / unreachable.

W3C `traceparent` / `tracestate` headers pass through untouched, so an OpenTelemetry-instrumented closure sees the caller's trace context automatically.

## Runtime built-ins

Independent of any closure, the runtime exposes:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness |
| `POST /exec` | Run a shell command in the sandbox. Body `{command, cwd?, env?, timeout?, paths_from?}`. SSE when `Accept: text/event-stream`; else JSON `{exit_code, stdout, stderr}`. |
| `POST /upload` | Multipart upload into `AGENTIX_UPLOAD_ROOT` (default `/workspace`). |
| `GET /download?path=…` | Stream a file back. |
| `GET /closures` | List loaded closures and their manifests. |
| `GET /closures/{ns}/logs` | Ring-buffered stdout/stderr of that closure's process. |

`RuntimeClient.run / upload / download / closures / logs` are typed Python helpers. Directory listing and other file inspection go through `/exec` (`ls -la`, `find`, `stat`).

### `/exec` env and PATH

Subprocesses run with a scrubbed env:

- Stripped: `LD_LIBRARY_PATH`, `LD_PRELOAD`, `PYTHONPATH`, `PYTHONHOME`, `LOCALE_ARCHIVE`, `FONTCONFIG_*`, `SSL_CERT_FILE`, anything prefixed `NIX_`.
- Default PATH: the task image's (`/usr/local/bin:/usr/bin:/bin`). Task-image tools take precedence over closure-bundled tools of the same name.
- Opt-in to a closure's bins with `paths_from=["<ns>"]` — prepends `/mnt/<ns>/entry/bin`.

## Writing a closure

Minimal Python-closure example: a directory with

- `pyproject.toml` declaring `[project.scripts] start = "<pkg>.__main__:main"` and `fastapi` + `uvicorn` in `dependencies`
- a package with `__main__.py` that binds uvicorn on `AGENTIX_SOCKET`
- a `default.nix` that uses `buildPythonApplication` (or equivalent) to emit `bin/start` and writes `manifest.json` into `$out` (e.g. via a `postInstall` hook, or `agentix.closure.write_manifest` from a Python build step)

Build the image with a Dockerfile of your own that runs `nix-build` in a builder stage, copies the closure of `/nix/store` deps plus a `/nix/entry` symlink into the final layer, and declares `VOLUME /nix`. `tests/closure-docker/Dockerfile` in this repo is a working reference.

Use it:

```python
SandboxConfig(
    image="ubuntu:24.04",
    runtime="agentix/runtime:0.1.0",
    closures={"mine": "my-closure:1.0"},
)
```

See `tests/closures/mock-agent/` and `tests/closures/mock-dataset/` for working references.
