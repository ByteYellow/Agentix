"""CLI for the Agentix TUI.

- `agentix-eval-tui --demo 40` — synthetic, no-Docker rollouts.
- `agentix-eval-tui --dataset m:d --agent m:a --bundle eval:0.1.0` — real run,
  adapters resolved like `agentix-run`.
- `agentix-eval-tui` — no run; browse the Catalog (and the planned tabs).
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Any

from .app import AgentixTUI
from .models import RunSpec


def _load(path: str) -> Any:
    module_name, sep, attr = path.partition(":")
    if not module_name or not sep or not attr:
        raise SystemExit(f"expected 'module:attr', got {path!r}")
    obj = getattr(importlib.import_module(module_name), attr)
    return obj() if isinstance(obj, type) else obj


def _load_provider(name_or_path: str) -> Any:
    if ":" in name_or_path:
        return _load(name_or_path)
    module = importlib.import_module(f"agentix.provider.{name_or_path}")
    classes = [
        value
        for key, value in vars(module).items()
        if isinstance(value, type) and key.endswith("Provider") and value.__module__ == module.__name__
    ]
    if len(classes) != 1:
        raise SystemExit(f"could not find a single *Provider class in agentix.provider.{name_or_path}")
    return classes[0]()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agentix-eval-tui", description="Modern TUI control room for Agentix.")
    parser.add_argument("--demo", type=int, metavar="N", default=None, help="Run N synthetic instances (no Docker).")
    parser.add_argument("--dataset", help="Dataset adapter as 'module:attr'.")
    parser.add_argument("--agent", help="Agent adapter as 'module:attr'.")
    parser.add_argument("--provider", default="docker", help="Provider backend name or 'module:attr'.")
    parser.add_argument("--bundle", help="Agentix bundle reference (from `agentix build`).")
    parser.add_argument("--model", default=None)
    parser.add_argument("--n-concurrent", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args(argv)


def _build_spec(args: argparse.Namespace) -> RunSpec | None:
    if args.demo is not None:
        from .demo import DemoAgent, DemoDataset, DemoProvider

        dataset = DemoDataset(args.demo)
        return RunSpec(
            dataset=dataset,
            agent=DemoAgent(),
            provider=DemoProvider(),
            bundle="demo",
            instances=dataset.instances(),
            n_concurrent=args.n_concurrent,
        )

    given = [bool(args.dataset), bool(args.agent), bool(args.bundle)]
    if not any(given):
        return None  # bare launch: browse the Catalog / planned tabs
    if not all(given):
        raise SystemExit("--dataset, --agent and --bundle must be given together (or use --demo N)")

    dataset = _load(args.dataset)
    instances = list(dataset.instances())
    if args.limit is not None:
        instances = instances[: args.limit]
    return RunSpec(
        dataset=dataset,
        agent=_load(args.agent),
        provider=_load_provider(args.provider),
        bundle=args.bundle,
        model=args.model,
        instances=instances,
        n_concurrent=args.n_concurrent,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    AgentixTUI(rollout_spec=_build_spec(args)).run()
    return 0
