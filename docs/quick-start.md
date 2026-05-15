# Quick start

## Install the framework

```bash
pip install agentix
```

You'll also want at least one namespace; for the bundled primitives:

```bash
pip install agentix-bash agentix-files
```

Confirm the install:

```bash
$ agentix plugins
agentix.namespace
  bash    → agentix.bash:Bash    [agentix-bash@0.1.0] ok
  files   → agentix.files:Files  [agentix-files@0.1.0] ok

agentix.deployment
  local   → agentix.deployment.docker:DockerDeployment    [agentix@…] ok
  daytona → …
  e2b     → …
…
```

## Call a namespace from your code

```python
import asyncio
from agentix import RuntimeClient, SandboxConfig
from agentix.deployment.base import session
from agentix.deployment.docker import DockerDeployment
from agentix.bash import Bash

async def main():
    deployment = DockerDeployment()
    config = SandboxConfig(
        image="ubuntu:24.04",
        runtime="agentix/runtime:latest",
        closures=["agentix/bash:0.1.0"],   # one closure image, pre-built
    )
    async with session(deployment, config) as sandbox:
        async with RuntimeClient(sandbox.runtime_url) as c:
            result = await c.remote(Bash.run, command="echo hi")
            print(result.stdout)   # → "hi\n"

asyncio.run(main())
```

A few things happening here:

* `DockerDeployment` is the built-in `agentix.deployment` plugin named `local`. You can also look it up dynamically: `load_deployment("local")`.
* `session(deployment, config)` is a free function (not a method) that creates a sandbox on entry and tears it down on exit.
* `c.remote(Bash.run, …)` reads `Bash.run.__module__` (= `"agentix.bash"`) as the routing key. The framework dispatches over `POST /_remote` (HTTP) or `/socket.io/` (for streams) depending on the method's signature.

## Write your own namespace

Three files. The Python project itself is whatever `uv init --lib` produces.

```python
# src/agentix/myagent/__init__.py
from agentix.namespace import Namespace

class MyAgent(Namespace):
    """Optional class docstring — surfaces in /namespaces output."""

    @staticmethod
    async def run(instruction: str) -> str:
        # the real implementation — runs inside the sandbox
        return f"did: {instruction}"
```

```toml
# pyproject.toml
[project]
name = "agentix-myagent"
version = "0.1.0"

[project.entry-points."agentix.namespace"]
myagent = "agentix.myagent:MyAgent"

[tool.hatch.build.targets.wheel]
packages = ["src/agentix"]
```

Build the image, push it, deploy:

```bash
agentix build ./my-namespace          # builds agentix/myagent:0.1.0
agentix install bash myagent -o my-bundle:0.1.0
agentix deploy local --image my-bundle:0.1.0
```

`pip install agentix-myagent` is all your users need to do — the framework discovers the entry point and `from agentix.myagent import MyAgent` resolves natively.

## Next

* [Writing other plugin types](plugins.md) — deployments, trace sinks, spec resolvers, wire patterns, CLI subcommands all share the same entry-point pattern.
* [Architecture](architecture.md) — how the dispatcher / runtime / wire patterns fit together.
* [CLI reference](cli.md) — every `agentix <subcommand>` documented.
