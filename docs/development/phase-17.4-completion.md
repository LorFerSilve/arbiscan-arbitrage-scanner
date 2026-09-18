# Phase 17.4 completion — football both-teams-to-score semantics and provider feasibility

Date: 2026-09-18

## Scope

Phase 17.4 evaluates and enables football pre-match regulation-time
both-teams-to-score (BTTS) across both real transport schemas.

Unlike totals and Asian handicap, BTTS needs no new payout algebra. The main
correctness problem is proving that provider-specific market identity refers to the
same full-match settlement scope and exact YES/NO outcome set.

## Provider feasibility result

Both existing real provider integrations expose a compatible BTTS market through the
API surfaces already used by ArbiScan.

### The Odds API

The documented soccer additional-market key is `btts`, with Yes/No outcomes,
available through the event-odds endpoint already used by the adapter.

The provider also documents period-specific variants such as `btts_h1`. Phase 17.4
therefore maps only the exact `btts` key to regulation-time BTTS and does not infer
period from human labels.

The adapter now requires:

- exactly one Yes and one No outcome;
- no unexpected point parameter.

### OddsPapi

The documented market catalog exposes `Both Teams To Score` with:

- football sport id;
- `period=fulltime`;
- `marketType=totals`;
- `handicap=0`;
- Yes/No outcomes.

The adapter accepts only that structured combination. A first-half fixture using the
same market name is ignored and never promoted to full-time canonical identity.

OddsPapi remains production-blocked independently of this technical capability.

## Canonical model

Phase 17.4 adds `MarketKind.BOTH_TEAMS_TO_SCORE`.

Canonical registry validation requires exactly:

- one `SelectionKind.YES`;
- one `SelectionKind.NO`.

The runtime market-support gate accepts only football `REGULATION` BTTS.

## End-to-end multi-source regression

The integration test uses both real adapter schemas for the same canonical Liverpool
vs Manchester United event.

It proves:

1. both source markets resolve to one canonical regulation-time BTTS market;
2. both source outcome vocabularies resolve to canonical YES/NO;
3. both transports contribute four normalized quotes in total before overlap
   consolidation;
4. duplicate Pinnacle price-origin observations consolidate under ADR-0012;
5. Bet365 supplies the best YES price at 2.10 through The Odds API;
6. Betfair supplies the best NO price at 2.05 through OddsPapi;
7. the canonical market book is complete;
8. the generic two-way evaluator detects the theoretical arbitrage;
9. a canonical Opportunity is materialized;
10. the existing conservative EUR stake allocator produces positive guaranteed
    profit.

No provider-specific arithmetic is added.

## Fail-closed regressions

Phase 17.4 verifies that:

- malformed The Odds API BTTS without exact Yes/No is rejected at the adapter
  boundary;
- BTTS carrying an unexpected numeric point is rejected;
- OddsPapi first-half BTTS is not promoted to regulation-time BTTS;
- canonical BTTS graphs missing either YES or NO are rejected;
- non-football or non-regulation canonical BTTS is unsupported.

## Code-bearing quality evidence

The code-bearing head
`03dbd1b0e6cd3ac377b393acae22ba34a42bd770` passed:

- Ruff formatting: pass (`214 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`143 source files`);
- pytest: pass (`291 passed`);
- `pip-audit`: no known vulnerabilities.

The final documentation head must preserve the same quality/security gates.

## Handoff

**Phase 17.4 is technically complete.**

The next dependency is **Phase 17.5 — football draw-no-bet settlement semantics**.

Before draw-no-bet can enter the generic opportunity path, Phase 17.5 must determine:

- canonical participant outcome completeness;
- regulation-time scope across providers;
- draw-as-refund/PUSH semantics;
- whether ordinary reciprocal-odds arbitrage is sufficient for detection;
- whether the existing stake allocator correctly models the draw refund terminal
  state;
- provider-specific mappings and fixtures;
- multi-source equivalence and fail-closed period/settlement variants.

A two-selection source shape must not be treated as ordinary win/lose merely because
the draw selection is absent.
