# agentix-deployment-docker

Docker deployment backend for [Agentix](https://github.com/Agentiix/Agentix).

Provisions a sandbox by running an Agentix bundle image in a local
Docker daemon, returns the runtime URL the orchestrator's
`RuntimeClient` connects to.

The backend shells out to a Docker-compatible CLI. It uses `docker` by
default, and can target Podman through `DockerDeploymentConfig`.

## Install

```bash
pip install agentix-deployment-docker
```

## Use

```python
from agentix import RuntimeClient, SandboxConfig, session
from agentix.deployment.docker import DockerDeployment, DockerDeploymentConfig

deployment = DockerDeployment(
    DockerDeploymentConfig(
        container_bin="podman",
        run_args=["--runtime=crun", "--cgroups=disabled"],
        network="host",
        gpu_args=["--device", "nvidia.com/gpu=all"],
    )
)

async with session(
    deployment,
    SandboxConfig(
        image="python:3.13-slim",
        bundle="my-agent:0.1.0",
        resource={"cpu": 4, "memory": "16g", "gpu": 1},
    )
) as sandbox:
    async with RuntimeClient(sandbox.runtime_url) as c:
        ...
```

`network="host"` skips port publishing and relies on the runtime binding
directly in the host network namespace. In that mode the backend sets
`AGENTIX_BIND_HOST=127.0.0.1` unless the caller overrides it in
`SandboxConfig.env`.

The `local` name comes from the entry point this wheel declares under
`agentix.deployment` — once installed, the framework discovers it
automatically. No core-framework changes are required to register a new
backend; the same pattern works for `agentix-deployment-daytona`,
`agentix-deployment-e2b`, or any third-party backend.

## License

MIT — see [LICENSE](LICENSE).
