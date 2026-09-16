# Development setup

## Toolchain

The engineering baseline is pinned to:

- CPython 3.13.15;
- uv 0.12.12;
- Ruff 0.16.7;
- mypy 2.3.1;
- pytest 9.1.1;
- pre-commit 4.6.2;
- pip-audit 2.10.1.

Python 3.13 is intentionally retained for the current implementation even though newer Python versions may exist. Changing the minor version should be a deliberate engineering decision validated against the full repository quality gate rather than an incidental local upgrade.

## First-time setup

Install uv using Astral's official installation instructions. Then, from the repository root:

```text
uv python install 3.13.15
uv sync --locked
uvx --from pre-commit==4.6.2 pre-commit install --install-hooks
```

`uv` validates its required version from `pyproject.toml`. If a different uv version is installed, use uv's official installation or upgrade mechanism to install 0.12.12.

## Quality gates

Run the complete local gate before opening or updating a pull request:

```text
uv run python scripts/quality.py --all
```

The command performs:

1. lock-file consistency check;
2. Ruff formatting check;
3. Ruff linting;
4. strict mypy type checking;
5. pytest test execution;
6. dependency vulnerability audit.

For a faster pass without the vulnerability audit:

```text
uv run python scripts/quality.py --fast
```

The GitHub Actions CI workflow runs the full gate using the same script and pinned tool versions.

## Environment configuration

Copy `.env.example` to `.env` only when local runtime configuration is needed. Never put real credentials in `.env.example` and never commit `.env`.

Provider-specific variables must not be added until that provider has passed `docs/product/provider-integration-checklist.md`.

The current real-provider integration uses `THE_ODDS_API_KEY`. CI and deterministic fixture tests do not require a live value.

## Source layout

The repository uses a `src/` layout with separate package boundaries for the canonical domain, providers, ingestion, normalization, matching, market-book construction, arbitrage, lifecycle/actionability, persistence, services/API, observability, and dashboard presentation.

Phases 0 through 15 are implemented. The next roadmap dependency is Phase 16 multi-provider expansion; see `docs/providers/phase-16-readiness.md` before adding another real source. Packaging the project as an end-user launcher is intentionally not part of the current setup baseline.
