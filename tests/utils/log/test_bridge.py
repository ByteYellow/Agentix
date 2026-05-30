"""Tests for the worker→host logging bridge payload."""

from __future__ import annotations

import logging
from decimal import Decimal

from agentix.runtime.shared.codec import pack
from agentix.utils.log._bridge import _coerce_extra, _record_payload


def _record(**extras: object) -> logging.LogRecord:
    record = logging.LogRecord("test", logging.INFO, "p.py", 10, "hello %s", ("world",), None)
    for key, value in extras.items():
        setattr(record, key, value)
    return record


def test_coerce_extra_keeps_native_types() -> None:
    assert _coerce_extra("s") == "s"
    assert _coerce_extra(3) == 3
    assert _coerce_extra(True) is True
    assert _coerce_extra(None) is None
    assert _coerce_extra([1, "a"]) == [1, "a"]
    assert _coerce_extra({"k": 2}) == {"k": 2}


def test_coerce_extra_reprs_unencodable() -> None:
    class Weird:
        def __repr__(self) -> str:
            return "<weird>"

    assert _coerce_extra(Weird()) == "<weird>"
    assert _coerce_extra(Decimal("1.5")) == "Decimal('1.5')"
    assert _coerce_extra({"obj": Weird()}) == {"obj": "<weird>"}


def test_record_payload_is_always_packable() -> None:
    class Weird:
        def __repr__(self) -> str:
            return "<weird>"

    payload = _record_payload(_record(obj=Weird(), count=3, label="x"))
    extras = payload["extras"]
    assert extras == {"obj": "<weird>", "count": 3, "label": "x"}
    # The whole frame must now msgpack-encode (regression: a non-serializable
    # extra previously made the drainer drop the record).
    assert pack(payload)
