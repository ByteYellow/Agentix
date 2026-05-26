"""Tests for the local Docker deployment backend."""

from __future__ import annotations

import asyncio

import agentix.deployment.docker as docker_mod
import pytest
from agentix.deployment.docker import DockerDeployment, DockerDeploymentConfig

from agentix.deployment.base import SandboxConfig, SandboxResource


def test_carrier_name_includes_platform() -> None:
    amd64 = docker_mod._carrier_name("bundle:pytest", "linux/amd64")
    arm64 = docker_mod._carrier_name("bundle:pytest", "linux/arm64")

    assert amd64 != arm64
    assert docker_mod._carrier_name("bundle:pytest") == docker_mod._carrier_name("bundle:pytest")


@pytest.mark.asyncio
async def test_create_passes_platform_to_carrier_and_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    async def fake_docker(
        *args: str,
        config: DockerDeploymentConfig | None = None,
        check: bool = True,
        retries: int = 0,
    ) -> tuple[int, bytes, bytes]:
        del config, check, retries
        calls.append(args)
        if args[0] == "inspect":
            return 1, b"", b""
        return 0, b"", b""

    async def fake_wait_healthy(self: DockerDeployment, port: int) -> None:
        return None

    monkeypatch.setattr(docker_mod, "_docker", fake_docker)
    monkeypatch.setattr(DockerDeployment, "_allocate_port", staticmethod(lambda: 18000))
    monkeypatch.setattr(DockerDeployment, "_wait_healthy", fake_wait_healthy)

    deployment = DockerDeployment()
    await deployment.create(
        SandboxConfig(
            image="python:3.13-slim",
            bundle="bundle:pytest",
            platform="linux/amd64",
        )
    )

    create_call = next(call for call in calls if call[0] == "create")
    start_call = next(call for call in calls if call[0] == "start")
    run_call = next(call for call in calls if call[0] == "run")

    assert create_call[1:3] == ("--platform", "linux/amd64")
    assert create_call[-3:] == ("bundle:pytest", "-c", "true")
    assert create_call[create_call.index("--entrypoint") + 1] == "/bin/sh"
    assert start_call[1:] == ("-a", docker_mod._carrier_name("bundle:pytest", "linux/amd64"))
    assert run_call[1:3] == ("--platform", "linux/amd64")
    assert run_call[run_call.index("-p") + 1] == "127.0.0.1:18000:18000"
    assert "--network" not in run_call
    # The bundle's own /nix/runtime/bootstrap.sh is the container entry
    # point — no more `-c '<inline bootstrap>'` indirection. The script
    # ships with the bundle (built by `agentix/builder/bundle-build.sh`
    # from `agentix/builder/bootstrap.sh`). The path lives on
    # `agentix.runtime.BUNDLE_RUNTIME_ENTRYPOINT` so every backend reads
    # the same constant — it's the runtime's contract, not any one
    # backend's convention.
    from agentix.runtime import BUNDLE_RUNTIME_ENTRYPOINT

    assert run_call[-1] == "python:3.13-slim"
    assert "-c" not in run_call
    assert run_call[run_call.index("--entrypoint") + 1] == BUNDLE_RUNTIME_ENTRYPOINT
    assert BUNDLE_RUNTIME_ENTRYPOINT == "/nix/runtime/bootstrap.sh"


@pytest.mark.asyncio
async def test_create_passes_resource_limits_and_extra_runner_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    async def fake_docker(
        *args: str,
        config: DockerDeploymentConfig | None = None,
        check: bool = True,
        retries: int = 0,
    ) -> tuple[int, bytes, bytes]:
        del config, check, retries
        calls.append(args)
        if args[0] == "inspect":
            return 1, b"", b""
        return 0, b"", b""

    async def fake_wait_healthy(self: DockerDeployment, port: int) -> None:
        return None

    monkeypatch.setattr(docker_mod, "_docker", fake_docker)
    monkeypatch.setattr(DockerDeployment, "_allocate_port", staticmethod(lambda: 18001))
    monkeypatch.setattr(DockerDeployment, "_wait_healthy", fake_wait_healthy)

    deployment = DockerDeployment(
        DockerDeploymentConfig(
            create_args=["--pull=never"],
            run_args=["--runtime=crun", "--cgroups=disabled"],
        )
    )
    await deployment.create(
        SandboxConfig(
            image="python:3.13-slim",
            bundle="bundle:pytest",
            resource=SandboxResource(cpu=4, memory="16g", gpu=2),
        )
    )

    create_call = next(call for call in calls if call[0] == "create")
    run_call = next(call for call in calls if call[0] == "run")

    assert "--pull=never" in create_call
    assert "--runtime=crun" in create_call
    assert "--cgroups=disabled" in create_call
    assert run_call[run_call.index("--cpus") + 1] == "4"
    assert run_call[run_call.index("--memory") + 1] == "16g"
    assert run_call[run_call.index("--gpus") + 1] == "2"
    assert "--runtime=crun" in run_call
    assert "--cgroups=disabled" in run_call


