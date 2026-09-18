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
- [`phase-17.4-completion.md`](phase-17.4-completion.md) — Phase 17.4 football regulation-time BTTS provider equivalence and YES/NO enablement.
- [`phase-17.5-completion.md`](phase-17.5-completion.md) — Phase 17.5 football Draw No Bet / Asian Handicap 0 refund-aware evaluation.
- [`phase-17.6-completion.md`](phase-17.6-completion.md) — Phase 17.6 indexed tennis Set 1/Set 2 winner semantics with provider-narrowed support.
- [`phase-17.7-completion.md`](phase-17.7-completion.md) — Phase 17.7 nested tennis game identity and fail-closed score-state/provider feasibility gate.

## Current hand-off

Phases 0 through 16 and **Phases 17.1–17.7** are the completed technical baseline.
The next roadmap dependency is **Phase 17.8 — tennis set-winner cross-transport
completion**.

Phase 17.7 adds a canonical nested game identity: `set_index` identifies the
containing set and game `period_index` identifies the game inside that set.
`GAME_WINNER` remains runtime-disabled because neither current transport has yet
demonstrated a stable fixed Set N / Game M winner mapping. Labels, mutable score
strings, tiebreaks, and service-relative markets are not used to manufacture one.

Provider revalidation during Phase 17.7 also found that The Odds API's current
official market list now documents tennis `h2h_s1` and `h2h_s2` set moneylines.
The Phase 17.6 implementation remains OddsPapi-only; Phase 17.8 will add and validate
the The Odds API side and prove cross-transport same-set equivalence under ADR-0012.

The tennis retirement/walkover/incomplete-set limitation remains explicit, and
OddsPapi's production/legal blockers remain independent of technical market support.
See [`../providers/oddspapi.md`](../providers/oddspapi.md).
