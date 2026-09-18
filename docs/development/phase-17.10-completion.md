# Phase 17.10 completion — Motorsport/F1 semantics and provider feasibility gate

**Status:** Technically complete on 2026-09-18.

## Delivered

- explicit motorsport race, qualifying, session, and tournament periods;
- `PODIUM_FINISH` and `HEAD_TO_HEAD` canonical market kinds;
- subject-specific podium identity through `Market.subject_participant_id`;
- strict race-winner full-grid completeness;
- exact podium YES/NO completeness;
- exact two-driver H2H completeness;
- runtime support gate that rejects all motorsport winner/podium/H2H evaluation;
- The Odds API motorsport discovery boundary that rejects binary event promotion for
  outright-style event shapes;
- OddsPapi feasibility regression proving an unverified motorsport sport record is
  not guessed into canonical support;
- deterministic tests for scope separation, participant identity, completeness, and
  fail-closed runtime behavior;
- ADR-0021 and dedicated market semantics documentation.

## Why no F1 market is enabled

Phase 17.10 found no publicly documented, cross-transport machine-readable contract
that proves equivalent F1 winner, podium, or H2H identity plus DNS/DNF,
disqualification, void, and dead-heat settlement behavior.

Enabling a market based on names alone would violate the Phase 17 correctness rule.
The phase is therefore complete as a semantic and provider-feasibility gate, analogous
to the earlier tennis game-market gate.

## Next dependency

**Phase 17.11 — broader outright tournament/championship markets.**

That phase should generalize multi-participant outright identity beyond motorsport,
including complete candidate sets, field/other outcomes, withdrawal/void behavior,
dead-heat settlement, and provider equivalence before any generic outright market is
enabled.
