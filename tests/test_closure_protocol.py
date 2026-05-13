"""Protocol-level integration tests for the runtime server + loader.

Uses the real ClosureLoader against an ephemeral echo closure — no mocks.
The `mount_closure` fixture mimics what the deployment layer does: expose
the closure at /mnt/<namespace>/entry, so loader.load() can find it.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from agentix.models import AGENTIX_CLOSURE_ABI, ClosureManifest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def server_module(tmp_socket_dir: Path):
    """Reload agentix.runtime.server with the tmp socket dir + mount root in effect."""
    import importlib
    import sys

    for mod in ["agentix.runtime.loader", "agentix.runtime.server"]:
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])

    from agentix.runtime import server

    return server


async def test_load_unload_manifest(
    server_module, echo_closure: Path, echo_manifest: ClosureManifest, mount_closure
):
    loader = server_module.loader
    mount_closure(echo_closure, "echo")
    closure = await loader.load("echo", manifest=echo_manifest)
    try:
        assert closure.name == "echo"
        assert closure.manifest.name == "echo"
        assert closure.manifest.abi == AGENTIX_CLOSURE_ABI
        assert any(e.path == "/echo" for e in closure.manifest.endpoints)
    finally:
        await loader.unload("echo")
        assert "echo" not in {c.name for c in loader.list_closures()}


async def test_reverse_proxy_via_http(
    server_module, echo_closure: Path, echo_manifest: ClosureManifest, mount_closure
):
    loader = server_module.loader
    mount_closure(echo_closure, "echo")
    await loader.load("echo", manifest=echo_manifest)
    try:
        transport = httpx.ASGITransport(app=server_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            r = await http.get("/closures")
            assert r.status_code == 200
            names = [x["name"] for x in r.json()]
            assert "echo" in names

            r = await http.post("/echo/echo", json={"hello": "world"})
            assert r.status_code == 200
            assert r.json() == {"path": "/echo", "data": {"hello": "world"}}

            r = await http.post("/nope/whatever", json={})
            assert r.status_code == 502
            assert r.json()["namespace"] == "nope"
    finally:
        await loader.unload("echo")


async def test_logs_endpoint(
    server_module, echo_closure: Path, echo_manifest: ClosureManifest, mount_closure
):
    loader = server_module.loader
    mount_closure(echo_closure, "echo")
    await loader.load("echo", manifest=echo_manifest)
    try:
        closure = loader.get("echo")
        for _ in range(3):
            r = await closure.client.post("/echo", json={"n": 1})
            assert r.status_code == 200
        import asyncio

        await asyncio.sleep(0.2)
        stdout, _stderr = loader.logs("echo")
        assert "handled POST" in stdout or "listening on" in stdout
    finally:
        await loader.unload("echo")


async def test_load_missing_closure(server_module):
    """Loading a namespace with no /mnt/<ns>/entry/bin/start raises."""
    loader = server_module.loader
    manifest = ClosureManifest(abi=AGENTIX_CLOSURE_ABI, name="missing", version="0.0.0")
    with pytest.raises(FileNotFoundError):
        await loader.load("does-not-exist", manifest=manifest)


async def test_multiple_closures_compose(
    server_module, echo_closure: Path, echo_manifest: ClosureManifest, mount_closure
):
    """Two closures mounted under different namespaces coexist and route
    independently — the regression guard for the multi-closure composition
    bug we fixed by moving to per-closure /mnt/<ns> mounts.
    """
    loader = server_module.loader
    mount_closure(echo_closure, "agent")
    mount_closure(echo_closure, "dataset")
    await loader.load("agent", manifest=echo_manifest)
    await loader.load("dataset", manifest=echo_manifest)
    try:
        names = {c.name for c in loader.list_closures()}
        assert names == {"agent", "dataset"}

        # Each closure has its own socket; their subprocesses are independent.
        a, d = loader.get("agent"), loader.get("dataset")
        assert a.socket_path != d.socket_path
        assert a.process.pid != d.process.pid

        # Both respond via the reverse proxy, with namespace isolation.
        transport = httpx.ASGITransport(app=server_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            r1 = await http.post("/agent/echo", json={"from": "agent"})
            r2 = await http.post("/dataset/echo", json={"from": "dataset"})
            assert r1.status_code == 200 and r1.json()["data"] == {"from": "agent"}
            assert r2.status_code == 200 and r2.json()["data"] == {"from": "dataset"}
    finally:
        await loader.unload("agent")
        await loader.unload("dataset")


async def test_auto_load_scans_mount_root(server_module, echo_closure: Path, mount_closure):
    """Runtime's startup scan picks up every /mnt/<ns> with a valid
    entry/manifest.json, except `runtime`.
    """
    mount_closure(echo_closure, "agent")
    mount_closure(echo_closure, "dataset")
    mount_closure(echo_closure, "runtime")  # should be skipped

    loader = server_module.loader
    try:
        await server_module._auto_load()
        names = {c.name for c in loader.list_closures()}
        assert names == {"agent", "dataset"}, f"runtime/ must be skipped; got {names}"
    finally:
        for ns in ("agent", "dataset"):
            if ns in {c.name for c in loader.list_closures()}:
                await loader.unload(ns)


async def test_auto_load_skips_without_manifest(
    server_module, echo_closure: Path, mount_root: Path, mount_closure
):
    """A /mnt/<ns> directory without entry/manifest.json is not a closure;
    auto-load must skip it without crashing (and without forking anything).
    Lets non-closure mounts (task data, caches) coexist under /mnt.
    """
    # Real closure
    mount_closure(echo_closure, "real")
    # Non-closure mount: has entry/bin/start but no manifest.json. Build a
    # sibling tree so the symlink-mount doesn't share echo_closure's manifest.
    bogus_src = mount_root.parent / "bogus-src"
    (bogus_src / "bin").mkdir(parents=True, exist_ok=True)
    (bogus_src / "bin" / "start").write_text("#!/bin/sh\nsleep 1\n")
    (bogus_src / "bin" / "start").chmod(0o755)
    mount_closure(bogus_src, "bogus")

    loader = server_module.loader
    try:
        await server_module._auto_load()
        names = {c.name for c in loader.list_closures()}
        assert names == {"real"}, f"closure-less mount must be skipped; got {names}"
    finally:
        if "real" in {c.name for c in loader.list_closures()}:
            await loader.unload("real")


async def test_auto_load_skips_wrong_abi(
    server_module, echo_closure: Path, mount_root: Path, mount_closure
):
    """A mount whose manifest declares a non-matching abi is treated as
    incompatible and skipped.
    """
    incompat_src = mount_root.parent / "incompat-src"
    (incompat_src / "bin").mkdir(parents=True, exist_ok=True)
    (incompat_src / "bin" / "start").write_text("#!/bin/sh\nsleep 1\n")
    (incompat_src / "bin" / "start").chmod(0o755)
    (incompat_src / "manifest.json").write_text(
        '{"abi": 999, "name": "future", "version": "9.9.9"}'
    )
    mount_closure(incompat_src, "future")

    loader = server_module.loader
    await server_module._auto_load()
    assert "future" not in {c.name for c in loader.list_closures()}
