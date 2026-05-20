"""agentix.bridge — provider-shape HTTP services that bridge the agentix
sandbox boundary so credentials and HTTP calls stay host-side.

Two services today, one subpackage each:

    import agentix.bridge.anthropic   # /v1/messages → OpenAI on host
    import agentix.bridge.oai         # /v1/chat/completions → OpenAI on host

(`oai` rather than `openai` so it doesn't shadow the upstream
`openai` package — same idea as `agentixx` on PyPI.)

Each subpackage exports the same surface: `start_service` (sandbox-side
async function for `c.remote`), `stop_service`, `Gateway` (host-side
namespace handler), and `NAMESPACE` (the SIO path it owns).
"""

from __future__ import annotations

__version__ = "0.2.0"

__all__ = ["__version__"]
