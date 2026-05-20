"""Host-side orchestrator: evaluate Claude Code on SWE-bench Verified.

Per instance, two sandboxes back-to-back:

    1. Agent sandbox (base = `swebench/sweb.eval.x86_64.<id>:latest`)
         - register `agentix.bridge.anthropic.OpenAIGateway` on the host RuntimeClient
         - c.remote(swe.clean, /testbed, base_commit)
         - c.remote(agentix.bridge.anthropic.start_service, ...)
         - c.remote(cc.run, ..., anthropic_base_url=svc.url)
         - c.remote(swe.get_patch, /testbed)

    2. Eval sandbox (fresh container, no LLM gateway)
         - c.remote(swe.eval, instance=..., patch=...)

Host wires an `openai.AsyncOpenAI` client into `AnthropicGateway` so
the actual provider call (model-eval, OpenRouter, etc.) lives on the
host. The sandbox-side `abridge` service just translates Anthropic ↔
OpenAI and routes via the `/abridge` SIO namespace.

Run as `python -m runner --limit N` or `python runner.py --limit N`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import agentix.bridge.anthropic
import cc
import swe
from agentix.deployment.docker import DockerDeployment
from datasets import load_dataset
from openai import AsyncOpenAI

from agentix import RuntimeClient
from agentix.deployment.base import SandboxConfig, session

WORKDIR = "/testbed"
logger = logging.getLogger("eval_cc_swe.runner")


def _instance_image(instance: dict, *, namespace: str, tag: str, arch: str) -> str:
    iid = instance["instance_id"].lower()
    return f"{namespace}/sweb.eval.{arch}.{iid}:{tag}".replace("__", "_1776_")


def _make_openai_client(*, base_url: str, api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


async def _run_agent_phase(
    inst: dict,
    *,
    cfg: SandboxConfig,
    openai_base_url: str,
    openai_api_key: str,
    upstream_model: str,
    response_model: str,
    cc_timeout: float,
    max_turns: int | None,
) -> dict:
    """Spin the agent sandbox: clean → start abridge → cc.run → get_patch."""
    iid = inst["instance_id"]

    gateway = agentix.bridge.anthropic.OpenAIGateway(
        client=_make_openai_client(base_url=openai_base_url, api_key=openai_api_key),
        upstream_model=upstream_model,
    )

    async with session(DockerDeployment(), cfg) as sandbox:
        client = RuntimeClient(sandbox.runtime_url)
        client.register_namespace(gateway)
        async with client as c:
            cleaned = await c.remote(
                swe.clean, workdir=WORKDIR, base_commit=inst["base_commit"],
            )
            if not cleaned.ok:
                print(f"[{iid}] clean failed:\n{cleaned.log[-500:]}")
                return {"instance_id": iid, "skipped": "clean_failed"}
            print(f"[{iid}] HEAD={cleaned.head[:12]}")

            svc = await c.remote(
                agentix.bridge.anthropic.start_service,
                response_model=response_model,
            )
            print(f"[{iid}] abridge service at {svc.url}")

            print(f"[{iid}] running claude (model={response_model})")
            cc_res = await c.remote(
                cc.run,
                instruction=inst["problem_statement"],
                workdir=WORKDIR,
                timeout=cc_timeout,
                max_turns=max_turns,
                anthropic_base_url=svc.url,
                anthropic_model=response_model,
            )
            print(f"[{iid}] claude exit={cc_res.exit_code}")
            if cc_res.stderr_tail:
                print(f"[{iid}] stderr_tail:\n{cc_res.stderr_tail.rstrip()}")

            patch = await c.remote(swe.get_patch, workdir=WORKDIR)
            try:
                await c.remote(agentix.bridge.anthropic.stop_service, handle=svc)
            except Exception:
                pass

    return {"instance_id": iid, "patch": patch, "claude_exit": cc_res.exit_code}


async def _run_eval_phase(
    inst: dict, *, cfg: SandboxConfig, patch: str, eval_timeout: float,
) -> swe.EvalResult:
    async with session(DockerDeployment(), cfg) as sandbox:
        async with RuntimeClient(sandbox.runtime_url) as c:
            return await c.remote(
                swe.eval, instance=inst, patch=patch, eval_timeout=eval_timeout,
            )


async def solve_one(
    inst: dict,
    *,
    bundle_image: str,
    swebench_namespace: str,
    swebench_tag: str,
    arch: str,
    openai_base_url: str,
    openai_api_key: str,
    upstream_model: str,
    response_model: str,
    cc_timeout: float,
    eval_timeout: float,
    max_turns: int | None,
    out_dir: Path,
) -> dict:
    iid = inst["instance_id"]
    base_image = _instance_image(
        inst, namespace=swebench_namespace, tag=swebench_tag, arch=arch,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = SandboxConfig(image=base_image, runtime_image=bundle_image)

    print(f"[{iid}] agent sandbox: {base_image}")
    started = time.time()
    agent = await _run_agent_phase(
        inst, cfg=cfg,
        openai_base_url=openai_base_url,
        openai_api_key=openai_api_key,
        upstream_model=upstream_model,
        response_model=response_model,
        cc_timeout=cc_timeout, max_turns=max_turns,
    )
    if "patch" not in agent:
        return agent

    patch: str = agent["patch"]
    (out_dir / f"{iid}.patch").write_text(patch)
    print(f"[{iid}] patch_bytes={len(patch)}")
    if not patch.strip():
        return {"instance_id": iid, "skipped": "empty_patch"}

    print(f"[{iid}] eval sandbox")
    ev = await _run_eval_phase(
        inst, cfg=cfg, patch=patch, eval_timeout=eval_timeout,
    )

    summary = {
        "instance_id": iid,
        "resolved": ev.resolved,
        "patch_applied": ev.patch_applied,
        "apply_cmd": ev.apply_cmd,
        "fail_to_pass": ev.fail_to_pass,
        "pass_to_pass": ev.pass_to_pass,
        "duration_s": round(time.time() - started, 1),
    }
    (out_dir / f"{iid}.json").write_text(json.dumps(summary, indent=2))

    verdict = "PASS" if ev.resolved else "FAIL"
    ftp_ok = len(ev.fail_to_pass.get("success", []))
    ftp_n = ftp_ok + len(ev.fail_to_pass.get("failure", []))
    print(
        f"[{iid}] {verdict}  patch_applied={ev.patch_applied}  "
        f"resolved={ftp_ok}/{ftp_n}  "
        f"regressions={len(ev.pass_to_pass.get('failure', []))}  "
        f"({summary['duration_s']}s)"
    )
    return summary


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle-image", default="eval-cc-swe:0.2.0")
    parser.add_argument("--swebench-namespace", default="swebench")
    parser.add_argument("--swebench-tag", default="latest")
    parser.add_argument("--arch", default="x86_64", choices=["x86_64", "arm64"])
    parser.add_argument("--dataset", default="princeton-nlp/SWE-bench_Verified")
    parser.add_argument("--split", default="test")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--instance-id", action="append", default=None)
    parser.add_argument(
        "--openai-base-url",
        default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    parser.add_argument(
        "--openai-api-key",
        default=os.environ.get("OPENAI_API_KEY", ""),
    )
    parser.add_argument(
        "--upstream-model",
        default=os.environ.get("UPSTREAM_MODEL", "gpt-4o-mini"),
        help="Model id sent to the upstream OpenAI-compatible provider.",
    )
    parser.add_argument(
        "--response-model",
        default=os.environ.get("RESPONSE_MODEL", "claude-3-5-sonnet-latest"),
        help="Model id echoed back to the agent (claude CLI).",
    )
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--cc-timeout", type=float, default=1800)
    parser.add_argument("--eval-timeout", type=float, default=1800)
    parser.add_argument("--out", default="runs")
    args = parser.parse_args(argv)

    if not args.openai_api_key:
        print(
            "error: --openai-api-key (or OPENAI_API_KEY) is required",
            file=sys.stderr,
        )
        return 2

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
    )

    ds = load_dataset(args.dataset, split=args.split)
    if args.instance_id:
        wanted = set(args.instance_id)
        instances = [dict(row) for row in ds if row["instance_id"] in wanted]
    else:
        instances = [dict(ds[i]) for i in range(args.limit)]

    out_dir = Path(args.out)
    summaries: list[dict] = []
    for inst in instances:
        iid = inst["instance_id"]
        try:
            s = await solve_one(
                inst,
                bundle_image=args.bundle_image,
                swebench_namespace=args.swebench_namespace,
                swebench_tag=args.swebench_tag,
                arch=args.arch,
                openai_base_url=args.openai_base_url,
                openai_api_key=args.openai_api_key,
                upstream_model=args.upstream_model,
                response_model=args.response_model,
                cc_timeout=args.cc_timeout,
                eval_timeout=args.eval_timeout,
                max_turns=args.max_turns,
                out_dir=out_dir,
            )
        except Exception as exc:
            # One instance blowing up (sandbox error, lost connection,
            # ...) must not abort the whole run — record and move on.
            logger.exception("[%s] crashed", iid)
            s = {"instance_id": iid, "error": f"{type(exc).__name__}: {exc}"}
        summaries.append(s)

    resolved = sum(1 for s in summaries if s.get("resolved"))
    print(f"\n{resolved}/{len(summaries)} resolved")
    (out_dir / "summary.json").write_text(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
