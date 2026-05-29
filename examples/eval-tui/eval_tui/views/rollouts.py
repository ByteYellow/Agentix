"""Rollouts view — a live batch-rollout dashboard over `agentix.runner`.

Per-instance phase grid (pending -> setup -> agent -> scoring -> PASS/FAIL/skip/
error), a live summary bar, and an event log. Phase transitions are observed by
wrapping the dataset/agent adapters (see `.._adapters`), so `agentix.runner` is
unchanged. With no `RunSpec` the view shows an idle state (other tabs still work).
"""

from __future__ import annotations

import time

from agentix.runner import Rollout, run_rollouts
from rich.text import Text
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, RichLog, Static

from .._adapters import TracingAgent, TracingDataset, instance_id
from ..models import RunSpec

_PHASE = {
    "pending": ("· pending", "dim"),
    "setup": ("⟳ setup", "yellow"),
    "agent": ("⟳ agent", "cyan"),
    "score": ("⟳ scoring", "magenta"),
}


class RolloutsView(Vertical):
    """Live dashboard for a batch of rollouts."""

    def __init__(self, spec: RunSpec | None) -> None:
        super().__init__()
        self._spec = spec
        self._instances = list(spec.instances) if spec else []
        self._t0 = 0.0
        self._done = 0
        self._resolved = 0
        self._failed = 0
        self._running = 0

    def compose(self):
        yield Static(id="rollouts-summary")
        with Horizontal(id="rollouts-body"):
            yield DataTable(id="rollouts-table", zebra_stripes=True, cursor_type="row")
            yield RichLog(id="rollouts-log", markup=True, wrap=True)

    def on_mount(self) -> None:
        table = self.query_one("#rollouts-table", DataTable)
        table.add_column("Instance", key="iid", width=34)
        table.add_column("Status", key="status", width=16)
        table.add_column("Time", key="time", width=9)
        table.add_column("Result", key="result")

        if self._spec is None or not self._instances:
            self.query_one("#rollouts-summary", Static).update(
                Text("No run configured — launch with --demo N, or --dataset/--agent/--bundle.", style="dim")
            )
            self.query_one("#rollouts-log", RichLog).write("[dim]Idle — the Catalog tab works without a run.[/]")
            return

        for inst in self._instances:
            iid = instance_id(inst)
            table.add_row(iid, _phase("pending"), "", "", key=iid)
        self._t0 = time.monotonic()
        self._refresh_summary()
        self.run_worker(self._drive(), name="rollouts-drive", exclusive=True)

    async def _drive(self) -> None:
        assert self._spec is not None
        log = self.query_one("#rollouts-log", RichLog)
        log.write(f"[b]▶ starting[/] {len(self._instances)} rollouts · concurrency {self._spec.n_concurrent}")
        rollouts = await run_rollouts(
            dataset=TracingDataset(self._spec.dataset, self._on_phase),
            agent=TracingAgent(self._spec.agent, self._on_phase),
            provider=self._spec.provider,
            bundle=self._spec.bundle,
            model=self._spec.model,
            instances=self._instances,
            n_concurrent=self._spec.n_concurrent,
            on_result=self._on_result,
        )
        dt = time.monotonic() - self._t0
        log.write(f"[b green]■ done[/] — {self._resolved}/{len(rollouts)} resolved in {dt:.1f}s")

    def _on_phase(self, iid: str, phase: str) -> None:
        if phase == "setup":
            self._running += 1
        self._set_cell(iid, "status", _phase(phase))
        self._refresh_summary()

    def _on_result(self, rollout: Rollout) -> None:
        self._running = max(0, self._running - 1)
        self._done += 1
        if rollout.resolved:
            self._resolved += 1
            label, style, result = "✓ PASS", "bold green", "resolved"
        elif rollout.error:
            self._failed += 1
            label, style, result = "✗ error", "bold red", rollout.error[:48]
        elif rollout.skipped:
            self._failed += 1
            label, style, result = f"⊘ {rollout.skipped}", "yellow", rollout.skipped
        else:
            self._failed += 1
            label, style, result = "✗ FAIL", "red", "unresolved"
        self._set_cell(rollout.instance_id, "status", Text(label, style=style))
        self._set_cell(rollout.instance_id, "time", f"{rollout.duration_s:.1f}s")
        self._set_cell(rollout.instance_id, "result", result)
        self.query_one("#rollouts-log", RichLog).write(
            f"[{style}]{label}[/] {rollout.instance_id} · {rollout.duration_s:.1f}s"
        )
        self._refresh_summary()

    def _set_cell(self, iid: str, column: str, value: object) -> None:
        try:
            self.query_one("#rollouts-table", DataTable).update_cell(iid, column, value, update_width=False)
        except Exception:
            pass

    def _refresh_summary(self) -> None:
        total = len(self._instances)
        dt = max(1e-6, time.monotonic() - self._t0)
        rate = self._done / dt * 60
        text = Text.assemble(
            (_bar(self._done, total), "bold"),
            "   ",
            (f"{self._done}/{total} done", "bold"),
            "    ",
            ("✓ ", "dim"),
            (str(self._resolved), "bold green"),
            "    ",
            ("✗ ", "dim"),
            (str(self._failed), "bold red"),
            "    ",
            ("⟳ ", "dim"),
            (f"{self._running} running", "bold cyan"),
            "    ",
            (f"{rate:.1f}/min", "dim"),
        )
        self.query_one("#rollouts-summary", Static).update(text)


def _phase(phase: str) -> Text:
    label, style = _PHASE.get(phase, (phase, "white"))
    return Text(label, style=style)


def _bar(done: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "[" + "─" * width + "]"
    filled = round(width * done / total)
    return "[" + "█" * filled + "·" * (width - filled) + "]"
