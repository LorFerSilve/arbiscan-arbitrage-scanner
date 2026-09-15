# Phase 12 — Opportunity lifecycle and execution realism

Phase 12 separates theoretical arbitrage detection from operational actionability.

## Lifecycle

`LifecycleState` represents `DETECTED`, `VALIDATED`, `ACTIONABLE`, `STALE`, `INVALIDATED`, and `EXPIRED`. Revalidation is fail-closed and returns a machine-readable `LifecycleReason`.

An opportunity is surfaced as `ACTIONABLE` only after the current quote set is verified, all quotes are active and fresh, current prices still form arbitrage, configured drift tolerance is respected, and a conservative rounded stake plan remains profitable after configured commission/tax assumptions and profit/ROI thresholds.

## Operational policy

`ActionabilityPolicy` supports:

- bankroll and maximum exposure;
- per-quote minimum/maximum stakes and stake increments through the existing `StakeConstraint` contract;
- currency and monetary quantum through `CurrencyRoundingPolicy`;
- minimum guaranteed net profit and ROI;
- maximum quote age;
- maximum deterioration in theoretical margin as the odds-drift tolerance;
- configured commission and tax rates.

Account-specific bookmaker limits are represented by user-supplied per-quote stake constraints. The scanner does not infer private account limits.

## Revalidation order

1. Verify the quote identity set still matches the detected opportunity.
2. Reject suspended/closed quotes and stale/future observations.
3. Recompute theoretical arbitrage from current prices.
4. Reject excessive deterioration relative to the detected theoretical margin when configured.
5. Rebuild a conservative stake plan with current prices, stake limits, increments, rounding and maximum exposure.
6. Apply configured commission/tax assumptions to guaranteed post-rounding profit.
7. Enforce minimum net guaranteed profit and minimum net ROI.

The output includes the stake plan (when one can be constructed), gross and net guaranteed profit, net ROI, and the complete operational assumptions used for the decision.

## Boundary

This phase remains scanner-only. It does not place bets, authenticate bookmaker accounts, transfer funds, or execute orders. Actionability means that the opportunity satisfies the configured operational model; it is not a guarantee that a bookmaker will accept a wager.
