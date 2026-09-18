# Football Draw No Bet

Status: **Settlement-aware support in Phase 17.5 for pre-match regulation-time football only**

## Canonical identity

Draw No Bet (DNB) is not a new canonical market family in ArbiScan.

It is represented as the already defined Asian Handicap zero line:

- sport: `FOOTBALL`;
- market kind: `HANDICAP`;
- period: `REGULATION`;
- `Market.line = Decimal("0")`;
- participant 1 selection handicap: `0`;
- participant 2 selection handicap: `0`;
- exactly the two ordered event participants are present.

This reuses the Phase 17.3 participant-anchored handicap identity instead of creating
a second canonical representation for equivalent settlement semantics.

## Settlement matrix

For stakes on both participant selections:

| Regulation result | Participant 1 DNB | Participant 2 DNB |
|---|---|---|
| Participant 1 wins | WIN | LOSS |
| Draw | PUSH / stake returned | PUSH / stake returned |
| Participant 2 wins | LOSS | WIN |

The draw is therefore a **shared refund state**.

## Reciprocal-odds mathematics

For the two DNB prices `o1` and `o2`, the ordinary reciprocal sum remains useful
for the two decisive outcomes:

```text
S = 1/o1 + 1/o2
R_decisive = 1/S
```

When `S < 1`, proportional two-way staking can create a positive return in either
decisive team-win outcome.

That does **not** imply strictly positive guaranteed profit across every settlement
state.

The draw state returns both stakes:

```text
R_refund = 1
R_worst = min(R_decisive, R_refund)
```

For a positive decisive-state edge:

```text
R_decisive > 1
R_refund = 1
R_worst = 1
worst-case profit margin = 0
```

The position is therefore no-loss under the modeled settlement states, with upside on
a decisive result, but it is not a strict positive-profit guarantee.

## Evaluation boundary

The ordinary canonical `Opportunity` and `StakePlan` path requires strictly
positive guaranteed profit. It must therefore not be used for DNB.

Phase 17.5 adds an explicit settlement-aware path:

- strict normalization defaults to `GENERIC_ARBITRAGE`;
- canonical handicap line 0 is rejected on that default path;
- callers must explicitly request `SETTLEMENT_AWARE`;
- Phase 17.5 admits only football regulation handicap 0 through that path;
- `evaluate_refundable_two_way_market()` evaluates the decisive-state reciprocal
  edge together with the shared refund state;
- the result exposes decisive return, refund return, worst-case return, and whether
  strictly positive guaranteed profit exists.

Other integer and quarter handicaps remain unsupported by this Phase 17.5 path.

## The Odds API mapping

The source market key is `draw_no_bet`.

The adapter requires:

- exactly two outcomes;
- outcome labels exactly matching the event home and away participants;
- no numeric `point` values.

It translates the source market to canonical handicap zero:

- `SourceMarket.line = 0`;
- each participant source selection receives `handicap = 0`.

The provider documents Draw No Bet as match winner excluding the draw, with a draw
returning the bet. The market is an additional event-level market; the adapter default
remains `h2h`, so DNB is opt-in.

Official provider references:

- https://the-odds-api.com/sports-odds-data/betting-markets.html
- https://the-odds-api.com/liveapi/guides/v4/

## OddsPapi mapping

OddsPapi exposes the same settlement shape through football Asian Handicap zero.

Phase 17.5 accepts the existing structured Asian Handicap mapping only when:

- football;
- non-player market;
- `period=fulltime`;
- `marketType=handicap`;
- `handicap=0`;
- outcomes are exactly participant sides `1` and `2`.

The catalog handicap becomes the canonical market line. Both selection handicaps are
therefore zero.

A first-half Asian Handicap zero market is not promoted to regulation DNB.

OddsPapi's public material identifies football Asian Handicap 0 / market 1072 as Draw
No Bet and its settlement API exposes `PUSH` as an explicit settlement result.

Provider references:

- https://oddspapi.io/en/docs/get-settlements
- https://oddspapi.io/blog/asian-handicap-api-cross-book-odds/

OddsPapi remains production-blocked until the independent provider-rights questions
are resolved.

## Cross-provider equivalence

A The Odds API DNB observation and an OddsPapi Asian Handicap zero observation may
contribute to one canonical market only after:

1. both source events resolve to the same ordered canonical event;
2. both source markets resolve to football `HANDICAP / REGULATION / line 0`;
3. both participant selections resolve to the same canonical participants;
4. all source and canonical selection handicaps equal zero;
5. settlement-aware market support is explicitly selected;
6. freshness, status, transport provenance, overlap, and price-origin rules pass.

Human labels alone never establish equivalence.

## Explicitly unsupported

Phase 17.5 does not enable through this path:

- first-half or other-period DNB;
- live/in-play DNB;
- non-football DNB;
- non-zero integer Asian handicaps;
- quarter-line Asian handicaps;
- ordinary `Opportunity` / `StakePlan` materialization that would claim strict
  positive guaranteed profit despite the draw refund.
