"""Overview — the landing dashboard.

An at-a-glance home screen: a branded gradient banner, ecosystem stat cards
(from the same introspection the Catalog uses), environment readiness, and
quick hints. Pure introspection — renders with or without Docker.
"""

from __future__ import annotations

import shutil

from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from .catalog import discover_catalog

# Brand gradient (Agentix docs palette), warm copper.
_GRADIENT = ["#f2ac90", "#e8957a", "#e0856b", "#d4775c", "#c46a50", "#b25f47", "#a45a45"]


class _Card(Static):
    """A single ecosystem stat card."""

    def __init__(self, icon: str, value: str, label: str, color: str) -> None:
        content = Text.assemble(
            (f"{icon}\n", color),
            (f"{value}\n", f"bold {color}"),
            (label, "dim"),
        )
        super().__init__(content, classes="ov-card")


class OverviewView(Vertical):
    """The landing dashboard for the Agentix TUI."""

    def __init__(self) -> None:
        super().__init__()
        rows = discover_catalog()
        self._counts = {
            "packages": sum(1 for row in rows if row[1] == "package"),
            "providers": sum(1 for row in rows if row[1] == "provider"),
            "closures": sum(1 for row in rows if row[1] == "nix-closure"),
        }
        self._docker = shutil.which("docker") is not None

    def compose(self):
        yield Static(_banner(), id="ov-banner")
        with Horizontal(id="ov-cards"):
            yield _Card("⬢", str(self._counts["packages"]), "packages", "#e0856b")
            yield _Card("◆", str(self._counts["providers"]), "providers", "cyan")
            yield _Card("✦", str(self._counts["closures"]), "nix closures", "magenta")
            yield _Card(
                "◉" if self._docker else "○",
                "ready" if self._docker else "—",
                "docker",
                "green" if self._docker else "red",
            )
        yield Static(_hints(), id="ov-hints")


def _banner() -> Text:
    title = "A G E N T I X"
    text = Text()
    index = 0
    for char in title:
        if char == " ":
            text.append(" ")
        else:
            text.append(char, style=f"bold {_GRADIENT[index % len(_GRADIENT)]}")
            index += 1
    text.append("\n")
    text.append("the universal bridge between agents and environments", style="dim italic")
    return text


def _hints() -> Text:
    return Text.assemble(
        ("tabs   ", "dim"),
        ("Overview · Rollouts · Catalog · Sandboxes · Build · Observability\n", ""),
        ("try    ", "dim"),
        ("agentix-eval-tui --demo 40", "bold"),
        ("    ", ""),
        ("q", "bold"),
        (" quit   ", "dim"),
        ("←/→", "bold"),
        (" switch tabs", "dim"),
    )
