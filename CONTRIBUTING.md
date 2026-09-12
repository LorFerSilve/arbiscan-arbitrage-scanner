# Contributing to ArbiScan

ArbiScan uses a protected pull-request workflow. Direct changes to `main` are not part of the normal development process.

## Development workflow

1. Create a focused branch from the current `main`.
2. Make one logically coherent change.
3. Run `uv sync --locked`.
4. Run `uv run python scripts/quality.py --all`.
5. Open a pull request against `main`.
6. Resolve all review conversations and required CI failures.
7. Squash-merge after the repository rules allow the merge.

## Commit and PR scope

Prefer small, reviewable changes. Do not mix unrelated refactors, dependency changes, provider integrations, and feature work in one pull request.

## Architecture boundaries

Provider-specific behavior must stay behind provider adapters. Core domain, matching, normalization, and arbitrage logic must depend on canonical types rather than provider payloads.

Any durable architecture decision that changes a previously accepted constraint should be recorded in `docs/adr/`.

## Quality baseline

The canonical quality entry point is:

```text
uv run python scripts/quality.py --all
```

CI invokes the same command. The fast pre-commit hook omits only the vulnerability audit.

## Secrets

Never commit API keys, access tokens, passwords, private keys, cookies, session data, or real `.env` files. Add only variable names and safe examples to `.env.example`.
