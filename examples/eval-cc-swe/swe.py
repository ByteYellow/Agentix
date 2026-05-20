"""Sandbox-side: SWE-bench Verified primitives.

Three remote-call entry points, mirroring the flow in
`swebench.harness.run_evaluation.run_instance` (L151+):

    1. `swe.clean(workdir, base_commit)`
       Reset `/testbed` to `base_commit`, drop any extra commits, wipe
       the working tree. Run before `cc.run` so the model starts from a
       known state regardless of what the prebuilt image happened to
       ship at HEAD.

    2. `swe.get_patch(workdir)`
       Capture the model's diff against `base_commit` — staged adds +
       working-tree edits — as a single unified diff string.

    3. `swe.eval(instance, patch)`
       Reproduce SWE-bench's evaluation:
         (a) write `patch` to `/tmp/patch.diff`, try the GIT_APPLY_CMDS
             fallback chain; emit APPLY_PATCH_PASS / APPLY_PATCH_FAIL.
         (b) write `test_spec.eval_script` to `/eval.sh` and run it.
         (c) grade the log via `get_eval_report`.
       Returns `{resolved, patch_applied, tests_status}`.

The intended host flow is two sandboxes per instance: one for the cc
agent (clean → cc.run → get_patch), tear down, then a fresh sandbox
for swe.eval. Both sandboxes use the per-instance SWE-bench eval
image (`swebench/sweb.eval.x86_64.<id>:latest`) as the base.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WORKROOT = Path(os.environ.get("AGENTIX_UPLOAD_ROOT", "/tmp")) / ".cache" / "swebench-eval"
TESTBED = "/testbed"
PATCH_DOCKER_PATH = "/tmp/patch.diff"

# Same fallback chain as swebench.harness.run_evaluation.GIT_APPLY_CMDS.
GIT_APPLY_CMDS = [
    "git apply --verbose",
    "git apply --verbose --reject",
    "patch --batch --fuzz=5 -p1 -i",
]


@dataclass
class CleanResult:
    ok: bool
    head: str
    log: str


@dataclass
class EvalResult:
    resolved: bool
    patch_applied: bool
    apply_cmd: str | None
    fail_to_pass: dict[str, list[str]] = field(default_factory=dict)
    pass_to_pass: dict[str, list[str]] = field(default_factory=dict)
    git_diff_before: str = ""
    git_diff_after: str = ""
    apply_log: str = ""
    test_log: str = ""


async def clean(workdir: str = TESTBED, base_commit: str | None = None) -> CleanResult:
    """Reset `workdir` to `base_commit` and drop everything else.

    Mirrors SWE-bench's expectation that /testbed enters the eval at
    exactly base_commit with a clean working tree.
    """
    parts = [
        f"cd {workdir}",
        "git -c core.fileMode=false update-index --refresh >/dev/null 2>&1 || true",
    ]
    if base_commit:
        parts.append(f"git reset --hard {base_commit}")
    else:
        parts.append("git reset --hard HEAD")
    parts.append("git clean -fdx")
    parts.append("git rev-parse HEAD")

    proc = await asyncio.create_subprocess_shell(
        " && ".join(parts),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    text = out.decode(errors="replace")
    head = text.strip().splitlines()[-1] if proc.returncode == 0 else ""
    return CleanResult(ok=proc.returncode == 0, head=head, log=text)


async def get_patch(workdir: str = TESTBED) -> str:
    """Return all `workdir` changes (including new files) as a unified diff.

    `git add -A` first so untracked files appear in `--cached`; this
    keeps parity with SWE-bench's expected prediction format.
    """
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


async def eval(
    *,
    instance: dict[str, Any],
    patch: str,
    workdir: str = TESTBED,
    apply_timeout: float = 120,
    eval_timeout: float = 1800,
) -> EvalResult:
    """Apply `patch` in `workdir`, run the instance's eval_script, grade."""
    from swebench.harness.constants import (
        APPLY_PATCH_FAIL,
        APPLY_PATCH_PASS,
        KEY_INSTANCE_ID,
        KEY_MODEL,
        KEY_PREDICTION,
    )
    from swebench.harness.grading import get_eval_report
    from swebench.harness.test_spec.test_spec import make_test_spec

    spec = make_test_spec(instance)
    workroot = WORKROOT / spec.instance_id
    if workroot.exists():
        shutil.rmtree(workroot)
    workroot.mkdir(parents=True)

    # (a) Stage the patch and try GIT_APPLY_CMDS in order — same chain
    # as swebench/harness/run_evaluation.py.
    Path(PATCH_DOCKER_PATH).write_text(patch or "")
    apply_log_parts: list[str] = []
    applied_with: str | None = None
    for cmd in GIT_APPLY_CMDS:
        proc = await asyncio.create_subprocess_shell(
            f"cd {workdir} && {cmd} {PATCH_DOCKER_PATH}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(
                proc.communicate(), timeout=apply_timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            apply_log_parts.append(f"[{cmd}] timed out\n")
            continue
        apply_log_parts.append(f"[{cmd}] exit={proc.returncode}\n{out.decode(errors='replace')}\n")
        if proc.returncode == 0:
            applied_with = cmd
            break

    if applied_with:
        apply_log_parts.append(f"{APPLY_PATCH_PASS}\n")
    else:
        apply_log_parts.append(f"{APPLY_PATCH_FAIL}\n")

    apply_log = "".join(apply_log_parts)
    (workroot / "apply.log").write_text(apply_log)

    git_diff_before = await _capture_diff(workdir)

    # (b) Run the eval script. test_spec.eval_script handles applying
    # test_patch and invoking the test command with START/END markers.
    eval_script = workroot / "eval.sh"
    eval_script.write_text(spec.eval_script)
    eval_script.chmod(0o755)

    test_log_path = workroot / "test_output.log"
    test_log = await _run_script(eval_script, test_log_path, timeout=eval_timeout)

    # The grading function expects APPLY_PATCH_PASS / APPLY_PATCH_FAIL
    # in the same log file it parses for test results.
    combined_log = apply_log + test_log
    test_log_path.write_text(combined_log)

    git_diff_after = await _capture_diff(workdir)

    # (c) Grade with the official report function.
    pred = {
        KEY_INSTANCE_ID: spec.instance_id,
        KEY_MODEL: "eval-cc-swe",
        KEY_PREDICTION: patch,
    }
    report = get_eval_report(
        test_spec=spec,
        prediction=pred,
        test_log_path=str(test_log_path),
        include_tests_status=True,
    )
    entry = report.get(spec.instance_id, {})
    tests = entry.get("tests_status", {}) or {}
    ftp = tests.get("FAIL_TO_PASS", {"success": [], "failure": []})
    ptp = tests.get("PASS_TO_PASS", {"success": [], "failure": []})

    return EvalResult(
        resolved=bool(entry.get("resolved", False)),
        patch_applied=bool(entry.get("patch_successfully_applied", False)),
        apply_cmd=applied_with,
        fail_to_pass={
            "success": list(ftp.get("success", [])),
            "failure": list(ftp.get("failure", [])),
        },
        pass_to_pass={
            "success": list(ptp.get("success", [])),
            "failure": list(ptp.get("failure", [])),
        },
        git_diff_before=git_diff_before,
        git_diff_after=git_diff_after,
        apply_log=apply_log,
        test_log=test_log,
    )


async def _capture_diff(workdir: str) -> str:
    proc = await asyncio.create_subprocess_shell(
        f"cd {workdir} && git -c core.fileMode=false diff",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    return out.decode(errors="replace").strip()


async def _run_script(path: Path, log_path: Path, *, timeout: float) -> str:
    """Run `path` under bash, return combined stdout+stderr text."""
    from swebench.harness.constants import TESTS_TIMEOUT

    proc = await asyncio.create_subprocess_exec(
        "bash", str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out.decode(errors="replace")
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        return f"{TESTS_TIMEOUT}\nscript {path.name} timed out after {timeout}s\n"


__all__ = ["clean", "get_patch", "eval", "CleanResult", "EvalResult"]
