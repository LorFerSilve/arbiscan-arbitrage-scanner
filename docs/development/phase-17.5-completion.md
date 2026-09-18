# Phase 17.5 completion — football Draw No Bet settlement semantics

Date: 2026-09-18

## Scope

Phase 17.5 defines regulation-time football Draw No Bet (DNB), proves cross-provider
equivalence, and introduces a settlement-aware evaluation boundary so a draw refund
cannot be misreported as strictly positive guaranteed profit.

## Canonical identity

DNB reuses the Phase 17.3 Asian Handicap representation:

- `MarketKind.HANDICAP`;
- `MarketPeriod.REGULATION`;
- line `0`;
- exactly the two ordered event participants;
- both participant selection handicaps equal `0`.

No duplicate DNB market kind is introduced.

## Settlement conclusion

DNB has three terminal states:

- participant 1 wins;
- participant 2 wins;
- draw, where both stakes are refunded.

The ordinary reciprocal sum remains valid for the two decisive outcomes. If
`1/o1 + 1/o2 < 1`, the decisive-state equalized return is greater than one.

The draw return multiplier is exactly one. Therefore a profitable decisive-state book
has:

- positive decisive-state margin;
- zero draw-state profit;
- worst-case return multiplier exactly `1`;
- worst-case profit margin exactly `0`.

This is a refundable/no-loss edge under the modeled settlement states, not a strict
positive-profit guarantee.

## Evaluation architecture

Phase 17.5 adds:

- `MarketSupportPurpose.GENERIC_ARBITRAGE`;
- `MarketSupportPurpose.SETTLEMENT_AWARE`;
- `RefundableTwoWayEvaluation`;
- `evaluate_refundable_two_way_market()`.

Generic normalization remains the default and still rejects handicap zero.

The settlement-aware path admits only football regulation handicap zero. Other
integer and quarter lines remain unsupported.

The existing `Opportunity` and `StakePlan` path is deliberately not used for DNB
because those schemas require strictly positive guaranteed profit.

## Provider mappings

### The Odds API

The exact `draw_no_bet` market is mapped to canonical handicap zero.

The adapter requires:

- exactly two outcomes;
- exact event home/away participant labels;
- no numeric `point`.

It emits:

- source market line `0`;
- selection handicap `0` on both participant outcomes.

### OddsPapi

The existing Asian Handicap mapping supplies DNB through full-time handicap zero.

Phase 17.5 additionally tightens Asian Handicap catalog eligibility to require
`marketType=handicap`.

For line zero:

- outcome `1` has handicap `0`;
- outcome `2` has handicap `0`;
- source market line is `0`.

A first-half handicap-zero catalog record is ignored.

OddsPapi remains development-only until its independent production-rights blockers
are resolved.

## End-to-end multi-source regression

The integration path uses both real adapter schemas for the same canonical Liverpool
vs Manchester United regulation DNB market.

It proves:

1. the generic normalization path rejects both DNB sources;
2. the explicit settlement-aware path accepts both sources;
3. eight raw normalized quote observations are produced before overlap
   consolidation;
4. overlapping Pinnacle observations consolidate under ADR-0012;
5. six executable price-origin quotes remain across Pinnacle, Bet365, and Betfair;
6. Bet365 supplies participant 1 DNB at **2.10** through The Odds API;
7. Betfair supplies participant 2 DNB at **2.05** through OddsPapi;
8. the canonical two-participant market book is complete;
9. the reciprocal decisive-state prefilter is positive;
10. refund-aware evaluation records a draw return multiplier of `1`;
11. worst-case profit is exactly `0`;
12. strict guaranteed-profit status is false.

## Fail-closed regressions

Phase 17.5 verifies that:

- The Odds API DNB with wrong participant outcomes fails;
- The Odds API DNB carrying an unexpected point fails;
- OddsPapi first-half Asian Handicap zero is not promoted to regulation DNB;
- generic normalization cannot emit DNB quotes;
- settlement-aware support does not unlock other integer handicaps.

## Code-bearing quality evidence

The code-bearing head
`dd548e999b901feb6a7495cf2f4ad5488da45167` passed:

- Ruff formatting: pass (`220 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`146 source files`);
- pytest: pass (`303 passed`);
- `pip-audit`: no known vulnerabilities.

The final documentation head must preserve the same quality and security gates.

## Handoff

**Phase 17.5 is technically complete.**

The next dependency is **Phase 17.6 — tennis set-winner and indexed-set semantics**.

Before enablement, Phase 17.6 must establish:

- canonical set index as mandatory market identity;
- exact two-participant outcome completeness;
- provider-specific source mappings for individual set winner markets;
- whether both real transports expose equivalent pre-match set markets;
- strict rejection of set 1 versus set 2/3 cross-comparison;
- retirement/withdrawal and incomplete-set settlement behavior where relevant;
- end-to-end same-set market-book construction without label-derived set identity.
