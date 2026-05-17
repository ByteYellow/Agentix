"""Debug helper: pretty-print a msgpack-encoded RPC frame or payload.

Usage:
    python -m agentix.runtime.shared.dump_frame <file>            # auto-detect framed vs raw
    python -m agentix.runtime.shared.dump_frame --framed <file>   # length-prefixed worker frame
    python -m agentix.runtime.shared.dump_frame --raw    <file>   # bare msgpack (HTTP body, SIO arg)

Reads bytes from `<file>` (or stdin if `-`), unpacks via `agentix.runtime.shared.codec`,
pretty-prints the resulting Python object.
"""

from __future__ import annotations

import argparse
import pprint
import struct
import sys
from pathlib import Path

from agentix.runtime.shared.codec import unpack


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentix.runtime.shared.dump_frame", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="path to frame file, or '-' for stdin")
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--framed", action="store_true",
                   help="length-prefixed frame (worker stdio shape)")
    g.add_argument("--raw", action="store_true",
                   help="bare msgpack bytes (HTTP body / SIO arg shape)")
    args = parser.parse_args(argv)

    blob = sys.stdin.buffer.read() if args.file == "-" else Path(args.file).read_bytes()

    if args.raw or (not args.framed and not blob.startswith(b"\x00\x00\x00")):
        # Heuristic: framed always starts with a 4-byte length; if first 3
        # bytes look like a small int (< 16M frame), assume framed.
        if not args.raw and len(blob) >= 4:
            (n,) = struct.unpack("<I", blob[:4])
            if 0 < n <= len(blob) - 4:
                payload = blob[4 : 4 + n]
                pprint.pp(unpack(payload))
                return 0
        pprint.pp(unpack(blob))
        return 0

    if len(blob) < 4:
        print("frame too short for length prefix", file=sys.stderr)
        return 1
    (n,) = struct.unpack("<I", blob[:4])
    payload = blob[4 : 4 + n]
    pprint.pp(unpack(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
