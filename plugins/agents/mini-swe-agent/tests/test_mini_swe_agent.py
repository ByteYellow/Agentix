from __future__ import annotations

import agentix.agents.mini_swe_agent as mini_swe
import pytest


class DummyEnvConfig:
    def __init__(self) -> None:
        self.cwd = ""


class DummyEnv:
    def __init__(self) -> None:
        self.config = DummyEnvConfig()


def test_run_success(tmp_path):
    class DummyAgent:
        def __init__(self) -> None:
            self.env = DummyEnv()

        def run(self, task: str):
            return {"exit_status": "submitted", "submission": "diff --git ..."}

    agent = DummyAgent()
    result = mini_swe.run(
        "fix bug",
        workdir=str(tmp_path),
        agent=agent,
    )
    assert result["exit_status"] == "submitted"
    assert result["submission"] == "diff --git ..."
    assert agent.env.config.cwd == str(tmp_path)


def test_run_exception_propagates(tmp_path):
    class BoomAgent:
        def __init__(self) -> None:
            self.env = DummyEnv()

        def run(self, task: str):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        mini_swe.run(
            "fix bug",
            workdir=str(tmp_path),
            agent=BoomAgent(),
        )
