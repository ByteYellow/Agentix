# Agentix Architecture (v0.1.0)

## Scope

v0.1.0 ships exactly three concerns:

1. A **closure convention** — what a Docker image must contain to be consumable by Agentix.
2. A **runtime server** — one process per sandbox that provides sandbox I/O and reverse-proxies to each closure.
3. A **Docker deployment** — packages closures into named volumes, assembles sandboxes, starts the runtime.

See [`ROADMAP.md`](../ROADMAP.md) for what comes later.

## Components

```
┌─ Host (orchestrator) ─────────────────────────────────────────┐
│  RuntimeClient                                                 │
│    • run / upload / download           (runtime built-ins)     │
│    • closures / logs                   (introspection)         │
│    • call(namespace, endpoint, data)   (any mounted closure)   │
└──────────────────────────────┬─────────────────────────────────┘
                               │ HTTP
┌─ Sandbox ──────────────────────▼───────────────────────────────┐
│                                                                 │
│  agentix-server                                                 │
│    built-in I/O:                                                │
│      GET  /health                                               │
│      POST /exec     (SSE or JSON)                               │
│      POST /upload                                               │
│      GET  /download                                             │
│    closure introspection:                                       │
│      GET  /closures, /closures/{ns}/logs                        │
│    streaming reverse proxy:                                     │
│      ANY  /{namespace}/{path*}                                  │
│                                                                 │
│  Closures (Unix sockets at /tmp/agentix/{ns}.sock):             │
│    forked by the runtime at startup from each                   │
│    /mnt/<ns>/entry/bin/start                                    │
│                                                                 │
│  /nix/store — tmpfs with a symlink forest merged from every     │
│  /mnt/<ns>/store content-addressed directory                    │
└─────────────────────────────────────────────────────────────────┘
```

The runtime's lifespan scans `/mnt` at startup and forks each closure it finds. Closures are fixed for the sandbox's lifetime; change the set by recreating the sandbox.

## Closure convention

A closure is a Docker image that declares `VOLUME /nix` and carries:

- `/nix/store/<hash>-*/` — content-addressed Nix dependencies (the transitive closure)
- `/nix/entry/bin/start` — executable entry point (no CLI args)
- `/nix/entry/manifest.json` — `ClosureManifest` with `abi == AGENTIX_CLOSURE_ABI`; the marker that identifies the mount as a closure

The `start` binary reads `AGENTIX_SOCKET` from env and binds a local HTTP server on that Unix socket. It SHOULD expose `GET /` returning the same manifest JSON — the runtime probes it only as a readiness signal. Everything else — routes, request schemas, streaming semantics — is the closure's choice; the runtime just proxies bytes.

See [`closure-protocol.md`](closure-protocol.md) for the full ABI.

## Sandbox layout

```
/
├── mnt/
│   ├── runtime/       ← -v agentix-closure-<digest>:/mnt/runtime:ro
│   │   ├── store/<hash>-*/
│   │   └── entry/
│   │       └── bin/start   ← the agentix-server binary
│   └── <ns>/          ← one mount per closure, ro
│       ├── store/<hash>-*/
│       └── entry/
│           └── bin/start
│
├── nix/
│   └── store/         ← --tmpfs /nix (writable),
│                        populated at entrypoint-time with
│                        `ln -sfn /mnt/*/store/* /nix/store/`
│
└── (task image rootfs — /usr, /bin, /etc, /testbed, ...)
```

Sandbox entrypoint (inlined into `docker run`):

```sh
set -e
mkdir -p /nix/store
for d in /mnt/*/store; do ln -sfn "$d"/* /nix/store/; done
exec /mnt/runtime/entry/bin/start
```

Why the symlink forest: Nix binaries have `/nix/store/<hash>` hard-coded in shebangs and RPATH. They only work if `/nix/store/<hash>` resolves. Symlinking each closure's `store/<hash>` into a shared `/nix/store` merges them cheaply — content-addressed paths can't collide, and the task image sees one unified `/nix/store`.

## Environment & PATH policy

The runtime is a Nix-built binary, so `os.environ` is loaded with Nix-runtime paths (`LD_LIBRARY_PATH`, `FONTCONFIG_FILE`, `NIX_*`, etc.). Leaking those into subprocesses causes glibc/ABI mismatches with task-image binaries.

Rules at every `/exec` and closure fork:

1. **Strip Nix-host-only env vars** — `LD_LIBRARY_PATH`, `LD_PRELOAD`, `PYTHONPATH`, `PYTHONHOME`, `LOCALE_ARCHIVE`, `FONTCONFIG_*`, `SSL_CERT_FILE`, anything prefixed `NIX_`.
2. **PATH defaults to the task image's default** (`/usr/local/bin:/usr/bin:/bin`). Task-image tools take precedence over closure-bundled tools of the same name.
3. **Closures invoke their own tools by absolute `/nix/store` path** — what well-formed Nix builds already produce via shebangs and wrappers.

When a closure is forked, PATH is prepended with `/mnt/<ns>/entry/bin` so the closure's own shell-outs resolve to its bundled tools first.

## Deployment (Docker)

Per unique closure image (cached in process):

```
docker run --rm -v agentix-closure-<digest>:/nix <image> true
```

Docker's volume-init-from-image rule auto-populates the named volume from the image's `/nix` layer on first attach; skips if already populated. The volume key is the image's SHA256 digest, so rebuilds produce a fresh volume automatically.

Sandbox create:

```
docker run -d \
  --name <sandbox-id> \
  --network host \
  -v agentix-closure-<runtime-digest>:/mnt/runtime:ro \
  -v agentix-closure-<ns-digest>:/mnt/<ns>:ro   (per closure) \
  --tmpfs /nix:exec,mode=755 \
  -e AGENTIX_BIND_PORT=<port> \
  <task-image> sh -c '<entrypoint>'
```

## Design decisions

- **Unix sockets over HTTP** — every HTTP stack works out of the box; curl-debuggable; logs stay clean.
- **Process per closure** — isolation, independent crashes, independent deps.
- **Runtime forwards bytes verbatim** — closures own their wire schemas; streaming (SSE, chunked) works end-to-end.
- **Static closure set per sandbox** — change the set by recreating the sandbox.
- **Built-in sandbox I/O on the runtime** — run / upload / download always available.

## Out of scope (v0.1.0)

- Bearer-token auth on the runtime (sandbox-level trust assumed).
- Higher-level interfaces for agents / datasets / benchmarks — see [`ROADMAP.md`](../ROADMAP.md).
