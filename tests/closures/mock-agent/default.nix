{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python312;
  pythonPkgs = python.pkgs;
in
pythonPkgs.buildPythonApplication {
  pname = "mock-agent";
  version = "0.1.0";
  format = "pyproject";

  src = ./.;

  nativeBuildInputs = [ pythonPkgs.hatchling ];

  propagatedBuildInputs = [
    pythonPkgs.fastapi
    pythonPkgs.uvicorn
  ];

  doCheck = false;

  # Agentix closure manifest — runtime reads this from
  # /mnt/<ns>/entry/manifest.json to identify the mount as a closure.
  postInstall = ''
    cat > $out/manifest.json <<'JSON'
    {"abi":1,"name":"mock-agent","version":"0.1.0","kind":"agent","description":"Mock agent: returns the instruction as a fake patch.","endpoints":[{"method":"POST","path":"/run","description":"Run against an instruction. Body: {instruction, workdir?}"}]}
    JSON
  '';

  meta.description = "Mock agent closure used in Agentix tests";
}
