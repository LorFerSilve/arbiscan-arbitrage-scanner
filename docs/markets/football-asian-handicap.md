# Football Asian handicap

Status: **Supported in Phase 17.3 for pre-match regulation half-goal lines only**

## Canonical identity and sign convention

A canonical football Asian handicap is represented as:

- sport: `FOOTBALL`;
- market kind: `HANDICAP`;
- period: `REGULATION`;
- `Market.line`: exact signed handicap of **canonical event participant 1**;
- selection 1: participant 1 with `Selection.handicap == Market.line`;
- selection 2: participant 2 with `Selection.handicap == -Market.line`.

The event participant order is therefore semantic. For a Liverpool vs Manchester
United event:

```text
Market.line = -0.5
Liverpool selection          handicap = -0.5
Manchester United selection  handicap = +0.5
```

A market anchored at participant 1 `-0.5` is not the same canonical market as one
anchored at participant 1 `+0.5`. Exact source/canonical market-line equality and
exact source/canonical selection-handicap equality are both required.

## Outcome completeness

A canonical handicap market requires exactly two participant selections:

1. one selection for ordered event participant 1;
2. one selection for ordered event participant 2.

No DRAW selection belongs to the market. The two selection handicap values must be
exact opposites.

## Line classes

Phase 17.3 gives Asian handicap lines explicit settlement geometry.

### Half-goal

Examples:

- `-1.5`
- `-0.5`
- `+0.5`
- `+2.5`

These have only WIN or LOSS terminal states. No integer regulation-time goal
difference can land exactly on a half-goal boundary.

This is the only line class currently allowed into the generic arbitrage and stake
allocation pipeline.

### Integer

Examples:

- `-1`
- `0`
- `+2`

An adjusted score of exactly zero produces a PUSH. The original stake is returned.

Integer lines are represented by the settlement model but are not yet eligible for
generic arbitrage evaluation because the existing opportunity/stake model assumes one
ordinary winning payout per terminal selection rather than a shared stake-return
state.

### Quarter

Examples:

- `-0.75`
- `-0.25`
- `+0.25`
- `+1.75`

A quarter line is split into two equal half-stakes on adjacent integer/half-goal
lines. Examples:

```text
-0.25 -> 50% at -0.5 + 50% at 0
-0.75 -> 50% at -1.0 + 50% at -0.5
+0.25 -> 50% at 0 + 50% at +0.5
```

This creates HALF_WIN and HALF_LOSS states in addition to WIN, PUSH and LOSS.

Quarter lines are represented by the settlement model but fail closed before quote
construction for generic arbitrage detection.

## Settlement model

`settle_asian_handicap()` accepts:

- the selected participant's signed handicap;
- the selected participant's regulation-time goal difference versus its opponent;
- exact decimal odds.

For each component:

```text
goal_difference + handicap > 0  -> WIN
goal_difference + handicap = 0  -> PUSH
goal_difference + handicap < 0  -> LOSS
```

The returned gross multiplier is measured against the original stake:

- WIN -> decimal odds;
- HALF_WIN -> half at decimal odds + half returned;
- PUSH -> 1;
- HALF_LOSS -> half returned;
- LOSS -> 0.

The settlement implementation is provider-independent.

## Generic-engine boundary

The existing `ArbitrageEvaluation` and `StakePlan` are sufficient for half-goal
handicaps because the market remains an ordinary mutually exclusive two-outcome
win/lose market.

They are **not** sufficient to claim guaranteed profit for integer or quarter lines.
Those variants require a future settlement-aware evaluator/stake allocator that
checks guaranteed return over all score/settlement scenarios rather than assuming a
single ordinary winner.

Accordingly, strict normalization emits `UNSUPPORTED_MARKET_VARIANT` for:

- integer handicaps;
- quarter-line handicaps;
- unsupported non-quarter granularity;
- non-regulation football handicaps;
- handicaps in other sports.

## The Odds API mapping

For explicitly configured `spreads`:

- source outcomes must match the exact event home and away participant labels;
- both outcomes must contain numeric `point` values;
- the two point values must be exact opposites;
- `SourceMarket.line` is anchored to the home participant's point;
- each `SourceSelectionQuote.handicap` preserves its own point.

The default adapter request remains `h2h`; Phase 17.3 does not silently add
`spreads`.

Provider reference:
https://the-odds-api.com/liveapi/guides/v4/

## OddsPapi mapping

Phase 17.3 recognizes football `Asian Handicap` catalog markets when:

- the market is non-player;
- period is `fulltime`;
- the outcome set is exactly `1` and `2`.

The catalog `handicap` is interpreted as participant-1's line:

- outcome `1` receives the catalog handicap;
- outcome `2` receives its exact negation;
- `SourceMarket.line` receives the catalog handicap.

Provider references:

- https://oddspapi.io/en/docs/get-markets
- https://oddspapi.io/en/docs/get-settlements

OddsPapi remains production-blocked independently of this technical mapping.

## Cross-provider equivalence

Two handicap observations can contribute to the same canonical market only after:

1. the events resolve to the same verified ordered canonical event;
2. both resolve to `HANDICAP` / `REGULATION`;
3. their participant-1 anchored market lines are exactly equal;
4. each selection maps to the same canonical participant;
5. each signed selection handicap exactly matches canonical identity;
6. the support policy accepts the line class;
7. freshness, status, provenance, overlap and price-origin rules pass.

Provider labels alone never establish handicap equivalence.

## Explicitly deferred

Phase 17.3 does not enable:

- integer Asian handicaps;
- quarter/split Asian handicaps;
- first-half or other period handicaps;
- live/in-play handicaps;
- non-football handicap families.

Enabling integer or quarter lines requires a settlement-aware guaranteed-return and
stake-allocation model rather than an adapter-only change.
