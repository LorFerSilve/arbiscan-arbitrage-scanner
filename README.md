# ArbiScan Arbitrage Scanner

ArbiScan is a multi-bookmaker sports-odds aggregation and arbitrage-detection engine. The initial product is a scanner: it identifies and reports semantically valid opportunities but does not place bets automatically.

## Current scope

Development follows [`roadmap.md`](roadmap.md). Phase 0 defines product scope and invariants; Phase 1 establishes the engineering baseline before canonical domain implementation begins.

Initial market priority:

1. football pre-match 1X2 match winner;
2. tennis pre-match two-way match winner.

## Development

The project uses Python 3.13, uv, Ruff, mypy, pytest, pre-commit, and GitHub Actions. See [`docs/development/setup.md`](docs/development/setup.md) for the reproducible setup and quality commands.

## Documentation

- Product requirements: [`docs/product/requirements.md`](docs/product/requirements.md)
- Non-goals: [`docs/product/non-goals.md`](docs/product/non-goals.md)
- Risk register: [`docs/product/risk-register.md`](docs/product/risk-register.md)
- Architecture decisions: [`docs/adr/`](docs/adr/)
- Development roadmap: [`roadmap.md`](roadmap.md)
