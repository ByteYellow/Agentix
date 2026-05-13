"""Helpers for writing an Agentix closure.

A closure's entry point must bind a Unix-socket HTTP server on the path the
runtime provides via `AGENTIX_SOCKET`. `serve()` wraps the uvicorn invocation
so authors only write their FastAPI (or any ASGI) app.

Typical __main__.py for a Python closure:

    from agentix.closure import serve
    from my_closure.app import app

    if __name__ == "__main__":
        serve(app)

For local dev without a sandbox, pass `socket_path=` explicitly:

    serve(app, socket_path="/tmp/my.sock")
    # another shell: curl --unix-socket /tmp/my.sock http://x/
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agentix.models import AGENTIX_CLOSURE_ABI, ClosureManifest, Endpoint


def serve(app: Any, *, socket_path: str | None = None, **uvicorn_kwargs: Any) -> None:
    """Bind an ASGI app to the Agentix-provided Unix socket.

    Reads `AGENTIX_SOCKET` from env unless `socket_path` is given explicitly.
    Extra kwargs are forwarded to `uvicorn.run` (e.g. `log_level="warning"`).
    """
    import uvicorn

    sock = socket_path or os.environ.get("AGENTIX_SOCKET")
    if not sock:
        raise RuntimeError(
            "AGENTIX_SOCKET not set; pass socket_path=... for local dev"
        )
    uvicorn.run(app, uds=sock, **uvicorn_kwargs)


def write_manifest(
    entry_dir: str | os.PathLike[str],
    *,
    name: str,
    version: str,
    description: str | None = None,
    kind: str | None = None,
    endpoints: list[Endpoint] | list[dict[str, Any]] | None = None,
) -> Path:
    """Emit `<entry_dir>/manifest.json` for a closure image build.

    Call this from your closure's build script (Dockerfile RUN, nix
    `runCommand`, Makefile, whatever) so the final image carries the file
    at `/nix/entry/manifest.json`. The runtime reads this file to identify
    `/mnt/<ns>` as a closure and to know what ABI it speaks.

    Returns the path written. Raises if `entry_dir` does not exist.
    """
    entry = Path(entry_dir)
    if not entry.is_dir():
        raise FileNotFoundError(f"entry_dir does not exist: {entry}")
    manifest = ClosureManifest(
        abi=AGENTIX_CLOSURE_ABI,
        name=name,
        version=version,
        description=description,
        kind=kind,
        endpoints=[Endpoint.model_validate(e) for e in (endpoints or [])],
    )
    out = entry / "manifest.json"
    out.write_text(manifest.model_dump_json())
    return out
