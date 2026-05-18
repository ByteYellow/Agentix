# Roadmap

## v0.1.0 — RPC + bundle (current)

Two concepts, no more:

- **RPC.** `c.remote(fn, ...)` dispatches any importable Python module
  to a sandboxed worker subprocess. `unary`, server-`stream`, and
  `bidi` shapes are detected from the function signature; the wire
  flows over HTTP for unary and Socket.IO for the rest.
- **Bundle.** `agentix build [path]` packages one project root + its
  declared deps into a deploy-ready Docker image. Plugins arrive
  transitively via pip; the runtime auto-registers any importable
  module on first dispatch.

What's shipped:

- [x] Dispatcher + worker subprocess (`agentix.dispatch`,
      `agentix.runtime.server.worker`).
- [x] HTTP + Socket.IO transport (`agentix.runtime.shared.codec` /
      `events` / `rpc`).
- [x] Trace pub/sub (`agentix.trace`) — namespace impls `trace.emit(...)`,
      subscribers get one-shot fan-out.
- [x] `DockerDeployment` (lives in `agentix-deployment-docker`).
- [x] `RolloutPool` — warm sandbox pool for batched RL rollouts.
- [x] Single-spec `agentix build` — one project root, plugins via pip.
- [x] On-demand auto-register — user projects don't need entry points.

Sibling repos (each independently releasable):

- [`Agentix-Runtime-Basic`](https://github.com/Agentiix/Agentix-Runtime-Basic)
  — `bash` + `files` namespaces. On PyPI as `agentix-runtime-basic`.
- [`Agentix-Deployment-Docker`](https://github.com/Agentiix/Agentix-Deployment-Docker)
  — local Docker backend. On PyPI as `agentix-deployment-docker`.
- [`Agentix-Deployment-Daytona`](https://github.com/Agentiix/Agentix-Deployment-Daytona),
  [`Agentix-Deployment-E2B`](https://github.com/Agentiix/Agentix-Deployment-E2B)
  — stub backends; CLI surface in place, lifecycle wiring pending.
- [`abridge`](https://github.com/Agentiix/abridge) — host-side
  rollout-to-RL-buffer bridge.

## Unscheduled

Future directions, listed so the framework is built with them in mind.

- **LLM proxy** — transparent proxy that intercepts API calls from
  namespaces for token-level trajectory capture, cost tracking, replay.
  The proxy route (`/_llm/<provider>/<path>`) already exists; the
  upstream wiring + the trace correlation are TBD.
- **Checkpoint / partial rollout** — snapshot a sandbox (filesystem +
  loaded namespace state), fork to explore alternative continuations.
  Enables tree search / RL over execution traces.
- **K8s deployment backend** — parallel `Deployment` implementation
  using the same bundle-image contract; would ship as
  `agentix-deployment-k8s`.
