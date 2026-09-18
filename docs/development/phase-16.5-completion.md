# Phase 16.5 completion — normalization and event-matching validation

Date: 2026-09-18

## Scope

Phase 16.5 validates the currently supported MVP normalization and event-matching
semantics across ArbiScan's two real transport adapter schemas: The Odds API and
OddsPapi. The work remains fixture-driven and credential-free.

This phase does not yet claim that both real transports safely coexist through every
runtime failure, overlap, conflict, and persistence path. Those regressions are the
explicit responsibility of Phase 16.6.

## Completed validation

1. Added a shared football fixture scenario for Liverpool versus Manchester United
   across both real adapter schemas, with distinct source event identifiers.
2. Added explicit provider-scoped competition and participant normalization for that
   scenario and verified both sources resolve to one canonical Premier League event.
3. Validated ordered football participant semantics:
   - normal home/away order matches;
   - reversed source participant order is rejected with
     `PARTICIPANT_ORDER_MISMATCH` rather than guessed.
4. Validated provider-referenced start-time/reschedule handling with a deliberate
   five-minute The Odds API source-time shift:
   - a verified Phase-8 `EventMatcher` decision permits strict normalization;
   - a bare static event-ID mapping fails closed with `IDENTITY_MISMATCH`.
5. Validated football regulation 1X2 semantics across the two source shapes:
   - The Odds API `Pinnacle h2h`;
   - OddsPapi `pinnacle Full Time Result`;
   - both normalize to one canonical `MATCH_WINNER_3_WAY` market and the same home,
     draw, and away selections.
6. Added a second shared tennis fixture scenario for Jannik Sinner versus Carlos
   Alcaraz and deliberately reversed the provider participant order between sources.
7. Validated tennis participant identity as `UNORDERED`, so the two provider orders
   resolve to one canonical event without weakening the ordered football invariant.
8. Validated tennis two-way match-winner semantics:
   - The Odds API `Pinnacle h2h`;
   - OddsPapi `pinnacle Match Winner`;
   - both normalize to one canonical `MATCH_WINNER_2_WAY` / `FULL_EVENT` market and
     the same two participant selections.
9. Verified source timestamps drive quote freshness and stale observations are
   rejected before quote eligibility.
10. Verified unknown selection mappings and unknown market status semantics remain
    fail-closed instead of entering the canonical quote set.
11. Verified overlapping Pinnacle observations preserve the shared executable
    price-provider identity while retaining distinct transport-provider provenance and
    non-colliding quote identifiers.
12. Generalized the deterministic The Odds API fixture transport so provider-specific
    football and tennis event/odds fixtures can share the same test harness without
    external I/O.

## Fail-closed invariants exercised

The Phase 16.5 suite explicitly covers the following rejection boundaries:

- participant-order mismatch for ordered football events;
- unverified event reschedule identity;
- unmapped selection semantics;
- unknown/inactive market status semantics;
- stale source observations.

The matching and normalization layers therefore continue to require explicit semantic
agreement rather than fuzzy or provider-specific guessing.

## Quality evidence

The code-bearing Phase 16.5 head `885e20604663cb6bfaf0c452f9ebcd5243212c54`
passed the repository's normal CI quality gate:

- Ruff formatting: pass (`189 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`130 source files`);
- pytest: pass (`218 passed`), including six Phase 16.5 integration tests;
- `pip-audit`: no known vulnerabilities found.

The final pull-request head must retain the same repository quality gate after this
completion record and hand-off update are added.

## Handoff

Phase 16.5 is complete. The next roadmap dependency is **Phase 16.6 — real
multi-source coexistence regressions**.

Phase 16.6 should exercise the actual multi-source runtime/consolidation boundaries,
including:

- two real adapter schemas contributing safely to one canonical market book;
- source outage/rate-limit isolation;
- stale-versus-fresh source precedence;
- overlapping bookmaker observations without double counting;
- equal-time conflicting observations failing closed with diagnostics;
- equivalent equal-time observations consolidating deterministically while retaining
  transport provenance;
- unmatched or ambiguous cross-source events remaining isolated;
- independent suspended/closed-source invalidation;
- price-origin inclusion/exclusion policy behavior;
- persisted opportunity evidence retaining both price origin and transport provenance.

Those tests should remain deterministic and fixture-driven in ordinary CI. Phase 16.6
must not require live provider availability or credentials for pull-request validation.
