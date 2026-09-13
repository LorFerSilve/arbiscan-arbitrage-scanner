# ADR-0004 — Arbitrage numerical and rounding policy

- Status: Accepted
- Date: 2026-09-13
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Phase 3 must decide whether a complete market is a theoretical arbitrage, calculate reproducible margins, and convert a theoretical opportunity into stakes that remain profitable after bookmaker constraints and currency rounding.

Binary floating-point arithmetic is unsuitable for guarantee claims because representation error can move a value across the `S == 1` boundary or create cent-level payout discrepancies. Plain `Decimal` division is substantially safer for money, but repeating reciprocals such as `1 / 3` are still rounded to the active Decimal context. A fair three-way book with odds `3, 3, 3` must therefore not become an arbitrage merely because three rounded thirds sum below one.

Stake allocation introduces a second correctness boundary. Bookmakers may impose minimum stakes, maximum stakes, and stake increments. Even when the continuous formula is profitable, executable rounded stakes can remove that profit. The scanner must never report a guaranteed stake plan unless the rounded plan itself is strictly profitable.

## Decision

ArbiScan adopts the following Phase 3 numerical policy:

1. External mathematical inputs that represent odds, money, margins, limits, increments, or currency quanta must be finite `Decimal` values. Binary floats are rejected.
2. The theoretical `S < 1` boundary is evaluated using exact rational arithmetic derived losslessly from the input Decimals.
3. Public probability, multiplier, and margin values are materialized as Decimals under a private fixed precision context of 60 significant digits with `ROUND_HALF_EVEN`.
4. Arbitrage classification fails closed if the materialized margin is not strictly positive, even when an exact difference exists below the representable fixed-precision result.
5. The mathematics core never reads a clock, generates IDs, performs I/O, or accesses provider-specific payloads. IDs and timestamps required for canonical output objects are supplied by the caller.
6. Stake amounts must lie on an explicit increment grid. The configured stake increment must be an exact multiple of the currency quantum.
7. Expected payouts used for guarantee claims are rounded **down** to the configured currency quantum.
8. Minimum and maximum stake constraints are applied before a `StakePlan` can be emitted.
9. When minimum stakes distort the unconstrained allocation, the allocator first solves a deterministic constrained continuous equal-payout target. Discrete allocation then descends only through relevant payout breakpoints: for each target it computes the minimum valid stake needed by every outcome, and if that target is not safe or profitable it moves to the highest lower payout reachable by reducing one currently required stake by one increment. This continues until a safe plan is found or no lower breakpoint exists.
10. All stake totals, payout comparisons, and guaranteed-profit arithmetic use the private fixed Decimal context rather than the caller's ambient Decimal context.
11. A `StakePlan` is returned only when the final rounded `guaranteed_profit` is strictly positive and satisfies any configured absolute guaranteed-profit threshold. Otherwise allocation returns no executable plan.

## Rationale

Exact rational comparison makes the theoretical boundary mathematically correct for finite decimal odds, including repeating reciprocal cases. Decimal remains the canonical representation exposed to the rest of the system and is appropriate for money and persisted values.

Conservative payout rounding is intentionally asymmetric: ArbiScan prefers underestimating a payout by at most one currency quantum to overstating a guarantee. The resulting stake plan is therefore safe with respect to the rounding policy encoded by Phase 3.

The event-driven discrete search is necessary because the nearest floor/ceiling stakes around the continuous optimum are not sufficient. A lower stake can sometimes reduce total outlay by more than it reduces the conservative guaranteed payout, turning a zero-profit rounded allocation into a positive executable one. Searching payout breakpoints rather than every currency quantum avoids skipping those valid lower-grid plans while still avoiding a blind cent-by-cent scan.

Keeping time, ID generation, networking, databases, and provider semantics outside the core preserves deterministic replay. Given the same canonical quotes, constraints, bankroll, policy, IDs, and timestamps, the result is reproducible.

## Consequences

### Positive

- exact `S == 1` classification for finite decimal odds;
- no uncontrolled binary floating-point boundary behavior;
- deterministic replay and testing;
- explicit bookmaker stake constraints;
- guaranteed-profit claims are based on rounded executable stakes rather than continuous theory;
- lower-grid profitable plans are not discarded merely because the nearest continuous-target grid points are non-profitable;
- arbitrary `n`-outcome books use the same core functions.

### Negative / trade-offs

- rational boundary calculation is more expensive than native float arithmetic;
- 60-digit Decimal materialization is a deliberate finite representation even though the boundary comparison is exact;
- discrete breakpoint descent may inspect multiple stake-grid transitions for very fine increments and large bankrolls;
- the Phase 3 allocator models stake limits and increments, but not every bookmaker-specific settlement or fee rule;
- a theoretically profitable opportunity may correctly produce no executable `StakePlan` for a specific bankroll or constraint set.

## Alternatives considered

### Binary float throughout

Rejected because exact-boundary and monetary guarantee behavior would depend on binary representation artifacts.

### Decimal only, including the `S < 1` boundary

Rejected because repeating reciprocals are rounded by the Decimal context. A mathematically fair book can therefore appear infinitesimally below or above one.

### Fraction/rational values throughout the domain model

Rejected because money, serialized domain values, and integration boundaries are naturally decimal. Exact rationals are used only where they materially improve the classification boundary.

### Only adjacent floor/ceiling stakes around the continuous target

Rejected because it can produce a false negative. For example, with odds `1.5 / 3.5`, a `0.25` bankroll, and cent increments, the closest rounded allocation can have zero guaranteed profit while the lower `0.16 / 0.07` allocation yields conservative payouts of `0.24 / 0.24` and a guaranteed profit of `0.01`.

### Round payouts to nearest currency quantum

Rejected for guarantee claims. Rounding down is conservative and cannot overstate the modeled payout.

## Revisit triggers

Revisit this ADR if:

- a supported provider settles payouts using a materially different documented rounding rule;
- exchange commission, taxes, fees, or stake-dependent odds must enter the core formula;
- performance profiling shows exact rational boundary checks or discrete payout-breakpoint search are bottlenecks at production scale;
- currencies or assets with non-decimal settlement units are introduced;
- automated wager execution is added to product scope.
