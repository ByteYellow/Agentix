"""mock-agent — reference closure for Agentix integration tests.

Stubs only. The runtime imports `agentix_closures.mock_agent._register`
to get a Dispatcher bound to `_impl`.

`__image__` lets callers pass this module to `SandboxConfig(closures=[...])`
instead of typing the image ref by hand.
"""

from __future__ import annotations

from dataclasses import dataclass

__version__ = "0.1.0"
__image__ = "agentix/mock-agent:0.1.0"


@dataclass
class RunResult:
    exit_code: int
    patch: str


def run(instruction: str, workdir: str = "/") -> RunResult:
    """Run against an instruction; returns a fake patch echoing the input."""
    raise NotImplementedError("call via RuntimeClient.remote(mock_agent.run, ...)")
