# System binaries for the hello-world bundle.
#
# `agentix build` reads this via `[tool.agentix].nix` and symlinks the
# resulting `bin/*` into `/nix/runtime/bin/` inside the bundle image.

{ pkgs }:

pkgs.symlinkJoin {
  name = "hello-world-sys";
  paths = [ pkgs.ripgrep ];
}
