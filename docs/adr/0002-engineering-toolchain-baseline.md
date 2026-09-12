# ADR-0002: Engineering toolchain baseline

- Status: Accepted
- Date: 2026-09-13

## Context

ArbiScan needs a reproducible, low-friction Python workflow before domain code is introduced. The project also needs local and CI quality gates to behave consistently and third-party automation to be supply-chain conscious.

## Decision

Use CPython 3.13 as the initial language baseline, pinned to 3.13.15 for the bootstrap. Use uv 0.12.12 for environment and dependency management, `pyproject.toml` as the configuration source, and commit `uv.lock`.

Use Ruff for formatting/linting, mypy in strict mode for static typing, pytest for tests, pre-commit for local hooks, and pip-audit for vulnerability checks. The canonical quality orchestration lives in `scripts/quality.py` so CI and local execution share one implementation.

GitHub Actions must declare least-privilege permissions and third-party actions must be pinned to immutable commit SHAs. Dependabot monitors supported dependency ecosystems.

## Consequences

The project accepts a small amount of bootstrap configuration and version maintenance in exchange for deterministic tooling, reviewable upgrades, and lower environment drift. Python 3.14 features are intentionally unavailable until a later ADR changes the supported baseline.
