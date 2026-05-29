"""Tests for `agentix deploy`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentix.provider.docker import DockerProviderConfig

import agentix.cli.deploy as deploy_mod
from agentix.provider.base import MaterializedBundle


class _Resolver:
    """Stand-in for `providers()` — `.get(name)` returns the resolved class."""

    def __init__(self, fn, names: tuple[str, ...] = ()) -> None:
        self._fn = fn
        self._names = names

    def get(self, name: str):
        return self._fn(name)

    def all(self) -> dict[str, object]:
        return dict.fromkeys(self._names, object())


class FakeMaterializer:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, str | None, str | None]] = []

    async def materialize_bundle(
        self,
        bundle: Path,
        *,
        name: str | None = None,
        platform: str | None = None,
    ) -> MaterializedBundle:
        self.calls.append((bundle, name, platform))
        return MaterializedBundle(
            bundle=name or "demo:1.0.0",
            platform=platform,
            metadata={"cache": "/tmp/agentix-runtime-pytest"},
        )


def test_deploy_unknown_backend_reports_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle.tar"
    bundle.write_text("placeholder")

    def _raise(name: str):
        raise KeyError(f"no plugin {name!r}")

    monkeypatch.setattr(
        deploy_mod,
        "providers",
        lambda: _Resolver(_raise, names=("docker", "podman")),
    )

    with pytest.raises(SystemExit, match="unknown deploy backend 'bogus'; available: docker, podman"):
        deploy_mod.main(["bogus", str(bundle)])


def test_deploy_broken_backend_reports_load_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle.tar"
    bundle.write_text("placeholder")

    def _broken(name: str):
        # Registered name whose plugin fails to load — the registry re-raises
        # the original (non-KeyError) exception.
        raise RuntimeError("plugin import boom")

    monkeypatch.setattr(deploy_mod, "providers", lambda: _Resolver(_broken, names=("docker",)))

    with pytest.raises(SystemExit, match="deploy backend 'docker' failed to load: plugin import boom"):
        deploy_mod.main(["docker", str(bundle)])


def test_deploy_invokes_materializer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    instance = FakeMaterializer()
    bundle = tmp_path / "bundle.tar"
    bundle.write_text("placeholder")

    monkeypatch.setattr(deploy_mod, "providers", lambda: _Resolver(lambda name: lambda: instance))

    assert deploy_mod.main(["fake", str(bundle), "--name", "demo:dev", "--platform", "linux/amd64"]) == 0

    assert instance.calls == [(bundle, "demo:dev", "linux/amd64")]
    output = capsys.readouterr().out
    assert "bundle -> demo:dev" in output
    assert "platform -> linux/amd64" in output
    assert "cache -> /tmp/agentix-runtime-pytest" in output


def test_deploy_passes_docker_compatible_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configs: list[DockerProviderConfig] = []
    bundle = tmp_path / "bundle.tar"
    bundle.write_text("placeholder")

    class FakeDockerProvider(FakeMaterializer):
        def __init__(self, config: DockerProviderConfig) -> None:
            super().__init__()
            configs.append(config)

    monkeypatch.setattr(deploy_mod, "providers", lambda: _Resolver(lambda name: FakeDockerProvider))

    assert deploy_mod.main(["podman", str(bundle), "--run-arg", "--runtime=crun"]) == 0

    assert configs == [
        DockerProviderConfig(
            container_bin="podman",
            run_args=["--runtime=crun"],
        )
    ]


def test_deploy_rejects_backend_without_materializer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeProvider:
        pass

    bundle = tmp_path / "bundle.tar"
    bundle.write_text("placeholder")
    monkeypatch.setattr(deploy_mod, "providers", lambda: _Resolver(lambda name: FakeProvider))

    with pytest.raises(SystemExit, match="cannot materialize"):
        deploy_mod.main(["fake", str(bundle)])


def test_deploy_format_json_emits_machine_readable_ref(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    instance = FakeMaterializer()
    bundle = tmp_path / "bundle.tar"
    bundle.write_text("placeholder")

    monkeypatch.setattr(deploy_mod, "providers", lambda: _Resolver(lambda name: lambda: instance))

    assert (
        deploy_mod.main(
            ["fake", str(bundle), "--name", "demo:dev", "--platform", "linux/amd64", "--format", "json"]
        )
        == 0
    )

    data = json.loads(capsys.readouterr().out)
    assert data["bundle"] == "demo:dev"
    assert data["platform"] == "linux/amd64"
    assert data["metadata"]["cache"] == "/tmp/agentix-runtime-pytest"
