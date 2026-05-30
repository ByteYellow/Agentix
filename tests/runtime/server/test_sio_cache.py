"""Unit tests for the bounded unacked-result cache in the RPC server."""

from __future__ import annotations

from agentix.runtime.server.sio import _store_pending_result


def _val(tag: str) -> tuple[str, dict[str, object]]:
    return ("call:result", {"call_id": tag})


def test_under_cap_keeps_everything() -> None:
    cache: dict[str, tuple[str, dict[str, object]]] = {}
    for i in range(3):
        assert _store_pending_result(cache, f"c{i}", _val(f"c{i}"), cap=5) is None
    assert list(cache) == ["c0", "c1", "c2"]


def test_over_cap_evicts_oldest_first() -> None:
    cache: dict[str, tuple[str, dict[str, object]]] = {}
    for i in range(5):
        _store_pending_result(cache, f"c{i}", _val(f"c{i}"), cap=3)
    # Only the three newest survive; the cache never exceeds the cap.
    assert len(cache) == 3
    assert list(cache) == ["c2", "c3", "c4"]


def test_eviction_returns_evicted_call_id() -> None:
    cache: dict[str, tuple[str, dict[str, object]]] = {}
    _store_pending_result(cache, "a", _val("a"), cap=1)
    evicted = _store_pending_result(cache, "b", _val("b"), cap=1)
    assert evicted == "a"
    assert list(cache) == ["b"]
