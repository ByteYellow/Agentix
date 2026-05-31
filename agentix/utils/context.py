"""Unified ambient context, propagated across `c.remote(fn, ...)`.

One process-global, contextvar-backed mapping — *baggage* — that any
code can read and write, plus a *propagator* seam so subsystems carry
their own structured slice across the sandbox boundary. The carrier is
generic; tracing is just one propagator on top of it (it injects
`trace_id` / `parent_span_id` so worker spans nest under the host's
span). Plugins register their own propagators the same way.

User surface (host and sandbox share the *same* API):

    from agentix.utils import context

    context.set(tenant="acme", request_id="r-42")
    with context.scope(attempt=2):
        await client.remote(run, task=task)   # carrier rides along

    # inside the remote `run`, in the sandbox worker:
    context.get("tenant")     # -> "acme"
    context.get("attempt")    # -> 2

Propagation is host → worker only and *automatic*: `remote()` snapshots
the ambient context at call time (`encode()`), and the worker restores
it for the duration of the call (`attach()`) before `fn` runs. An empty
context is free — nothing is captured and nothing ships on the wire.

Baggage values travel by pickle (like the call's arguments), so they
may be arbitrary Python objects; keep them small and picklable.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import pickle
from collections.abc import Iterator, Mapping
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("agentix.utils.context")

# The ambient baggage: an immutable mapping swapped wholesale on every
# mutation, so a `set()` in one task/thread never leaks into another.
_baggage: contextvars.ContextVar[Mapping[str, Any]] = contextvars.ContextVar(
    "agentix_context_baggage",
    default={},
)

_BAGGAGE_KEY = "baggage"


# ── baggage: the built-in unified key/value context ───────────────


def get(key: str, default: Any = None) -> Any:
    """Read one key from the ambient baggage."""
    return _baggage.get().get(key, default)


def snapshot() -> dict[str, Any]:
    """A read-only copy of the full ambient baggage."""
    return dict(_baggage.get())


def set(**values: Any) -> None:
    """Merge `values` into the ambient baggage (sticky for this
    task/thread). For a temporary overlay that auto-reverts, use
    `scope(...)` instead."""
    if not values:
        return
    merged = dict(_baggage.get())
    merged.update(values)
    _baggage.set(merged)


@contextlib.contextmanager
def scope(**values: Any) -> Iterator[dict[str, Any]]:
    """Overlay `values` onto the ambient baggage for the duration of
    the block, then restore the prior state."""
    merged = dict(_baggage.get())
    merged.update(values)
    tok = _baggage.set(merged)
    try:
        yield merged
    finally:
        _baggage.reset(tok)


def clear() -> None:
    """Drop all ambient baggage (sticky). Mostly for tests."""
    _baggage.set({})


# ── propagator seam: how subsystems carry their own slice ─────────


@runtime_checkable
class Propagator(Protocol):
    """A participant in cross-boundary context propagation.

    `key` names this propagator's slice in the carrier. `inject()` runs
    host-side at capture and returns a picklable value (or `None` to
    contribute nothing); `extract(value)` runs worker-side and returns a
    context manager that applies the slice for the duration of the call.

    Tracing implements this in `agentix.utils.trace`; it is just one
    propagator — the carrier itself knows nothing about spans.
    """

    key: str

    def inject(self) -> Any: ...

    def extract(self, value: Any) -> contextlib.AbstractContextManager[Any]: ...


_propagators: list[Propagator] = []


def register_propagator(p: Propagator) -> None:
    """Register a `Propagator`. Raises if its `key` is already taken
    (`baggage` is reserved for the built-in carrier)."""
    if p.key == _BAGGAGE_KEY:
        raise ValueError(f"propagator key {_BAGGAGE_KEY!r} is reserved")
    for existing in _propagators:
        if existing.key == p.key:
            raise ValueError(f"context propagator {p.key!r} already registered")
    _propagators.append(p)


def get_propagators() -> list[Propagator]:
    return list(_propagators)


# ── capture / restore across the remote() boundary ────────────────


def capture() -> dict[str, Any]:
    """Snapshot the full ambient context — baggage plus every
    propagator's slice — into a serializable carrier dict. Empty keys
    are omitted, so an unused context captures to `{}`."""
    carrier: dict[str, Any] = {}
    bag = _baggage.get()
    if bag:
        carrier[_BAGGAGE_KEY] = dict(bag)
    for p in _propagators:
        try:
            slice_ = p.inject()
        except Exception:
            logger.debug("context propagator %r inject() raised", p.key, exc_info=True)
            slice_ = None
        if slice_ is not None:
            carrier[p.key] = slice_
    return carrier


@contextlib.contextmanager
def attach(carrier: Mapping[str, Any] | None) -> Iterator[None]:
    """Restore a captured `carrier` for the duration of the block:
    overlay its baggage and enter each propagator's `extract(...)`. A
    falsy carrier is a no-op."""
    if not carrier:
        yield
        return
    with contextlib.ExitStack() as stack:
        bag = carrier.get(_BAGGAGE_KEY)
        if isinstance(bag, Mapping) and bag:
            stack.enter_context(scope(**dict(bag)))
        for p in _propagators:
            if p.key not in carrier:
                continue
            try:
                stack.enter_context(p.extract(carrier[p.key]))
            except Exception:
                logger.debug("context propagator %r extract() raised", p.key, exc_info=True)
        yield


def encode() -> bytes | None:
    """Capture the ambient context and serialize it for the wire.
    Returns `None` when there is nothing to carry."""
    carrier = capture()
    if not carrier:
        return None
    return pickle.dumps(carrier)


def decode(blob: bytes | None) -> dict[str, Any]:
    """Inverse of `encode()` — `None`/empty decodes to `{}`."""
    if not blob:
        return {}
    value = pickle.loads(blob)
    return value if isinstance(value, dict) else {}


__all__ = [
    "Propagator",
    "attach",
    "capture",
    "clear",
    "decode",
    "encode",
    "get",
    "get_propagators",
    "register_propagator",
    "scope",
    "set",
    "snapshot",
]
