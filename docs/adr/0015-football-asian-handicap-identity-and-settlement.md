# ADR-0015 — Anchor football Asian handicap identity and gate complex settlement

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Asian handicap markets introduce two distinct correctness problems.

First, a signed handicap has a side. A bare line such as `-0.5` is ambiguous unless
ArbiScan defines which ordered event participant owns that value. Provider schemas
represent the same idea differently: The Odds API exposes a signed point on each
spread outcome, while OddsPapi exposes a market-level handicap plus participant-side
outcomes.

Second, Asian line geometry changes payout semantics. Half-goal lines settle as
ordinary WIN/LOSS. Integer lines can PUSH. Quarter lines split a stake across adjacent
lines and may produce HALF_WIN or HALF_LOSS. ArbiScan's existing generic
`ArbitrageEvaluation` and `StakePlan` assume an ordinary complete outcome book
whose winning leg pays its decimal odds; they do not enumerate shared push or
split-settlement scenarios.

## Decision

### Canonical line orientation

For a canonical `HANDICAP` market:

- `Market.line` is the exact signed handicap of ordered canonical event participant 1;
- participant 1's `Selection.handicap` must equal `Market.line`;
- participant 2's `Selection.handicap` must equal `-Market.line`;
- exactly those two participant selections are required.

This orientation is provider-independent and is validated by the canonical registry.

### Settlement representation

ArbiScan represents Asian handicap line classes explicitly:

- half-goal;
- integer;
- quarter;
- unsupported granularity.

The domain settlement model represents:

- WIN;
- HALF_WIN;
- PUSH;
- HALF_LOSS;
- LOSS.

Quarter lines decompose into two equal half-stake components on adjacent
integer/half-goal lines. Settlement returns an exact gross-return multiplier on the
original stake.

### Generic arbitrage boundary

Only football pre-match regulation **half-goal** handicap lines may enter the existing
generic arbitrage and stake-allocation pipeline.

Integer and quarter lines remain structurally representable and settleable by the
domain semantics, but strict normalization must reject them before canonical quotes
are constructed for generic arbitrage detection.

A future implementation that enables those lines must use a settlement-aware
guaranteed-return/stake model that evaluates all relevant terminal settlement
scenarios.

## Rationale

A stable participant-1 anchor makes the market line deterministic across providers and
prevents accidental equivalence between opposite handicap directions.

Separating settlement semantics from current execution eligibility avoids two unsafe
shortcuts:

1. hiding line orientation in provider-specific labels or IDs;
2. treating PUSH/HALF_WIN/HALF_LOSS as if they were ordinary two-way WIN/LOSS
   payouts.

Half-goal lines can reuse the proven generic engine because they have exactly the
ordinary two terminal payout states that engine assumes.

## Consequences

### Positive

- signed handicap identity is deterministic and provider-independent;
- market and selection parameters independently defend against side inversion;
- integer/quarter settlement behavior is explicitly modeled rather than ignored;
- half-goal handicap arbitrage reuses existing tested math and stake allocation;
- unsafe line classes cannot silently produce false guaranteed-profit claims;
- provider adapters remain translation layers rather than owners of payout math.

### Negative / trade-offs

- integer and quarter Asian handicap coverage is deliberately unavailable to the
  generic opportunity pipeline;
- a future settlement-aware arbitrage/staking engine will be more complex than the
  current reciprocal-odds calculation;
- ordered participant identity becomes a required invariant for handicap mapping.

## Alternatives considered

### Use an unsigned market line and keep sign only on selections

Rejected. It removes one exact market-level identity check and makes cross-provider
market orientation less explicit.

### Define `Market.line` as an absolute handicap magnitude

Rejected. `0.5` would not distinguish participant-1 +0.5 from participant-1 -0.5.

### Enable integer lines in the generic two-way formula

Rejected. A PUSH returns both stakes on the pushed side's settlement scenario; that is
not represented by the ordinary winner-pays-decimal-odds model used by the current
guaranteed-return calculation.

### Enable quarter lines by replacing them with one synthetic decimal price

Rejected. HALF_WIN/HALF_LOSS are stake-split payout states and cannot be represented
correctly by one ordinary WIN/LOSS price without losing scenario semantics.

## Revisit triggers

Revisit the execution boundary when:

- the arbitrage evaluator can model scenario-dependent payout matrices;
- the stake allocator can guarantee profit across PUSH and split-settlement states;
- additional market families need the same settlement algebra;
- provider evidence shows a market-level handicap orientation that cannot be mapped
  safely to ordered participant 1.
