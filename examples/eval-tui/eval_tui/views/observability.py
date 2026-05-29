"""Observability — live `/trace` spans + `/log` records.

Agentix ships two side channels alongside `/rpc`: `/trace` (OTel-style spans)
and `/log` (stdlib logging bridged sandbox→host). This view streams both into a
split live feed. With no run attached it plays a short synthetic demo so the
shape is visible; real streams arrive from running sandboxes.
"""

from __future__ import annotations

import asyncio

from textual.containers import Horizontal, Vertical
from textual.widgets import RichLog, Static

_DEMO_SPANS = [
    ("rollout.setup", "3ms", "green"),
    ("agent.solve", "—", "cyan"),
    ("llm.call #1", "412ms", "magenta"),
    ("llm.call #2", "388ms", "magenta"),
    ("bash.run git-diff", "21ms", "yellow"),
    ("agent.solve", "1.4s", "cyan"),
    ("dataset.score", "1.1s", "green"),
]
_DEMO_LOGS = [
    ("INFO", "prepare_env: reset /testbed to base commit"),
    ("INFO", "bridge: anthropic service on 127.0.0.1:38211"),
    ("INFO", "claude: editing src/… (2 files)"),
    ("DEBUG", "llm.call tokens_in=2310 tokens_out=181"),
    ("INFO", "extracted patch (1.8 KB)"),
    ("INFO", "score: 1 fail_to_pass resolved"),
    ("INFO", "rollout resolved=true"),
]


class ObservabilityView(Vertical):
    """Split live feed of `/trace` spans and `/log` records."""

    def __init__(self, *, demo: bool = True, delay: float = 0.25) -> None:
        super().__init__()
        self._demo = demo
        self._delay = delay
        self._emitted = 0

    def compose(self):
        yield Static("Live observability — /trace spans · /log records", id="obs-title")
        with Horizontal(id="obs-body"):
            yield RichLog(id="obs-trace", markup=True, wrap=True)
            yield RichLog(id="obs-log", markup=True, wrap=True)

    def on_mount(self) -> None:
        self.query_one("#obs-trace", RichLog).write("[b]/trace[/]  OTel-style spans")
        self.query_one("#obs-log", RichLog).write("[b]/log[/]  bridged stdlib logging")
        if self._demo:
            self.run_worker(self._stream(), name="obs-demo", exclusive=True)

    async def _stream(self) -> None:
        trace = self.query_one("#obs-trace", RichLog)
        log = self.query_one("#obs-log", RichLog)
        for i in range(max(len(_DEMO_SPANS), len(_DEMO_LOGS))):
            if i < len(_DEMO_SPANS):
                name, dur, color = _DEMO_SPANS[i]
                trace.write(f"[{color}]◷[/] {name}  [dim]{dur}[/]")
                self._emitted += 1
            if i < len(_DEMO_LOGS):
                level, msg = _DEMO_LOGS[i]
                level_style = {"INFO": "green", "DEBUG": "dim", "WARNING": "yellow", "ERROR": "red"}.get(level, "white")
                log.write(f"[{level_style}]{level:<5}[/] {msg}")
                self._emitted += 1
            if self._delay:
                await asyncio.sleep(self._delay)
