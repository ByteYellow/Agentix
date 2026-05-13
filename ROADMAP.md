# Roadmap

## v0.1.0 — Closure runtime (current)

Run any Nix closure inside a Docker sandbox as a typed Python module imported in-process by the runtime. Compose multiple closures, dispatch typed calls via `RuntimeClient.remote(fn, ...)`.

- [x] Closure ABI: `VOLUME /nix` + `/nix/store` + `/nix/entry/python/<package>` + `/nix/entry/manifest.json`
- [x] `DockerDeployment` — per-image named volume keyed by image digest, auto-populated by Docker; per-closure `-v /mnt/c<digest>:ro` + tmpfs `/nix`; sandbox entrypoint builds the `/nix/store` symlink forest and execs the runtime
- [x] Runtime server — built-in `exec / upload / download`, `/closures`, single typed-dispatch endpoint `POST /_remote`
- [x] Auto-load on startup: runtime scans `/mnt`, imports each closure's package, calls `<pkg>._register.register()` -> `Dispatcher`
- [x] Streaming returns via `AsyncIterator[T]` on stubs; wire is NDJSON on the same `/_remote` endpoint
- [x] Unit tests in CI

Higher-level concepts (agent adapter, dataset runner, benchmark orchestration) are **explicitly out of scope for v0.1.0** and will be revisited once the closure substrate is stable.

## Unscheduled

Future directions, listed so the closure layer is built with them in mind.

- **LLM proxy** — transparent proxy that intercepts API calls from closures for token-level trajectory capture, cost tracking, replay.
- **Checkpoint / partial rollout** — snapshot a sandbox (filesystem + loaded closure state), fork to explore alternative continuations; enables tree search / RL over execution traces.
- **K8s deployment backend** — parallel `Deployment` implementation using the same closure image contract.
