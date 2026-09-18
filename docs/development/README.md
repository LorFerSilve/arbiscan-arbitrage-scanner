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
- [`phase-16.2-completion.md`](phase-16.2-completion.md) — Phase 16.2 multi-source provenance hardening.
- [`phase-16.3-completion.md`](phase-16.3-completion.md) — Phase 16.3 OddsPapi second provider adapter.
- [`phase-16.4-completion.md`](phase-16.4-completion.md) — Phase 16.4 reusable fixtures and provider conformance.
- [`phase-16.5-completion.md`](phase-16.5-completion.md) — Phase 16.5 normalization and event-matching validation across both real adapter schemas.
- [`phase-16.6-completion.md`](phase-16.6-completion.md) — Phase 16.6 real multi-source coexistence regressions.
- [`phase-16.7-completion.md`](phase-16.7-completion.md) — Phase 16.7 observability and operational tuning for the second real source.
- [`phase-16.8-completion.md`](phase-16.8-completion.md) — Phase 16.8 staged enablement and formal Phase 16 technical closure.
- [`phase-17.1-completion.md`](phase-17.1-completion.md) — Phase 17.1 structured advanced-market semantic foundation.
- [`phase-17.2-completion.md`](phase-17.2-completion.md) — Phase 17.2 football pre-match regulation totals on push-free half-goal lines.
- [`phase-17.3-completion.md`](phase-17.3-completion.md) — Phase 17.3 football Asian handicap identity, settlement semantics, and half-goal enablement.

## Current hand-off

Phases 0 through 16 and **Phases 17.1–17.3** are the completed technical baseline.
The next roadmap dependency is **Phase 17.4 — football both-teams-to-score semantics
and provider feasibility**.

Before Phase 17.4 implementation, verify the provider API surfaces rather than
assuming that a shared YES/NO label implies equivalent settlement scope. The phase
must prove regulation-time identity, exact YES/NO completeness, source mappings for
each real transport, and end-to-end same-market comparison.

Phase 17.3 deliberately does not enable integer or quarter Asian handicap lines in
generic arbitrage/staking. Their settlement states are represented, but enabling them
requires a future scenario-aware guaranteed-return and stake-allocation model.

Phase 16 technical completion still does not override unresolved provider-specific
production/legal blockers. OddsPapi remains production-blocked as documented in
[`../providers/oddspapi.md`](../providers/oddspapi.md).
