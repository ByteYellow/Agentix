"""Help overlay — a modal cheatsheet of the app's key bindings.

Pressing `?` pushes this screen; `?` / `escape` / `q` dismiss it. The rows are
rendered from the running app's `BINDINGS` at display time, so the overlay
cannot advertise a key the app doesn't actually bind (and can't drift as
bindings change).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

# Display labels for binding names that differ from what a user would type.
_KEY_LABELS = {"question_mark": "?"}


def _binding_rows(bindings: object) -> list[tuple[str, str]]:
    """`(key, description)` for each described binding, read from a Textual
    `BINDINGS` list (tuples or `Binding` objects). Bindings without a
    description are omitted — they aren't user-facing."""
    rows: list[tuple[str, str]] = []
    for b in bindings or ():  # type: ignore[union-attr]
        if isinstance(b, tuple):
            key = b[0]
            description = b[2] if len(b) > 2 else ""
        else:
            key = getattr(b, "key", "")
            description = getattr(b, "description", "")
        if key and description:
            rows.append((_KEY_LABELS.get(key, key), description))
    return rows


def _render(rows: list[tuple[str, str]]) -> str:
    width = max((len(key) for key, _ in rows), default=1)
    return "\n".join(f"[b]{key.ljust(width)}[/]   {desc}" for key, desc in rows)


class HelpScreen(ModalScreen[None]):
    """Centered modal listing the app's key bindings."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: $background 60%;
    }
    #help-card {
        width: auto;
        height: auto;
        max-width: 80%;
        padding: 1 3;
        border: round $primary;
        background: $panel;
    }
    #help-title { padding-bottom: 1; text-style: bold; color: $accent; }
    #help-foot { padding-top: 1; color: $text-muted; }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("question_mark", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        rows = _binding_rows(getattr(self.app, "BINDINGS", ()))
        with Vertical(id="help-card"):
            yield Static("Agentix TUI — keys", id="help-title")
            yield Static(_render(rows), id="help-body")
            yield Static("press ? or esc to close", id="help-foot")
