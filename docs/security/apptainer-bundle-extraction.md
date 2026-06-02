# Apptainer bundle extraction hardening

## Summary

The Apptainer provider extracts the `nix/` tree from an Agentix bundle tar
before bind-mounting it into the sandbox. This extraction path now uses the same
safe extraction model as the Docker provider instead of calling
`tar.extract(...)` directly.

## Risk addressed

Bundle tar member names are untrusted input. A member that appears to live under
`nix/` can still normalize to a path outside the extraction root if the extractor
does not validate it before writing to disk.

The hardened extraction path rejects:

- absolute paths
- empty or current-directory-only paths
- parent traversal through `..`
- members outside the `nix/` tree
- hard links whose targets are outside the checked `nix/` tree
- unsupported tar member types

## Implementation

The Apptainer provider now:

1. normalizes every tar member name with POSIX path semantics
2. validates that the normalized member is exactly `nix` or starts with `nix/`
3. creates parent directories manually while rejecting unsafe existing parents
4. copies file contents manually instead of delegating to `tar.extract(...)`
5. extracts into a temporary directory and replaces the cache only after the
   whole bundle tree validates successfully

This keeps the cached bundle from being partially populated if extraction fails
partway through.

## Validation

The regression test builds a bundle tar containing a valid runtime tree followed
by an unsafe member. The provider must raise an error, avoid writing outside the
cache directory, and avoid leaving a partially extracted runtime tree behind.

Targeted tests:

```powershell
python -m pytest -o addopts= `
  plugins\providers\apptainer\tests\test_apptainer_provider.py::test_bundle_digest_uses_manifest_when_present `
  plugins\providers\apptainer\tests\test_apptainer_provider.py::test_bundle_digest_falls_back_to_file_hash `
  plugins\providers\apptainer\tests\test_apptainer_provider.py::test_extract_bundle_skips_when_runtime_already_present `
  plugins\providers\apptainer\tests\test_apptainer_provider.py::test_extract_bundle_rejects_path_traversal_member
```

## Compatibility

Valid Agentix bundles with a normal top-level `nix/` tree continue to extract as
before. Bundles containing unsafe paths, unsafe hard links, or unsupported member
types now fail early with a `RuntimeError`.
