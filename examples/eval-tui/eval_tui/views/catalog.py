"""Catalog view — the installed Agentix ecosystem at a glance.

Introspects the running environment with `importlib.metadata`: every installed
`agentix*` distribution, plus the `agentix.provider` (sandbox backends) and
`agentix.nix` (agents/datasets that ship a Nix closure) entry points. This is
pure introspection — no Docker, no runtime — so it always has something to show
and is fully testable headlessly.
"""

from __future__ import annotations

import importlib.metadata as md

from textual.containers import Vertical
from textual.widgets import DataTable, Static


class CatalogView(Vertical):
    """Installed Agentix distributions and entry points."""

    def compose(self):
        yield Static("Installed Agentix distributions & entry points", id="catalog-title")
        yield DataTable(id="catalog-table", zebra_stripes=True, cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#catalog-table", DataTable)
        table.add_column("Name", width=38)
        table.add_column("Kind", width=14)
        table.add_column("Version", width=12)
        table.add_column("Detail")
        rows = discover_catalog()
        for name, kind, version, detail in rows:
            table.add_row(name, kind, version, detail)
        title = self.query_one("#catalog-title", Static)
        title.update(f"Installed Agentix distributions & entry points  ([b]{len(rows)}[/])")


def discover_catalog() -> list[tuple[str, str, str, str]]:
    """Return (name, kind, version, detail) rows for the installed ecosystem."""
    rows: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()

    for dist in md.distributions():
        name = (dist.metadata["Name"] or "").strip()
        if name.startswith("agentix") and name not in seen:
            seen.add(name)
            summary = (dist.metadata.get("Summary") or "").strip()
            rows.append((name, "package", dist.version or "", summary))

    for kind, group in (("provider", "agentix.provider"), ("nix-closure", "agentix.nix")):
        try:
            entry_points = md.entry_points(group=group)
        except TypeError:  # pragma: no cover - very old importlib.metadata
            entry_points = md.entry_points().get(group, [])  # type: ignore[attr-defined]
        for ep in entry_points:
            rows.append((ep.name, kind, "", ep.value))

    rows.sort(key=lambda r: (r[1], r[0]))
    return rows
