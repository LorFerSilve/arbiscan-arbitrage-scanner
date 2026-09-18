# Tennis indexed set winner

Status: **Supported for documented pre-match Set 1 and Set 2 markets across both real transport schemas**

## Canonical semantics

A tennis set-winner market is represented as:

- sport: `TENNIS`;
- market kind: `SET_WINNER`;
- period: `SET`;
- a mandatory positive `period_index`;
- no numeric line;
- exactly two `PARTICIPANT` selections covering the event participants;
- no selection handicaps.

Phase 17.6 enables only `period_index` **1** and **2** because these are the indexed
set-winner markets currently demonstrated by the supported provider schema.

Set identity is a first-class market parameter. Set 1 and Set 2 are different
canonical markets even when:

- the event is the same;
- the participant labels are the same;
- the bookmakers are the same;
- the prices happen to be identical.

## Structured period identity

Canonical set identity must never be inferred by parsing free-form labels such as
"First Set Winner".

The source adapter must preserve a structured set index. Strict normalization then
requires:

```text
source_market.period_index == canonical_market.period_index
```

A mismatch fails with `MARKET_PARAMETER_MISMATCH` before quote construction.

## Outcome completeness

Every canonical set-winner market requires exactly:

- one participant selection for event participant A;
- one participant selection for event participant B.

Missing, duplicate, outsider, or non-participant outcomes invalidate the canonical
graph.

For a normally completed set, exactly one participant wins the set, so the existing
ordinary two-outcome reciprocal-odds and stake-allocation model is sufficient for the
theoretical market calculation.

## OddsPapi mapping

Phase 17.6 uses the provider's exact documented tennis market identities:

- market **123** — First Set Winner — period `p1` — canonical `period_index=1`;
- market **125** — Second Set Winner — period `p2` — canonical
  `period_index=2`.

Both require:

- tennis sport;
- non-player market;
- `marketType=winner`;
- `handicap=0`;
- exactly outcomes `1` and `2`.

The market ID, market name, and provider period are checked together. A record such
as market 125 carrying period `p1` is ignored fail-closed.

Outcome labels `1` and `2` refer to the provider fixture participant ordering.
They are resolved to canonical participant IDs only after event matching.

OddsPapi remains production-blocked independently of this technical capability.

## The Odds API mapping

Phase 17.8 implements the provider's documented tennis set moneyline keys:

- `h2h_s1` — first-set moneyline — canonical `period_index=1`;
- `h2h_s2` — second-set moneyline — canonical `period_index=2`.

The adapter accepts those keys only when:

- the event is tennis;
- exactly two outcomes are present;
- outcome labels exactly match the event participants;
- no outcome carries a `point`.

The set number is preserved as structured `SourceMarket.period_index`. It is never
derived from display labels.

The default provider request remains `h2h`; set markets are opt-in.

Official reference:

- https://the-odds-api.com/sports-odds-data/betting-markets.html

## Cross-transport equivalence

Phase 17.8 proves that The Odds API `h2h_s1` / `h2h_s2` and OddsPapi market
123 / 125 normalize to the same canonical Set 1 / Set 2 identities.

The regression deliberately exposes Pinnacle through both transports. Equal-time,
equal-price observations consolidate under ADR-0012 to one executable Pinnacle price
origin per set/selection while preserving transport provenance.

Before consolidation the two transports contribute 16 source quotes. Four Pinnacle
overlaps collapse deterministically, leaving 12 executable quotes with no material
conflicts.

## Arbitrage boundary

For a normally completed set, the two participant outcomes form an ordinary complete
two-way book. The existing generic path can therefore perform:

- best-price selection;
- reciprocal-odds evaluation;
- Opportunity creation;
- conservative stake allocation.

The Phase 17.6 regression established indexed-set arithmetic on OddsPapi. Phase 17.8
extends the same canonical markets across both real transport schemas and proves
same-bookmaker overlap consolidation before best-price selection.

## Retirement, walkover, and incomplete-set caveat

Tennis settlement has exceptional states that are not represented by the current
quote schema as bookmaker-specific rules.

A retirement, walkover, abandonment, or incomplete set may be voided or settled
differently depending on bookmaker rules. OddsPapi also exposes settlement states
such as `CANCELLED` and `UNDECIDED`.

Therefore Phase 17.6 proves the **theoretical completed-set price calculation**. It
does not upgrade tennis set-winner signals to a bookmaker-rule-independent claim of
realized or executable guaranteed profit under exceptional settlement conditions.

A later execution-realism layer must incorporate bookmaker-specific tennis settlement
rules before making that stronger claim.

## Explicitly unsupported

Phase 17.6 does not enable:

- set 3 or later set-winner markets without an exact supported provider mapping;
- tennis game-winner markets;
- live/in-play set markets;
- label-derived set indexes;
- cross-comparison between different `period_index` values;
- bookmaker-rule-independent guarantees for retirement, walkover, abandonment, or
  incomplete-set settlement.
