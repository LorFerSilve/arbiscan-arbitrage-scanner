# Phase 17.3 completion — football Asian handicap settlement semantics

Date: 2026-09-18

## Scope

Phase 17.3 defines canonical football Asian handicap identity and settlement
semantics, enables the safe half-goal subset end to end, and keeps integer/quarter
variants outside the generic arbitrage engine until their scenario-dependent payouts
can be modeled by opportunity and stake allocation.

## Canonical line identity

ADR-0015 establishes:

- `Market.line` is ordered canonical participant 1's signed handicap;
- participant 1 selection handicap equals `Market.line`;
- participant 2 selection handicap equals its exact negation;
- the canonical market contains exactly those two participant selections.

The registry rejects incomplete, wrong-side or non-mirrored handicap graphs.

## Settlement semantics

The new provider-independent Asian-handicap domain model classifies exact Decimal
lines as:

- half-goal;
- integer;
- quarter;
- unsupported.

It explicitly represents WIN, HALF_WIN, PUSH, HALF_LOSS and LOSS.

Quarter lines are decomposed into two equal half-stakes on adjacent lines. The
settlement function returns an exact gross-return multiplier against the original
stake.

Regression examples include:

- `-0.5` ordinary win/loss;
- `-1` PUSH at a one-goal winning margin;
- `+0.25` HALF_WIN on a draw;
- `-0.25` HALF_LOSS on a draw;
- `-0.75` HALF_WIN at a one-goal winning margin.

## Execution boundary

The existing generic `ArbitrageEvaluation` and `StakePlan` are sufficient for
half-goal Asian handicaps. Strict normalization therefore enables only:

- football;
- regulation time;
- half-goal handicap line.

Integer, quarter and unsupported line granularities are rejected with
`UNSUPPORTED_MARKET_VARIANT` before quote construction. Their settlement semantics
are known, but a future settlement-aware payout matrix is required before ArbiScan may
claim a guaranteed arbitrage or produce an executable stake plan for them.

## Provider mappings

### The Odds API

Configured `spreads` now require:

- exactly two outcomes;
- exact event home/away labels;
- a structured point on each outcome;
- exact opposite signed points.

The source market line is anchored to the home participant's point and each source
selection preserves its own signed handicap.

Malformed participant labels or non-opposite spread points fail at the adapter
boundary.

### OddsPapi

Schema-faithful fixtures validate football full-time `Asian Handicap` catalog
markets:

- outcome `1` receives the catalog handicap;
- outcome `2` receives its exact negation;
- source market line equals the catalog handicap.

Synthetic fixtures exercise `-0.5`, `+0.5`, `0` and `-0.25` lines.

OddsPapi remains development-only until its independent production-rights blockers
are resolved.

## End-to-end regression

The Phase 17.3 integration path uses both real adapter schemas for the same canonical
Liverpool vs Manchester United event and participant-1 line `-0.5`.

It proves:

1. both transports map to the same anchored canonical handicap;
2. source selection handicaps match the canonical participant sides exactly;
3. overlapping Pinnacle observations remain transport-distinct and consolidate by
   price origin under ADR-0012;
4. Bet365 supplies participant 1 `-0.5` at 2.10 through The Odds API;
5. Betfair supplies participant 2 `+0.5` at 2.05 through OddsPapi;
6. the canonical best-price book is complete;
7. the existing generic evaluator detects the theoretical arbitrage;
8. a canonical Opportunity is materialized;
9. the existing conservative EUR stake allocator produces a plan with positive
   guaranteed profit.

Additional regressions prove:

- participant-1 `-0.5` and participant-1 `+0.5` remain distinct markets and
  cannot complete each other;
- integer `0` and quarter `-0.25` variants fail before quote construction.

## Code-bearing quality evidence

The code-bearing head
`da3806f3eb400f091c1e51600698ea5b4da9cce8` passed:

- Ruff formatting: pass (`210 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`142 source files`);
- pytest: pass (`283 passed`);
- `pip-audit`: no known vulnerabilities.

Security analysis on the final documentation head must remain green before this phase
is marked review-ready.

## Handoff

**Phase 17.3 is technically complete.**

The next dependency is **Phase 17.4 — football both-teams-to-score semantics and
provider feasibility**.

Before enablement, Phase 17.4 must confirm:

- canonical regulation-time settlement scope;
- exact YES/NO outcome completeness;
- provider-specific source mappings from supported endpoints;
- whether each real provider exposes equivalent pre-match BTTS semantics through the
  currently supported API surface;
- cross-source equivalence and fail-closed unsupported variants;
- end-to-end market-book/arbitrage regressions without provider-specific core math.
