{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python312;
  pythonPkgs = python.pkgs;
in
pythonPkgs.buildPythonApplication {
  pname = "mock-dataset";
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
    {"abi":1,"name":"mock-dataset","version":"0.1.0","kind":"dataset","description":"Mock dataset: setup returns an instruction, verify always passes.","endpoints":[{"method":"POST","path":"/setup","description":"Return an agent_input for the given instance."},{"method":"POST","path":"/verify","description":"Return {pass: true, reason: ...}."}]}
    JSON
  '';

  meta.description = "Mock dataset closure used in Agentix tests";
}
