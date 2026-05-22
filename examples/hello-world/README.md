# hello-world

The smallest possible Agentix bundle — the fixture for the
`agentix build` end-to-end test.

```sh
agentix build examples/hello-world
```

It declares the framework (`agentixx`) plus one sandbox-side plugin
(`agentix-runtime-basic`), so building it exercises the whole pipeline:
the Nix toolchain, a `uv sync`'d venv, and plugin/project system
closures merged into `/nix/runtime`.

The project also declares its own `default.nix`, which adds `ripgrep`
to `/nix/runtime/bin/rg`.
