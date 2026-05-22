"""Minimal remote target for the `agentix build` end-to-end test.

A bundle of this project is the smallest thing that still exercises the
real pipeline: a uv venv with the framework + a plugin, the Nix
toolchain, and plugin/project system closures.
"""

from __future__ import annotations

import subprocess


def run(name: str = "world") -> dict[str, str]:
    """A trivial remote callable — `c.remote(run, name=...)`."""
    return {"greeting": f"hello, {name}"}


def ripgrep_version() -> str:
    """Return the bundled ripgrep version from the runtime PATH."""
    proc = subprocess.run(["rg", "--version"], check=True, capture_output=True, text=True)
    return proc.stdout.splitlines()[0]
