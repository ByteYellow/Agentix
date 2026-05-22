{ pkgs }:

pkgs.symlinkJoin {
  name = "hello-world-sys";
  paths = [ pkgs.ripgrep ];
}
