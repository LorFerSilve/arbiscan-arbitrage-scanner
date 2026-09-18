# ADR-0014 — Enable football totals only when settlement is push-free

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Phase 17.2 is the first advanced market family to enter ArbiScan's generic arbitrage
engine.

Football totals look like a simple two-outcome market, but not every numeric line has
the same settlement structure. A half-goal line such as 2.5 has only two terminal
outcomes: Over wins or Under wins. An integer line such as 3.0 can push when exactly
three goals are scored. Asian quarter lines such as 2.25 or 2.75 may split a stake and
produce half-win or half-loss settlement.

The current generic arbitrage mathematics assumes each canonical selection has one
decimal price and that the required outcome set is mutually exclusive and collectively
exhaustive under ordinary win/lose settlement. It does not model returned stakes or
split settlements.

The Odds API exposes totals with a structured point, and OddsPapi exposes full-time
Over/Under markets with a numeric market handicap/line. OddsPapi also documents
settlement states including PUSH, HALF-WIN, and HALF-LOSS.

## Decision

Phase 17.2 enables football pre-match regulation totals only when the canonical line
is a positive half-goal value (`x.5`).

The runtime market-support policy must reject before quote construction:

- integer total lines;
- quarter/split lines;
- non-positive lines;
- non-regulation football totals;
- totals for other sports.

Canonical total markets must contain exactly one OVER and one UNDER selection.

Exact line identity from ADR-0013 remains mandatory. Explicit canonical ID mappings
cannot bypass this settlement-support gate.

## Rationale

Half-goal football totals fit the existing two-outcome mathematical model without
adding a hidden third settlement state.

Restricting the initial implementation is preferable to interpreting provider prices
under incomplete settlement assumptions. It lets Phase 17.2 deliver real
cross-provider advanced-market arbitrage while keeping the established
fail-closed correctness policy.

## Consequences

### Positive

- a supported total has an unambiguous two-outcome settlement model;
- the existing arbitrage core can be reused without provider-specific math;
- integer and quarter lines cannot create false guaranteed-return calculations;
- exact line and outcome completeness are enforced before market-book construction;
- future settlement-aware work has an explicit boundary to extend.

### Negative / trade-offs

- valid bookmaker markets at integer and quarter lines are intentionally ignored;
- coverage is lower than the raw provider feeds offer;
- Asian totals require a later richer settlement model before they can be enabled.

## Alternatives considered

### Treat integer totals as ordinary two-way markets

Rejected. A push can return stake, so the modeled terminal payouts differ from a
simple win/lose pair.

### Treat quarter lines as ordinary two-way markets

Rejected. Split settlement can produce half-win/half-loss states that the current
single-price leg model does not represent.

### Add push and split settlement to the arbitrage core immediately

Deferred. That is broader than the smallest coherent Phase 17.2 dependency and would
change generic stake/payout semantics. It should be introduced through its own
explicit model and regression suite.

### Let each provider adapter decide which lines are safe

Rejected. Settlement eligibility is a canonical market-policy concern, not a
provider-specific arithmetic rule.

## Revisit triggers

Revisit this decision when:

- the canonical settlement model represents push/refund outcomes;
- stake plans can represent split-line or half-win/half-loss payouts;
- a later market family requires the same richer settlement algebra;
- provider-specific settlement rules demonstrate that a nominal line cannot be
  classified safely from the current semantic fields.
