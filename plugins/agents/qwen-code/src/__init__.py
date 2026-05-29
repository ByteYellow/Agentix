"""Run the qwen-code agent (Qwen3-Coder CLI) inside an Agentix sandbox.

qwen-code is a Node CLI shipped by this plugin's ``default.nix`` — the ``qwen``
binary lands on ``/nix/runtime/bin`` during ``agentix build`` (mirrors
``agentix.agents.claude_code`` / ``agentix.agents.opencode``). It speaks the
OpenAI-compatible API, so point it at the in-sandbox bridge through ``env``
(``OPENAI_BASE_URL`` / ``OPENAI_API_KEY``) and run it non-interactively.

Invoke it from the host::

    from agentix.agents.qwen_code import run

    result = await client.remote(
        run,
        instruction="fix the failing test",
        workdir="/testbed",
        model="qwen3-coder-plus",
        env={"OPENAI_BASE_URL": bridge_url, "OPENAI_API_KEY": "sk-..."},
    )
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass


@dataclass
class Result:
    exit_code: int
    stdout: str
    stderr: str


async def run(
    instruction: str,
    *,
    workdir: str = "/testbed",
    timeout: float = 1800,
    model: str | None = None,
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> Result:
    """Run ``qwen`` once over ``workdir`` with ``instruction``.

    Runs non-interactively (``--prompt``) and auto-approves tool actions
    (``--yolo``) — appropriate inside a sandbox. ``model`` is forwarded as
    ``--model``; ``env`` is layered over the process environment (pass the LLM
    endpoint here); ``extra_args`` are appended verbatim.
    """
    qwen_bin = shutil.which("qwen") or "qwen"
    cmd: list[str] = [qwen_bin, "--yolo", "--prompt", instruction]
    if model:
        cmd += ["--model", model]
    if extra_args:
        cmd += extra_args

    full_env = {**os.environ, **(env or {})}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=workdir,
        env=full_env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return Result(exit_code=-1, stdout="", stderr=f"qwen timed out after {timeout}s")

    return Result(
        exit_code=proc.returncode or 0,
        stdout=out.decode(errors="replace"),
        stderr=err.decode(errors="replace"),
    )


__all__ = ["Result", "run"]
