# ArbiScan Arbitrage Scanner

ArbiScan is a multi-bookmaker sports-odds aggregation and arbitrage-detection engine. The product boundary is intentionally scanner-only: it identifies and reports semantically valid opportunities but does not place bets automatically.

## Current status

Phases 0 through 15 of [`roadmap.md`](roadmap.md) are implemented. **Phase 16.1 — provider candidate review and selection — and Phase 16.2 — multi-source provenance hardening — are complete.** OddsPapi is the selected development target for the second real transport source, while production enablement remains blocked pending explicit data-rights clarification and the remaining Phase 16 correctness gates.

The next implementation dependency is **Phase 16.3 — second provider adapter**. The adapter must use the Phase-16.2 source-aware quote model and explicitly map overlapping bookmaker identities into the canonical price-provider namespace before mixed-source market books can be enabled.

The implemented core now includes:

- provider-neutral canonical event/market/selection/quote models;
- separate transport-source and bookmaker/exchange price-provider provenance;
- deterministic multi-source overlap consolidation with fail-closed conflict handling;
- deterministic Decimal-based arbitrage mathematics and stake allocation;
- a strict async provider-adapter contract plus synthetic providers;
- one real odds-data integration through The Odds API;
- semantic normalization and cross-provider event matching;
- canonical best-price market books;
- realtime ingestion, freshness/stale control, rate-limit handling, and provider isolation;
- persistence/audit evidence and opportunity reconstruction;
- opportunity lifecycle/actionability revalidation;
- transport-neutral service/API contracts;
- system/provider observability;
- read-only dashboard projection and alert deduplication.

The project is still versioned as development software and is **not** being productized into a packaged local launcher yet. That is deliberate: provider coverage and correctness work take priority over packaging/deployment.

See [`docs/providers/phase-16-readiness.md`](docs/providers/phase-16-readiness.md) for the Phase 16 implementation sequence, [`docs/providers/phase-16.1-provider-selection.md`](docs/providers/phase-16.1-provider-selection.md) for the provider decision, and [`docs/development/phase-16.2-completion.md`](docs/development/phase-16.2-completion.md) for the multi-source provenance architecture and validation evidence.

## Current market scope

Initial supported semantics remain intentionally narrow:

1. football pre-match 1X2 match winner;
2. tennis pre-match two-way match winner.

Advanced totals, handicaps/spreads, set markets, outrights, motorsport/F1 market expansion, and broader market semantics remain later roadmap work.

## Development

The project uses Python 3.13, uv, Ruff, mypy, pytest, pre-commit, and GitHub Actions. See [`docs/development/setup.md`](docs/development/setup.md) for the reproducible setup and quality commands.

The full local/CI quality gate is:

```text
uv run python scripts/quality.py --all
```

CI uses deterministic fixtures and does not require live provider credentials.

## Documentation

- Development status and phase completion records: [`docs/development/`](docs/development/)
- Product requirements: [`docs/product/requirements.md`](docs/product/requirements.md)
- Non-goals: [`docs/product/non-goals.md`](docs/product/non-goals.md)
- Risk register: [`docs/product/risk-register.md`](docs/product/risk-register.md)
- Provider integration checklist: [`docs/product/provider-integration-checklist.md`](docs/product/provider-integration-checklist.md)
- The Odds API integration: [`docs/providers/the-odds-api.md`](docs/providers/the-odds-api.md)
- Phase 16 readiness: [`docs/providers/phase-16-readiness.md`](docs/providers/phase-16-readiness.md)
- Phase 16.1 provider selection: [`docs/providers/phase-16.1-provider-selection.md`](docs/providers/phase-16.1-provider-selection.md)
- Phase 16.2 completion: [`docs/development/phase-16.2-completion.md`](docs/development/phase-16.2-completion.md)
- OddsPapi onboarding record: [`docs/providers/oddspapi.md`](docs/providers/oddspapi.md)
- Dashboard/alert boundary: [`docs/product/dashboard-and-alerts.md`](docs/product/dashboard-and-alerts.md)
- Architecture decisions: [`docs/adr/`](docs/adr/)
- Development roadmap: [`roadmap.md`](roadmap.md)
