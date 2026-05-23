# hello-world

Minimal Agentix example with one Python file and one Nix dependency.

`main.py` defines `hello()`, which runs `rg --version`. The same function
is called once on the host and once inside an Agentix sandbox. The sandbox
gets `rg` from `default.nix`, which `agentix build` merges into
`/nix/runtime/bin`.

## Run (local Docker)

```bash
uv sync
uv run agentix build . --format oci-image
uv run main.py                          # defaults to --deployment local
```

`main.py` accepts `--deployment`, `--image`, and `--bundle`. By default
it loads the Docker backend (`local`) and runs the same bundle name
that `agentix build` produced.

## Run on an HPC host (apptainer)

Build a portable tar bundle and run with the apptainer backend:

```bash
uv run agentix build . --format tar --output /path/to/hello-world.tar
uv run main.py \
    --deployment apptainer \
    --bundle /path/to/hello-world.tar \
    --image docker://python:3.13-slim
```

The backend pulls the task image with `apptainer pull` on first use and
caches it under `$AGENTIX_APPTAINER_CACHE` (default
`~/.cache/agentix/apptainer/`).

## Flow

1. `uv sync` installs this example plus the local Agentix packages from
   `[tool.uv.sources]`.
2. `uv run agentix build . --format <oci-image|tar>` builds the runtime
   bundle (Docker image or portable tar). The build installs `main.py`
   into the bundle and applies `default.nix`, so `rg` is available in
   the sandbox runtime.
3. `uv run main.py [--deployment ...]` starts a sandbox with the
   selected backend, then prints the host result and sandbox result.
