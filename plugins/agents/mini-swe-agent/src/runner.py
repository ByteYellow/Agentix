from __future__ import annotations

from pathlib import Path
from typing import Any

from minisweagent import Agent


def run(
    task: str,
    *,
    workdir: str = "/testbed",
    agent: Agent,
) -> dict[str, Any]:
    """Run a pre-built mini-swe-agent instance in sandbox."""
    workdir_path = Path(workdir)
    workdir_path.mkdir(parents=True, exist_ok=True)

    env = getattr(agent, "env", None)
    env_config = getattr(env, "config", None)
    if env_config is not None and hasattr(env_config, "cwd"):
        env_config.cwd = str(workdir_path)

    return dict(agent.run(task))
