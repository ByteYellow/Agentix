# eval-tui

A modern [Textual](https://textual.textualize.io/) **control room** for Agentix —
a tabbed TUI that surfaces each Agentix area in one place. See
[`DESIGN.md`](DESIGN.md) for the rubrics it's iterated against.

```text
┌─ Agentix · agent ↔ environment control room ───────────────────────────────┐
│  Rollouts │ Catalog │ Sandboxes │ Build │ Observability                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ [████████████············] 18/40 done    ✓ 11   ✗ 7   ⟳ 4 running   62.3/min │
│ Instance              Status      Time  Result │ ▶ starting 40 rollouts        │
│ demo__task-000        ✓ PASS      1.2s  resolved│ ✓ PASS demo__task-000 · 1.2s │
│ demo__task-001        ⟳ scoring   …          … │ …                            │
└─────────────────────────────────────────────────────────────────────────────┘
 q Quit
```

## Tabs

- **Rollouts** — live batch-rollout dashboard over
  [`agentix.runner`](../../plugins/runner): per-instance phase grid (`pending →
  setup → agent → scoring → PASS/FAIL/skip/error`), summary bar (progress /
  resolved / failed / running / throughput), and an event log. Phase
  transitions are observed by wrapping the dataset/agent adapters
  (`_adapters.py`), so `agentix.runner` is unchanged.
- **Catalog** — the installed Agentix ecosystem: every `agentix*` distribution
  plus `agentix.provider` (backends) and `agentix.nix` (agents/datasets shipping
  a Nix closure) entry points. Pure introspection — no Docker.
- **Sandboxes · Build · Observability** — signposted; landing in follow-up PRs.

## Run

```bash
cd examples/eval-tui
uv sync

# No-Docker synthetic demo:
uv run agentix-eval-tui --demo 40 --n-concurrent 6

# Real run — adapters resolved like `agentix-run`:
uv run agentix-eval-tui --dataset my_pkg:dataset --agent my_pkg:agent \
    --provider docker --bundle eval:0.1.0 --model claude-3-5-sonnet-latest

# Bare launch — just browse the Catalog (no run):
uv run agentix-eval-tui
```

## Test

```bash
uv sync --extra dev
uv run pytest        # headless Textual run_test pilots — no Docker
```
