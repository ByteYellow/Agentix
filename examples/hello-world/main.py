"""Minimal remote target for the `agentix build` end-to-end test.

A bundle of this project is the smallest thing that still exercises the
real pipeline: a uv venv with the framework + a plugin, the Nix
toolchain, and plugin/project system closures.
"""

from __future__ import annotations

import logging
import subprocess

from agentix.deployment.docker import DockerDeployment

from agentix import RuntimeClient
from agentix.deployment.base import SandboxConfig, session

logger = logging.getLogger(__name__)


def run(name: str = "world") -> dict[str, str]:
    """A trivial remote callable — `c.remote(run, name=...)`."""
    return {"greeting": f"hello, {name}"}


def ripgrep_version() -> str:
    """Return the bundled ripgrep version from the runtime PATH."""
    proc = subprocess.run(["rg", "--version"], check=True, capture_output=True, text=True)
    logger.info("proc.stderr: %s", proc.stderr)
    logger.info("proc.returncode: %s", proc.returncode)
    return proc.stdout.splitlines()[0]


async def main():
    deployment = DockerDeployment()
    config = SandboxConfig(
        image="python:3.13-slim",
        bundle="hello-world",
    )
    logger.info("config: %s", config)
    async with session(deployment, config) as sandbox:
        async with RuntimeClient(sandbox.runtime_url) as client:
            result = await client.remote(ripgrep_version)
            print(result)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
