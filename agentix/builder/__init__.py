"""agentix.builder — in-container bundle builder assets.

`agentix build` runs `bundle-build.sh` inside a Docker container that
materializes a Nix toolchain, syncs the project's uv dependencies, and
stages every plugin Nix closure into a runtime image. The shell script,
the `Dockerfile` that wraps it, and the pinned `flake.nix` / `flake.lock`
that drive it all ship as wheel data under this package.

The host side (`agentix.cli.build`) loads them via `importlib.resources`,
so renaming the directory is transparent to plugins.
"""

__all__: list[str] = []
