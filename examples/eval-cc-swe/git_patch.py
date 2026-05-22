"""Sandbox-side generic workspace patch helpers."""

from __future__ import annotations

import asyncio

WORKDIR = "/testbed"


async def get_patch(workdir: str = WORKDIR) -> str:
    """Return all `workdir` changes, including new files, as a unified diff."""
    proc = await asyncio.create_subprocess_shell(
        (
            f"cd {workdir} && "
            "git -c core.fileMode=false add -A && "
            "git -c core.fileMode=false diff --cached --no-color --binary"
        ),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    return out.decode(errors="replace") if proc.returncode == 0 else ""


__all__ = ["get_patch"]
