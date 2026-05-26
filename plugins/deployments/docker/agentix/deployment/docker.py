"""Docker deployment: sandbox CRUD via a Docker-compatible CLI.

Design:

  Two images, one container. `config.bundle` is the generic
  Agentix bundle from `agentix build` (carries `/nix/runtime/bin/` and
  the full Python closure under `/nix/store/...`). `config.image` is
  the task-specific base the workload runs against. The runtime is
  overlaid onto the task container's `/nix` so the
  `/nix/runtime/bootstrap.sh` entry point and its store paths resolve
  regardless of the task image's distribution.

  Overlay mechanism: a per-bundle stopped "carrier" container
  declares the runtime's `/nix` as a VOLUME (set in the image's config
  by `agentix build`); sandbox containers re-use it with
  `--volumes-from <carrier>:ro`. The carrier is created and started
  once with a harmless shell command so Podman copies the image's
  `/nix` data into the anonymous volume without trying to run
  `/nix/runtime/bootstrap.sh` from inside that same volume. One stopped
  carrier per distinct bundle — they cost only metadata.

  (`--mount type=image,subpath=nix` would let us skip the carrier
  entirely with one invocation, but it is not available across the
  Docker-compatible CLIs this backend supports. The carrier path works
  with both Docker and Podman.)

  Sandbox create:
      docker create [--platform <platform>] --name <carrier> <bundle>
      docker run [--platform <platform>] -d --name <sid> \\
         -p 127.0.0.1:<port>:<port> \\
         -e AGENTIX_BIND_PORT=<port> \\
         --volumes-from <carrier>:ro \\
         --entrypoint /nix/runtime/bootstrap.sh \\
         <image>

  The bundle's `/nix/runtime/bootstrap.sh` preps the runtime PATHs and
  launches the runtime server. We pick a free host port, publish the
  same port to loopback, pass it via `AGENTIX_BIND_PORT`, and
  health-check `/health` on it.

  The backend defaults to the `docker` CLI. Podman can be selected with
  `DockerDeploymentConfig(container_bin="podman", ...)` when it
  provides the Docker-compatible commands this backend needs.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shlex
import socket
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field, field_validator

from agentix.deployment.base import Deployment, Sandbox, SandboxConfig, SandboxId, SandboxInfo, SandboxResource
from agentix.runtime import BIND_HOST_ENV, BIND_PORT_ENV, BUNDLE_RUNTIME_ENTRYPOINT

logger = logging.getLogger("agentix.deployment.docker")


def _split_shell_args(value: str, label: str) -> list[str]:
    try:
        return shlex.split(value)
    except ValueError as exc:
        raise RuntimeError(f"{label} must contain shell-style arguments: {exc}") from exc


class DockerDeploymentConfig(BaseModel):
    """Docker-compatible CLI settings for the deployment backend."""

    container_bin: str = Field(
        default="docker",
        description="Docker-compatible CLI binary, e.g. `docker` or `podman`.",
    )
    create_args: list[str] = Field(
        default_factory=list,
        description="Extra arguments inserted after `container create` platform args.",
    )
    run_args: list[str] = Field(
        default_factory=list,
        description="Extra arguments inserted before sandbox networking and env args.",
    )
    network: str | None = Field(
        default=None,
        description="Optional container network mode, e.g. `host` or `slirp4netns`.",
    )
    publish_host: str = Field(
        default="127.0.0.1",
        description="Host address for `-p`; empty string emits `<port>:<port>`.",
    )
    gpu_args: list[str] | None = Field(
        default=None,
        description="Optional resource.gpu translation; args may contain `{gpu}`.",
    )

    @field_validator("container_bin")
    @classmethod
    def _validate_container_bin(cls, value: str) -> str:
        if not value:
            raise ValueError("container_bin must not be empty")
        return value

    @field_validator("create_args", "run_args", mode="before")
    @classmethod
    def _parse_extra_args(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return _split_shell_args(value, "deployment extra args")
        return value

    @field_validator("gpu_args", mode="before")
    @classmethod
    def _parse_gpu_args(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            return _split_shell_args(value, "deployment gpu_args")
        return value


def _default_config(config: DockerDeploymentConfig | None = None) -> DockerDeploymentConfig:
    return config or DockerDeploymentConfig()


def _container_bin(config: DockerDeploymentConfig | None = None) -> str:
    return _default_config(config).container_bin


def _port_mapping(port: int, config: DockerDeploymentConfig | None = None) -> str:
    host = _default_config(config).publish_host
    if not host:
        return f"{port}:{port}"
    return f"{host}:{port}:{port}"


def _network_args(config: DockerDeploymentConfig | None = None) -> list[str]:
    network = _default_config(config).network
    if not network:
        return []
    return ["--network", network]


def _network_uses_host_ports(config: DockerDeploymentConfig | None = None) -> bool:
    network = _default_config(config).network
    return network == "host" or bool(network and network.startswith("host:"))


def _publish_args(port: int, config: DockerDeploymentConfig | None = None) -> list[str]:
    if _network_uses_host_ports(config):
        return []
    return ["-p", _port_mapping(port, config)]


def _format_cpu(cpu: float) -> str:
    return str(int(cpu)) if cpu.is_integer() else str(cpu)


def _gpu_args(gpu: int, config: DockerDeploymentConfig | None = None) -> list[str]:
    template = _default_config(config).gpu_args
    if template is None:
        return ["--gpus", str(gpu)]
    return [arg.format(gpu=gpu) for arg in template]


def _resource_args(resource: SandboxResource | None, config: DockerDeploymentConfig | None = None) -> list[str]:
    if resource is None:
        return []
    args: list[str] = []
    if resource.cpu is not None:
        args.extend(["--cpus", _format_cpu(resource.cpu)])
    if resource.memory is not None:
        args.extend(["--memory", str(resource.memory)])
    if resource.gpu is not None:
        args.extend(_gpu_args(resource.gpu, config))
    return args


async def _docker(
    *args: str,
    config: DockerDeploymentConfig | None = None,
    check: bool = True,
    retries: int = 0,
) -> tuple[int, bytes, bytes]:
    attempt = 0
    delay = 2.0
    bin_name = _container_bin(config)
    while True:
        proc = await asyncio.create_subprocess_exec(
            bin_name,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        rc = proc.returncode or 0
        if not check or rc == 0:
            return rc, stdout, stderr
        if attempt >= retries or not _is_transient_docker_error(stderr):
            raise RuntimeError(f"{bin_name} {args[0]} failed: {stderr.decode(errors='replace')}")
        attempt += 1
        logger.warning(
            "%s %s failed with transient error; retrying in %.1fs (%d/%d)",
            bin_name,
            args[0],
            delay,
            attempt,
            retries,
        )
        await asyncio.sleep(delay)
        delay *= 2


def _is_transient_docker_error(stderr: bytes) -> bool:
    text = stderr.decode(errors="replace").lower()
    return any(
        needle in text
        for needle in (
            "failed to fetch oauth token",
            "unexpected status from post request",
            "tls handshake timeout",
            "connection reset by peer",
            "i/o timeout",
            "temporarily unavailable",
        )
    )


def _carrier_name(bundle: str, platform: str | None = None) -> str:
    """Stable name for the stopped container that holds a runtime's /nix volume."""
    key = f"{bundle}@{platform}" if platform else bundle
    slug = hashlib.sha1(key.encode()).hexdigest()[:12]
    return f"agentix-runtime-{slug}"


