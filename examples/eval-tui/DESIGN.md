# Agentix TUI — design & rubrics

A modern, reactive [Textual](https://textual.textualize.io/) control room for
Agentix. The goal is a single TUI that surfaces **every core Agentix surface** —
not just batch rollouts — built on the stable `client.remote` + `bundle` APIs
(plus `provider.session`) and degrading gracefully when no Docker/runtime is
present.

## Rubrics (v1 — scored 0–5, target ≥4, revisable)

| # | Dimension | "Advanced" looks like |
|---|-----------|------------------------|
| 1 | **Coverage** | Rollouts · plugin **Catalog** · **Sandboxes**/providers + remote-invoke · **Build**/bundle · **Observability** (traces + logs) |
| 2 | **Reactivity** | Fully async, live updates, bounded concurrency, never blocks the UI |
| 3 | **Navigation / IA** | Discoverable multi-area nav (tabs), command palette, help |
| 4 | **Visual design** | Cohesive theme, semantic color, responsive layout, dark/light |
| 5 | **Interaction** | Keybindings, mouse, search/filter, drill-down detail |
| 6 | **Robustness** | Graceful with no Docker (demo/empty states), error surfaces, cancellation |
| 7 | **Feedback** | Progress, throughput, status, notifications |
| 8 | **Code quality** | Typed, ruff-clean, modular, documented |
| 9 | **Verifiability** | Headless `run_test` pilots per screen; demo mode without infra |
| 10 | **Polish / UX** | Help screen, sensible defaults, onboarding |

## Architecture

```text
AgentixTUI(App)                      # shell: Header + TabbedContent + Footer, theme, palette
├── Rollouts   (views/rollouts.py)   # live batch-rollout dashboard over agentix.runner
├── Catalog    (views/catalog.py)    # installed agentix dists + entry points (no Docker)
├── Sandboxes  (views/…)             # providers + live sessions + remote-invoke   [planned]
├── Build      (views/…)             # trigger & stream `agentix build`            [planned]
└── Observability (views/…)          # live /trace spans + /log streams            [planned]
```

Each area is a self-contained view widget with its own demo/empty state, so the
app is useful (and testable headlessly) with no runtime attached.

## Rubric addendum (v2)

| # | Dimension | "Advanced" looks like |
|---|-----------|------------------------|
| 11 | **Aesthetics** | A landing dashboard that's genuinely beautiful — branded gradient banner, ecosystem stat cards, cohesive theme; a "sexy" first impression |

## Iteration log

- **PR-A** — app shell (TabbedContent nav) + **Catalog** view (real entry-point /
  distribution introspection) + this rubric doc + theming. Coverage 1→2, IA 1→4, Visual 3→4.
- **drill-down** — Rollouts instance detail pane (verdict/duration/score/error). Interaction 3→4.
- **Overview dashboard** — branded gradient banner + live ecosystem stat cards +
  environment readiness as the landing tab; branded Textual theme. Aesthetics →4, Polish →4.
- **next** — Sandboxes, Build, Observability views; command palette; search/filter.
