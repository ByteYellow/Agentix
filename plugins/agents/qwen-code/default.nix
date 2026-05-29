# qwen-code (Qwen3-Coder CLI) pinned for the `agentix.agents.qwen_code` sandbox
# integration. `agentix build` discovers this file through the `agentix.nix`
# entry point and places `qwen` on `/nix/runtime/bin`.
#
# Lifted from numtide/llm-agents.nix (packages/qwen-code, v0.16.2) and adapted
# to plain nixpkgs: the Darwin-only build inputs and the network-touching
# versionCheckHook are dropped; the buildPhase/installPhase are kept as-is.
# `git` and `ripgrep` are joined into the runtime closure so the CLI can shell
# out to them inside the sandbox.

{ pkgs }:

let
  qwen = pkgs.buildNpmPackage (finalAttrs: {
    npmDepsFetcherVersion = 2;
    pname = "qwen-code";
    version = "0.16.2";

    src = pkgs.fetchFromGitHub {
      owner = "QwenLM";
      repo = "qwen-code";
      tag = "v${finalAttrs.version}";
      hash = "sha256-0JUwrIvuJV7m2Y2yemZfr9K3R6KX1fzrzTUTiBEArtQ=";
    };

    # npmDepsHash recomputed against Agentix's pinned nixpkgs (the upstream
    # llm-agents.nix value resolves to a different hash here).
    npmDepsHash = "sha256-Ep7/A+kbpTZHAHo30bXuPbHLcwDYb49v50B7D8ud1VA=";
    makeCacheWritable = true;

    nativeBuildInputs = [
      pkgs.pkg-config
      pkgs.git
    ];
    buildInputs = [
      pkgs.ripgrep
      pkgs.glib
      pkgs.libsecret
    ];

    buildPhase = ''
      runHook preBuild

      npm run generate
      for ws in \
        packages/web-templates \
        packages/channels/base \
        packages/channels/telegram \
        packages/channels/weixin \
        packages/channels/dingtalk
      do
        npm run build --workspace=$ws
      done
      npm run bundle

      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall

      mkdir -p $out/bin $out/share/qwen-code
      cp -r dist/* $out/share/qwen-code/
      npm prune --production
      cp -r node_modules $out/share/qwen-code/
      find $out/share/qwen-code/node_modules -type l -delete || true
      patchShebangs $out/share/qwen-code
      ln -s $out/share/qwen-code/cli.js $out/bin/qwen

      runHook postInstall
    '';

    meta = {
      description = "qwen-code — command-line AI workflow tool for Qwen3-Coder models";
      homepage = "https://github.com/QwenLM/qwen-code";
      license = pkgs.lib.licenses.asl20;
      mainProgram = "qwen";
      platforms = [ "x86_64-linux" "aarch64-linux" ];
    };
  });
in
pkgs.symlinkJoin {
  name = "agentix-agent-qwen-code-sys";
  paths = [
    qwen
    pkgs.git
    pkgs.ripgrep
  ];
}
