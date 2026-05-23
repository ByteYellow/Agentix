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
from agentix.utils.log import configure_logging as configure_agentix_logging

logger = logging.getLogger(__name__)


def configure_example_logging() -> None:
    configure_agentix_logging(default_context="host")


def hello() -> str:
    """Return the bundled ripgrep version from the runtime PATH."""
    proc = subprocess.run(["rg", "--version"], check=True, capture_output=True, text=True)
    logger.info("proc.stderr: %s", proc.stderr)
    logger.info("proc.returncode: %s", proc.returncode)
    return proc.stdout.splitlines()[0]


def run() -> str:
    return "hello, world"


def ripgrep_version() -> str:
    return hello()


async def main():
    deployment = DockerDeployment()
    config = SandboxConfig(
        image="python:3.13-slim",
        bundle="hello-world",
    )
    logger.info("config: %s", config)
    async with session(deployment, config) as sandbox:
        async with RuntimeClient(sandbox.runtime_url) as client:
            # Run function in host
            result = hello()
            print(f'Host result: {result}')
            # Run same function in sandbox
            result = await client.remote(hello)
            print(f'Sandbox result: {result}')


if __name__ == "__main__":
    import asyncio

    configure_example_logging()
    asyncio.run(main())
