# Phase 3 completion record

Status: **Complete pending final CI verification on this documentation commit**

## Roadmap exit criteria

### Arbitrage detection is mathematically correct and provider-independent

Satisfied by the pure `arbiscan.arbitrage` API. The core consumes canonical `OddsQuote` values and canonical selection IDs only. It performs no provider API calls, persistence, networking, clock reads, ID generation, or provider-payload interpretation.

The theoretical boundary uses:

```text
S = Σ(1 / o_i)
```

with arbitrage possible only for `S < 1`. Finite Decimal odds are converted losslessly to exact rational values for the boundary comparison, so fair books such as `3 / 3 / 3` remain exactly non-arbitrage rather than being affected by rounded repeating thirds.

### Core calculations are reproducible and numerically controlled

Satisfied by:

- strict finite `Decimal` inputs for odds, monetary values, margins, limits, increments, and currency quanta;
- rejection of binary float inputs at mathematical boundaries;
- exact rational classification of the `S < 1` condition;
- a private 60-significant-digit Decimal context for rendered probabilities, multipliers, margins, and stake calculations;
- an explicit regression proving caller/global Decimal precision does not change evaluation metrics;
- deterministic ordering by canonical selection identity;
- caller-supplied IDs and timestamps for canonical output materialization.

ADR-0004 records the numerical and rounding policy.

### Complete-market semantics fail closed

`evaluate_market()` requires exactly one active quote for every caller-supplied expected canonical selection and rejects:

- invalid odds;
- fewer than two outcomes;
- duplicate quote IDs;
- duplicate selections;
- missing selections;
- unexpected selections;
- quotes from different canonical events;
- quotes from different canonical markets;
- non-active quotes.

Two-way, three-way, and arbitrary `n`-outcome books share the same calculation path.

### Stake allocation respects executable constraints

`allocate_stakes()` supports:

- bankroll ceilings;
- per-quote minimum stake;
- per-quote maximum stake;
- per-quote stake increments;
- currency quantum policy;
- configurable minimum guaranteed profit.

Minimum stakes are incorporated through a deterministic constrained equal-payout solve. Maximum stakes cap the achievable payout target. Discrete stakes are selected from valid increment-grid candidates.

Expected payouts used for guarantee claims are rounded **down** to the currency quantum. A canonical `StakePlan` is emitted only when the final rounded guaranteed profit is strictly positive and satisfies the configured guaranteed-profit threshold. A theoretical opportunity that loses its profit after rounding returns no guaranteed plan.

### Mathematical properties and edge cases are tested

The Phase 3 suite covers deterministic examples and deterministic seeded randomized properties, including:

- exact `S == 1` behavior;
- invalid odds and float rejection;
- configurable theoretical margin thresholds;
- two-way and three-way opportunities;
- arbitrary `n`-outcome books;
- duplicate/incomplete/cross-market books;
- order invariance;
- 250 randomized exact-boundary books;
- randomized profitable multi-outcome books;
- 100 randomized post-rounding stake plans;
- minimum/maximum stake behavior;
- stake increments;
- insufficient bankroll;
- conservative currency rounding;
- post-rounding loss of theoretical arbitrage;
- caller Decimal-context independence.

## Verified CI result before this completion-record commit

The Phase 3 pull request was validated on the repository's pinned Python 3.13.15 / uv toolchain with:

- `uv lock --check`: passed;
- Ruff format check: passed;
- Ruff lint: passed;
- strict mypy: no issues in 28 source files;
- pytest: **42 tests passed**;
- `pip-audit`: **no known vulnerabilities found**.

The final documentation-only commit that adds this record must pass the same repository quality gate before merge.

## Deliberate Phase 3 boundaries

- Phase 3 does not fetch odds or implement provider adapters; Phase 4 owns the provider port and fake provider.
- Phase 3 does not choose the best provider quote per selection; later market-book construction/arbitrage scanning owns quote selection.
- Phase 3 does not match provider events or markets; normalization and matching phases own semantic alignment.
- Phase 3 does not decide quote freshness or stale-data policy; ingestion/freshness phases own those operational rules.
- Phase 3 does not model provider-specific settlement rules, taxes, exchange commission, fees, boosts, cash-out behavior, or promotional eligibility.
- Phase 3 does not place or automate wagers.
- The discrete allocator is a deterministic safe-plan constructor around the constrained continuous equal-payout target; Phase 3 requires safety and reproducibility, not a claim of globally optimal stake utilization under every possible future provider rule.

## Result

After final CI verification, Phase 3 establishes the provider-independent mathematical foundation required by all later ingestion, normalization, matching, scanning, persistence, alerting, and presentation phases.