@pytest.mark.asyncio
async def test_host_network_binds_runtime_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    async def fake_docker(
        *args: str,
        config: DockerDeploymentConfig | None = None,
        check: bool = True,
        retries: int = 0,
    ) -> tuple[int, bytes, bytes]:
        del config, check, retries
        calls.append(args)
        if args[0] == "inspect":
            return 1, b"", b""
        return 0, b"", b""

    async def fake_wait_healthy(self: DockerDeployment, port: int) -> None:
        return None

    monkeypatch.setattr(docker_mod, "_docker", fake_docker)
    monkeypatch.setattr(DockerDeployment, "_allocate_port", staticmethod(lambda: 18004))
    monkeypatch.setattr(DockerDeployment, "_wait_healthy", fake_wait_healthy)

    deployment = DockerDeployment(DockerDeploymentConfig(network="host"))
    await deployment.create(SandboxConfig(image="python:3.13-slim", bundle="bundle:pytest"))

    run_call = next(call for call in calls if call[0] == "run")
    assert "--network" in run_call
    assert run_call[run_call.index("--network") + 1] == "host"
    assert "-p" not in run_call
    assert "-e" in run_call
    assert "AGENTIX_BIND_HOST=127.0.0.1" in run_call


def test_gpu_args_can_be_overridden_for_podman_cdi() -> None:
    config = DockerDeploymentConfig(gpu_args=["--device", "nvidia.com/gpu=all", "--label", "gpu-count={gpu}"])

    assert docker_mod._resource_args(SandboxResource(gpu=2), config) == [
        "--device",
        "nvidia.com/gpu=all",
        "--label",
        "gpu-count=2",
    ]


def test_publish_host_can_be_omitted_for_podman_cni() -> None:
    assert docker_mod._port_mapping(18002) == "127.0.0.1:18002:18002"

    assert docker_mod._port_mapping(18002, DockerDeploymentConfig(publish_host="")) == "18002:18002"


def test_network_mode_disables_port_publishing() -> None:
    assert docker_mod._network_args() == []
    assert docker_mod._publish_args(18003) == ["-p", "127.0.0.1:18003:18003"]

    slirp = DockerDeploymentConfig(network="slirp4netns")
    assert docker_mod._network_args(slirp) == ["--network", "slirp4netns"]
    assert docker_mod._publish_args(18003, slirp) == ["-p", "127.0.0.1:18003:18003"]

    host = DockerDeploymentConfig(network="host")
    assert docker_mod._network_args(host) == ["--network", "host"]
    assert docker_mod._publish_args(18003, host) == []


@pytest.mark.asyncio
async def test_container_bin_config_selects_podman(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    class FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b""

    async def fake_exec(*args: str, **kwargs: object) -> FakeProc:
        calls.append(args)
        assert kwargs["stdout"] == asyncio.subprocess.PIPE
        assert kwargs["stderr"] == asyncio.subprocess.PIPE
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    await docker_mod._docker("ps", config=DockerDeploymentConfig(container_bin="podman"))

    assert calls == [("podman", "ps")]


@pytest.mark.asyncio
async def test_carrier_recreated_when_runtime_tag_moves(monkeypatch: pytest.MonkeyPatch) -> None:
    carrier = docker_mod._carrier_name("bundle:pytest", "linux/amd64")
    calls: list[tuple[str, ...]] = []

    async def fake_docker(
        *args: str,
        config: DockerDeploymentConfig | None = None,
        check: bool = True,
        retries: int = 0,
    ) -> tuple[int, bytes, bytes]:
        del config, check, retries
        calls.append(args)
        if args == ("inspect", carrier):
            return 0, b"", b""
        if args == ("inspect", "-f", "{{.Image}}", carrier):
            return 0, b"sha256:old\n", b""
        if args == ("image", "inspect", "-f", "{{.Id}}", "bundle:pytest"):
            return 0, b"sha256:new\n", b""
        return 0, b"", b""

    monkeypatch.setattr(docker_mod, "_docker", fake_docker)

    deployment = DockerDeployment()
    assert await deployment._ensure_carrier("bundle:pytest", "linux/amd64") == carrier

    rm_call = calls.index(("rm", "-f", carrier))
    create_call = calls.index(
        (
            "create",
            "--platform",
            "linux/amd64",
            "--name",
            carrier,
            "--entrypoint",
            "/bin/sh",
            "bundle:pytest",
            "-c",
            "true",
        )
    )
    start_call = calls.index(("start", "-a", carrier))
    assert rm_call < create_call
    assert create_call < start_call