class DockerDeployment(Deployment):
    """Sandbox CRUD via local Docker."""

    def __init__(self, config: DockerDeploymentConfig | None = None):
        self.config = _default_config(config)
        self._ports: dict[SandboxId, int] = {}  # sandbox_id → host port

    @staticmethod
    def _allocate_port() -> int:
        # Ask the kernel for any free TCP port. There's still a small
        # TOCTOU window before the container binds, but no worse than a
        # linear probe and without the seed parameter.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    async def _ensure_carrier(self, bundle: str, platform: str | None) -> str:
        """Create (if missing) a stopped container exposing bundle's /nix.

        Stopped containers cost only metadata; one per distinct
        bundle/platform is enough regardless of how many sandboxes share it.
        """
        carrier = _carrier_name(bundle, platform)
        rc, _, _ = await _docker("inspect", carrier, config=self.config, check=False)
        if rc == 0:
            current_image = await _image_id(bundle, self.config)
            carrier_image = await _container_image_id(carrier, self.config)
            if current_image and carrier_image and current_image != carrier_image:
                await _docker("rm", "-f", carrier, config=self.config, check=False)
            else:
                return carrier
        platform_args = ["--platform", platform] if platform else []
        await _docker(
            "create",
            *platform_args,
            *self.config.create_args,
            *self.config.run_args,
            "--name",
            carrier,
            "--entrypoint",
            "/bin/sh",
            bundle,
            "-c",
            "true",
            config=self.config,
        )
        await _docker("start", "-a", carrier, config=self.config, check=False)
        return carrier

    async def create(self, config: SandboxConfig) -> Sandbox:
        sandbox_id = SandboxId(f"agentix-{uuid4().hex[:8]}")
        port = self._allocate_port()

        env_args: list[str] = ["-e", f"{BIND_PORT_ENV}={port}"]
        if _network_uses_host_ports(self.config) and not (config.env and BIND_HOST_ENV in config.env):
            env_args.extend(["-e", f"{BIND_HOST_ENV}=127.0.0.1"])
        if config.env:
            for k, v in config.env.items():
                env_args.extend(["-e", f"{k}={v}"])

        carrier = await self._ensure_carrier(config.bundle, config.platform)
        platform_args = ["--platform", config.platform] if config.platform else []
        resource_args = _resource_args(config.resource, self.config)
        await _docker(
            "run",
            *platform_args,
            *resource_args,
            *self.config.run_args,
            *_network_args(self.config),
            "-d",
            "--name",
            sandbox_id,
            *_publish_args(port, self.config),
            *env_args,
            "--volumes-from",
            f"{carrier}:ro",
            "--entrypoint",
            BUNDLE_RUNTIME_ENTRYPOINT,
            config.image,
            config=self.config,
            retries=3,
        )

        self._ports[sandbox_id] = port
        logger.info("Created sandbox %s on port %d", sandbox_id, port)

        await self._wait_healthy(port)
        return Sandbox(
            sandbox_id=sandbox_id,
            runtime_url=f"http://localhost:{port}",
            status="running",
        )

    async def _wait_healthy(self, port: int) -> None:
        base_url = f"http://localhost:{port}"
        async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
            for _ in range(120):
                try:
                    r = await client.get("/health")
                    if r.status_code == 200:
                        return
                except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError):
                    pass
                await asyncio.sleep(0.5)
        raise TimeoutError(f"Runtime server not alive at {base_url}")

    async def get(self, sandbox_id: SandboxId) -> SandboxInfo:
        port = self._ports.get(sandbox_id)
        if port is None:
            raise KeyError(f"Sandbox not found: {sandbox_id}")
        rc, stdout, _ = await _docker(
            "inspect",
            "-f",
            "{{.State.Status}}",
            sandbox_id,
            config=self.config,
            check=False,
        )
        status = stdout.decode().strip() if rc == 0 else "unknown"
        return SandboxInfo(
            sandbox_id=sandbox_id,
            runtime_url=f"http://localhost:{port}",
            status=status,
        )

    async def delete(self, sandbox_id: SandboxId) -> None:
        await _docker("rm", "-f", sandbox_id, config=self.config, check=False)
        self._ports.pop(sandbox_id, None)
        logger.info("Deleted sandbox %s", sandbox_id)


async def _image_id(image: str, config: DockerDeploymentConfig | None = None) -> str | None:
    rc, stdout, _ = await _docker("image", "inspect", "-f", "{{.Id}}", image, config=config, check=False)
    if rc != 0:
        return None
    return stdout.decode().strip() or None


async def _container_image_id(container: str, config: DockerDeploymentConfig | None = None) -> str | None:
    rc, stdout, _ = await _docker("inspect", "-f", "{{.Image}}", container, config=config, check=False)
    if rc != 0:
        return None
    return stdout.decode().strip() or None


__all__ = ["DockerDeployment", "DockerDeploymentConfig"]
