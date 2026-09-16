# Development documentation

This directory contains the reproducible engineering setup plus formal completion records for implementation phases that own cross-cutting runtime/application concerns.

## Setup and engineering policy

- [`setup.md`](setup.md) — reproducible local setup and quality commands.
- [`dependency-policy.md`](dependency-policy.md) — third-party dependency and supply-chain policy.
- [`normalization.md`](normalization.md) — canonical normalization rules and supported semantics.

## Phase completion records

- [`phase-1-completion.md`](phase-1-completion.md) — Phase 1 repository bootstrap and engineering baseline.
- [`../domain/phase-2-completion.md`](../domain/phase-2-completion.md) — Phase 2 canonical domain model.
- [`../arbitrage/phase-3-completion.md`](../arbitrage/phase-3-completion.md) — Phase 3 arbitrage mathematics core.
- [`../providers/phase-4-completion.md`](../providers/phase-4-completion.md) — Phase 4 provider adapter contract.
- [`../architecture/phase-5-completion.md`](../architecture/phase-5-completion.md) — Phase 5 synthetic end-to-end vertical slice.
- [`phase-6-completion.md`](phase-6-completion.md) — Phase 6 first real odds-data integration.
- [`phase-7-completion.md`](phase-7-completion.md) — Phase 7 normalization engine.
- [`phase-8-completion.md`](phase-8-completion.md) — Phase 8 cross-provider event matching.
- [`phase-9-completion.md`](phase-9-completion.md) — Phase 9 market alignment and best-price construction.
- [`phase-10-completion.md`](phase-10-completion.md) — Phase 10 realtime ingestion and freshness control.
- [`phase-11-completion.md`](phase-11-completion.md) — Phase 11 persistence and auditability.
- [`phase-12-completion.md`](phase-12-completion.md) — Phase 12 opportunity lifecycle and execution realism.
- [`phase-13-completion.md`](phase-13-completion.md) — Phase 13 service/API boundary.
- [`phase-14-completion.md`](phase-14-completion.md) — Phase 14 observability and operational resilience.
- [`phase-15-completion.md`](phase-15-completion.md) — Phase 15 dashboard and alert boundary.

## Current hand-off

Phases 0 through 15 are the completed baseline. The next roadmap dependency is Phase 16 multi-provider expansion. Before implementation, read [`../providers/phase-16-readiness.md`](../providers/phase-16-readiness.md) and ADR-0012, which define the source-independence, overlap-provenance, and coexistence gates for adding another real odds source.
