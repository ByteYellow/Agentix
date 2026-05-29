"""Headless pilot tests for the Agentix TUI (no Docker)."""

from __future__ import annotations

from eval_tui.app import AgentixTUI
from eval_tui.demo import DemoAgent, DemoDataset, DemoProvider
from eval_tui.models import RunSpec
from eval_tui.views.catalog import discover_catalog
from eval_tui.views.rollouts import RolloutsView
from textual.widgets import DataTable


def _demo_spec(n: int = 8) -> RunSpec:
    dataset = DemoDataset(n, seed=3, dur_scale=0.03)
    return RunSpec(
        dataset=dataset,
        agent=DemoAgent(),
        provider=DemoProvider(),
        bundle="demo",
        instances=dataset.instances(),
        n_concurrent=4,
    )


async def test_tui_runs_demo_and_lists_catalog() -> None:
    n = 8
    app = AgentixTUI(rollout_spec=_demo_spec(n))
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()

        view = app.query_one(RolloutsView)
        assert view._done == n
        assert view._resolved + view._failed == n

        catalog = app.query_one("#catalog-table", DataTable)
        assert catalog.row_count >= 1  # at least agentixx / agentix-runner are installed


async def test_tui_idle_without_spec_does_not_crash() -> None:
    app = AgentixTUI(rollout_spec=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one(RolloutsView)._done == 0
        assert app.query_one("#catalog-table", DataTable).row_count >= 1


async def test_rollouts_drilldown_shows_instance_detail() -> None:
    app = AgentixTUI(rollout_spec=_demo_spec(6))
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        view = app.query_one(RolloutsView)
        view.query_one("#rollouts-table", DataTable).move_cursor(row=0)
        await pilot.pause()

        assert "demo__task-000" in view._detail_text
        assert "verdict" in view._detail_text  # a finished instance renders its verdict


def test_discover_catalog_finds_agentix_distributions() -> None:
    rows = discover_catalog()
    names = {name for name, *_ in rows}
    assert any(n.startswith("agentix") for n in names)
