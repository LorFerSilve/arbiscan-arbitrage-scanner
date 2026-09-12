# Third-party dependency policy

A dependency is a design and supply-chain decision, not a convenience import.

Before adding a runtime or development dependency, evaluate:

- whether the standard library or an existing dependency already solves the problem;
- project maintenance activity and release history;
- security advisories and unresolved critical issues;
- package provenance and publisher controls;
- transitive dependency footprint;
- license and redistribution compatibility;
- Python-version/platform support;
- API stability and migration cost;
- whether the dependency handles secrets, network traffic, parsing, cryptography, or untrusted input.

## Version management

- Runtime dependencies belong in `pyproject.toml` and are resolved into `uv.lock`.
- `uv.lock` is committed and CI uses locked synchronization.
- One-shot engineering tools are invoked with exact versions in `scripts/quality.py` until there is a reason to move them into the project environment.
- GitHub Actions are pinned to immutable commit SHAs with human-readable version comments.
- Dependabot monitors uv and GitHub Actions weekly.

## Update policy

Dependency updates must pass the complete CI suite. Major-version updates require review of release notes and breaking changes rather than blind automated merging.
