# Arbitrage mathematics core

## Scope

Phase 3 provides the pure mathematical core for evaluating one complete canonical market book and, when possible, converting a theoretical arbitrage into a rounded executable `StakePlan`.

It deliberately does **not**:

- fetch or normalize provider data;
- choose the best provider quote per outcome;
- decide quote freshness;
- match events or markets;
- model provider-specific settlement rules, commission, taxes, or fees;
- place bets.

Those concerns belong to later phases.

## Core formula

For decimal odds `o_1 ... o_n`:

```text
S = Σ (1 / o_i)
```

A theoretical arbitrage exists only when:

```text
S < 1
```

The equalized theoretical gross return multiplier is:

```text
R = 1 / S
```

and the gross theoretical profit margin is:

```text
M = R - 1
```

For bankroll `B`, the unconstrained continuous stake for outcome `i` is:

```text
stake_i = B * (1 / o_i) / S
```

All ideal payouts are then equal to:

```text
B / S
```

## Public API

`arbiscan.arbitrage` exposes:

- `implied_probability()`;
- `implied_probability_sum()`;
- `gross_return_multiplier()`;
- `theoretical_profit_margin()`;
- `is_theoretical_arbitrage()`;
- `evaluate_market()`;
- `build_opportunity()`;
- `allocate_stakes()`;
- `ArbitrageEvaluation`;
- `StakeConstraint`;
- `CurrencyRoundingPolicy`.

## Complete-book requirement

`evaluate_market()` requires exactly one active canonical quote for every expected canonical selection.

It rejects:

- fewer than two outcomes;
- duplicate selection IDs;
- duplicate quote IDs;
- quotes from different canonical events;
- quotes from different canonical markets;
- suspended, closed, or unknown quote statuses;
- missing outcomes;
- unexpected outcomes.

The function does not infer completeness from market names. The caller supplies the expected canonical selection IDs. Later market-alignment phases are responsible for constructing that exact book.

## Determinism and precision

Odds and money inputs are strict finite `Decimal` values. Floats are rejected.

The exact `S < 1` decision is calculated using rational numbers derived losslessly from the finite decimal odds. This prevents a fair book such as:

```text
3.00 / 3.00 / 3.00
```

from being misclassified because a finite decimal approximation of `1/3` was summed three times.

Public probability/margin values are materialized under a private 60-significant-digit Decimal context. Caller changes to the process-global Decimal context therefore do not control the core formula output.

## Minimum theoretical margin

`is_theoretical_arbitrage()` and `evaluate_market()` accept `minimum_profit_margin`.

For example:

```text
minimum_profit_margin = Decimal("0.01")
```

requires at least a 1% gross theoretical margin. The book must still satisfy `S < 1`; a threshold of zero does not turn a fair `S == 1` book into an arbitrage.

## Opportunity materialization

`build_opportunity()` converts a positive `ArbitrageEvaluation` into the Phase 2 canonical `Opportunity` schema.

The caller supplies:

- `OpportunityId`;
- `detected_at`.

The mathematics layer intentionally does not generate IDs or read the system clock.

## Stake constraints

`StakeConstraint` supports, per quote:

- `minimum_stake`;
- optional `maximum_stake`;
- `stake_increment`.

Stake increments use a zero-based grid. For example, an increment of `0.05` permits `0.05`, `0.10`, `0.15`, and so on, subject to minimum/maximum limits.

If a provider minimum is not itself on the increment grid, the effective minimum is rounded upward to the first valid grid point. A maximum is rounded downward to the last valid grid point.

The increment must be an exact multiple of the currency quantum.

## Currency rounding policy

`CurrencyRoundingPolicy` contains:

- a three-letter currency code;
- a positive decimal `quantum`.

For EUR, the normal policy is:

```text
CurrencyRoundingPolicy("EUR", Decimal("0.01"))
```

Stake amounts are placed on bookmaker increment grids. Expected payouts used for guarantee claims are rounded **down** to the currency quantum.

This is intentionally conservative. If an unrounded payout is EUR `101.009`, the guarantee calculation uses EUR `101.00`, not EUR `101.01`.

## Constrained allocation

Bookmaker minimum stakes can distort the simple proportional formula. Phase 3 therefore solves a constrained continuous equal-payout target first:

1. start from all outcomes;
2. pin any outcome whose equalized stake would fall below its effective minimum;
3. recompute the target payout with the remaining bankroll and unpinned outcomes;
4. repeat until all remaining outcomes satisfy their minimums;
5. cap the target by every effective maximum stake;
6. create the adjacent valid lower/upper increment-grid candidates around that continuous target;
7. evaluate deterministic combinations implied by candidate payout levels;
8. select the candidate plan with highest conservative guaranteed profit, then deterministic tie-breaks.

The final plan may use less than the supplied bankroll when limits or rounding make additional stake economically harmful.

## Guaranteed-profit rule

`allocate_stakes()` returns a `StakePlan` only when all of the following remain true **after** constraints and payout rounding:

- all outcomes have a positive valid stake;
- total stake does not exceed bankroll;
- every stake respects its increment/minimum/maximum constraints;
- `guaranteed_payout` is the minimum conservative payout across outcomes;
- `guaranteed_profit = guaranteed_payout - total_staked`;
- guaranteed profit is strictly positive;
- guaranteed profit satisfies `minimum_guaranteed_profit` when configured.

Otherwise it returns `None`.

This is important for small-bankroll or low-margin opportunities. For example, odds `2.01 / 2.01` are theoretically profitable, but a EUR 1.00 bankroll can round both EUR 0.50 payouts down to EUR 1.00. The rounded guaranteed profit is then zero, so no guaranteed `StakePlan` is emitted.

## Reproducibility

The Phase 3 core has no provider-specific schema dependency and performs no I/O. A calculation can be reproduced from:

- canonical quotes;
- expected selection IDs;
- configured thresholds;
- bankroll;
- currency policy;
- stake constraints;
- caller-supplied canonical IDs/timestamps.
