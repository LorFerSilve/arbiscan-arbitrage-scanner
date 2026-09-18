# ADR-0017 — Reuse Asian Handicap 0 for Draw No Bet and require refund-aware evaluation

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Football Draw No Bet (DNB) is a two-priced market with three settlement states.

If participant 1 wins, participant 1 DNB wins and participant 2 DNB loses. The
opposite applies when participant 2 wins. On a regulation-time draw, both bets push
and the stakes are returned.

This creates two related architectural questions.

First, DNB is settlement-equivalent to Asian Handicap 0. Creating another canonical
market kind would give one sporting proposition two canonical identities.

Second, reciprocal-odds mathematics across the two participant prices can identify a
positive return in each decisive outcome, but it omits the shared draw-refund state.
The existing `Opportunity` and `StakePlan` schemas describe strictly positive
guaranteed profit and therefore cannot truthfully represent DNB when a draw returns
exactly the total stake.

## Decision

### Canonical identity

DNB reuses the canonical Asian Handicap representation:

- `MarketKind.HANDICAP`;
- `MarketPeriod.REGULATION`;
- `Market.line = 0`;
- exactly two participant selections;
- both selection handicaps equal zero.

No `DRAW_NO_BET` market kind is added.

### Evaluation-path gate

Normalization distinguishes the intended evaluation path with
`MarketSupportPurpose`.

The default remains `GENERIC_ARBITRAGE`. Handicap zero remains unsupported on that
path.

`SETTLEMENT_AWARE` explicitly enables only football regulation handicap zero in
Phase 17.5. It does not unlock other integer or quarter Asian handicap lines.

### Refund-aware mathematics

For the two participant prices, the existing reciprocal calculation is retained as
the decisive-state calculation:

```text
S = 1/o1 + 1/o2
R_decisive = 1/S
```

The shared draw state has:

```text
R_refund = 1
R_worst = min(R_decisive, R_refund)
```

`RefundableTwoWayEvaluation` records both decisive and refund outcomes.

When `S < 1`, DNB may be classified as a refundable/no-loss arbitrage under the
modeled settlement states, but `has_strict_guaranteed_profit` remains false because
the draw produces zero profit.

### Opportunity and stake-plan boundary

Phase 17.5 does not materialize ordinary canonical `Opportunity` or `StakePlan`
objects for DNB.

Those schemas currently require strictly positive guaranteed profit. Reusing them
would either violate domain validation or misrepresent the draw settlement.

## Rationale

Reusing Asian Handicap zero keeps canonical identity normalized and aligns both real
provider schemas to the same existing settlement concept.

Making the evaluation path explicit prevents a generic caller from accidentally
treating a refundable market as an ordinary exhaustive win/lose market.

The dedicated evaluation object preserves useful cross-book price information without
weakening the meaning of "guaranteed profit" elsewhere in the product.

## Consequences

### Positive

- DNB and Asian Handicap 0 cannot diverge into duplicate canonical identities;
- default generic normalization remains fail-closed;
- the draw-refund terminal state is explicitly represented;
- decisive-state reciprocal mathematics is reused rather than duplicated;
- no-loss/conditional-upside semantics remain distinct from strict positive
  guaranteed profit;
- other integer and quarter handicap variants stay closed until their own payout
  paths are implemented.

### Negative / trade-offs

- DNB cannot yet use the ordinary `Opportunity` lifecycle or `StakePlan` output;
- callers must explicitly select the settlement-aware normalization path;
- a later settlement-aware staking/product model is needed if DNB should become an
  actionable user-facing opportunity type.

## Alternatives considered

### Add a dedicated DRAW_NO_BET market kind

Rejected. DNB is already exactly represented by football regulation Asian Handicap 0.

### Treat DNB as an ordinary two-outcome guaranteed-profit market

Rejected. A draw returns both stakes, so the worst-case profit is zero when the
decisive states are profitable.

### Allow generic normalization and fix the result later

Rejected. Incorrect settlement semantics must be blocked before ordinary opportunity
generation rather than repaired downstream.

### Enable every integer handicap in settlement-aware mode

Rejected. Lines such as -1 or +1 have different push conditions tied to winning
margins. Phase 17.5 intentionally adds only the exact DNB / line-zero case.

### Force DNB into the existing StakePlan with zero guaranteed profit

Rejected. The current domain contract intentionally requires positive guaranteed
profit. Weakening it would change the meaning of all existing stake plans.

## Revisit triggers

Revisit this decision when:

- ArbiScan introduces a general settlement-scenario payout matrix;
- a settlement-aware stake allocator can represent refundable terminal states;
- the product introduces a distinct no-loss/conditional-upside opportunity type;
- other integer handicap lines become a roadmap dependency;
- provider settlement evidence materially differs from the modeled line-zero rules.
