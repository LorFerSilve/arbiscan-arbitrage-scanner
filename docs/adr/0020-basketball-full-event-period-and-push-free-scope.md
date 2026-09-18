# ADR-0020 — Basketball full-event period and push-free scope

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Basketball providers expose game-level spreads/totals alongside quarter, half, alternate,
and regulation-only families. OddsPapi explicitly labels its main total and handicap as
including overtime. The Odds API exposes featured `spreads` and `totals` separately
from period-specific `*_qN` and `*_hN` keys.

Canonical comparison must not erase settlement scope, and the generic two-outcome
arbitrage engine must not treat PUSH or split-settlement lines as strict guaranteed
profit.

## Decision

Phase 17.9 introduces canonical `Sport.BASKETBALL`.

The only newly enabled advanced basketball markets are:

- `TOTAL_POINTS / FULL_EVENT` on positive half-point lines;
- `HANDICAP / FULL_EVENT` on half-point lines.

`FULL_EVENT` means the complete provider game market, including overtime where the
source family explicitly carries that semantics. Basketball regulation-time markets
remain a separate canonical period and are not interchangeable.

Spread identity is anchored to ordered participant 1 exactly like the existing
canonical handicap invariant: participant 1 carries `Market.line`, participant 2
carries its exact negation.

Integer lines can PUSH. Quarter lines can require split settlement. They therefore
remain ineligible for the generic reciprocal-odds/stake engine. Quarter, half,
alternate, and live market families are not promoted to the full-event family.

## Consequences

### Positive

- overtime-inclusive and regulation-only markets cannot share canonical identity;
- same-line full-event observations from independent transports can consolidate safely;
- half-point totals/spreads can reuse the existing deterministic two-outcome math;
- unsupported settlement geometry fails before opportunity construction.

### Negative / trade-offs

- useful integer and quarter-line basketball markets remain unavailable;
- provider-specific regulation and sub-period markets need later semantic work;
- full-event equivalence still depends on exact provider market-family mapping.

## Revisit triggers

Revisit when ArbiScan gains scenario-aware PUSH/split-settlement staking, enables
quarter/half/live basketball markets, or provider documentation changes settlement
scope.
