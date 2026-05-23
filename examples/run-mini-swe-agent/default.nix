{ pkgs }:
pkgs.symlinkJoin {
  name = "run-mini-swe-agent-sys";
  paths = [
    pkgs.stdenv.cc.cc.lib
  ];
}
