"""Agentix TUI — a modern Textual control room for Agentix.

A tabbed shell that surfaces each Agentix area as its own view. Today: live
**Rollouts** (over `agentix.runner`) and a **Catalog** of the installed
ecosystem; **Sandboxes**, **Build**, and **Observability** are signposted and
land in follow-up PRs. See `DESIGN.md` for the rubrics this iterates against.

Run a no-Docker demo with `agentix-eval-tui --demo 40`, point it at real
adapters like `agentix-run`, or launch it bare to browse the Catalog.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, TabbedContent, TabPane

from .models import RunSpec
from .views import CatalogView, PlaceholderView, RolloutsView


class AgentixTUI(App):
    """Tabbed control room for Agentix."""

    TITLE = "Agentix"
    SUB_TITLE = "agent ↔ environment control room"

    CSS = """
    TabbedContent { height: 1fr; }
    TabPane { padding: 0; }

    #rollouts-summary {
        height: 3;
        padding: 0 2;
        content-align: left middle;
        border: round $primary;
        background: $panel;
    }
    #rollouts-body { height: 1fr; }
    #rollouts-table { width: 3fr; height: 1fr; border: round $primary; }
    #rollouts-side { width: 2fr; height: 1fr; }
    #rollouts-detail { height: 2fr; border: round $primary; padding: 0 1; }
    #rollouts-log { height: 3fr; border: round $primary; padding: 0 1; }

    #catalog-title { height: 1; padding: 0 1; }
    #catalog-table { height: 1fr; border: round $primary; }

    #placeholder { text-align: center; width: auto; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
    ]

    def __init__(self, *, rollout_spec: RunSpec | None = None) -> None:
        super().__init__()
        self._spec = rollout_spec

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="rollouts"):
            with TabPane("Rollouts", id="rollouts"):
                yield RolloutsView(self._spec)
            with TabPane("Catalog", id="catalog"):
                yield CatalogView()
            with TabPane("Sandboxes", id="sandboxes"):
                yield PlaceholderView(
                    "Sandboxes",
                    "Open a live sandbox over a provider and call client.remote(...) interactively.",
                )
            with TabPane("Build", id="build"):
                yield PlaceholderView("Build", "Trigger and stream `agentix build` bundles.")
            with TabPane("Observability", id="observability"):
                yield PlaceholderView("Observability", "Live /trace spans and /log streams from running sandboxes.")
        yield Footer()
