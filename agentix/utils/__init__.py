"""agentix.utils — side-channel observability primitives.

Two sub-packages live here:

  - `agentix.utils.log`   — stdlib `logging` bridge (sandbox -> host).
  - `agentix.utils.trace` — OTel-style Trace + Span + SpanEvent.

Both are *side channels* relative to `c.remote(fn, ...)`: they ride
dedicated Socket.IO namespaces (`/log`, `/trace`) and are not part of
the RPC result path.
"""

from __future__ import annotations

from agentix.utils import log, trace

__all__ = ["log", "trace"]
