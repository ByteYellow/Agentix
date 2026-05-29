"""Placeholder view for surfaces that are planned but not yet built.

Honest signposting (not fake functionality): it states what the screen will do,
so the navigation/IA reads as complete while the implementation lands PR by PR.
"""

from __future__ import annotations

from rich.text import Text
from textual.containers import Center, Middle
from textual.widgets import Static


class PlaceholderView(Center):
    def __init__(self, title: str, blurb: str) -> None:
        super().__init__()
        self._title = title
        self._blurb = blurb

    def compose(self):
        with Middle():
            yield Static(
                Text.assemble(
                    (f"{self._title}\n\n", "bold"),
                    (self._blurb, "dim"),
                    ("\n\nComing soon — landing in a follow-up PR.", "dim italic"),
                ),
                id="placeholder",
            )
