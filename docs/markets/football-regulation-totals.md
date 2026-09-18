# Football regulation totals

Status: **Supported in Phase 17.2 for pre-match positive half-goal lines only**

## Canonical semantics

A supported football total is represented as:

- sport: `FOOTBALL`;
- market kind: `TOTAL_POINTS`;
- period: `REGULATION`;
- line: an exact positive finite `Decimal` ending in `.5`;
- required selections: exactly one `OVER` and one `UNDER`.

The line is part of canonical market identity. Total 2.5 and total 3.5 are different
markets and must never share quotes, selections, completeness state, or arbitrage
evaluation.

## Settlement boundary

Phase 17.2 intentionally supports only push-free half-goal totals such as 0.5, 1.5,
2.5, and 3.5.

Integer lines are not enabled because an exact score equal to the line may settle as
a push/refund. Quarter lines such as 2.25 and 2.75 are not enabled because Asian
settlement can split a stake and produce half-win or half-loss outcomes.

The current generic arbitrage engine models mutually exclusive win/lose selections
with one decimal price per leg. Treating push or split-settlement markets as ordinary
two-outcome markets would overstate the guaranteed-return model.

Until a later settlement-aware model is introduced:

- integer totals fail closed;
- quarter-line totals fail closed;
- non-positive totals fail closed;
- full-event/overtime-inclusive totals fail closed;
- non-football totals fail closed.

## Provider mappings

### The Odds API

Phase 17.2 accepts an explicitly configured `totals` market only when:

- every outcome contains a numeric `point`;
- all outcomes share exactly one point;
- the market contains exactly one `Over` and one `Under` outcome.

The shared point is preserved as `SourceMarket.line`.

The default adapter configuration remains `h2h`; totals are not silently added to
existing requests.

Provider reference:
https://the-odds-api.com/liveapi/guides/v4/

### OddsPapi

Phase 17.2 recognizes the catalog family only when all of the following are true:

- market name is `Over Under Full Time`;
- period is `fulltime`;
- market type is `totals`;
- the catalog handicap/line is positive;
- the outcome set is exactly `Over` and `Under`;
- it is not a player prop.

The catalog `handicap` value is preserved as `SourceMarket.line`.

Provider references:

- https://oddspapi.io/en/docs/get-markets
- https://oddspapi.io/en/docs/get-settlements

OddsPapi remains production-blocked independently of this technical market support.

## Cross-provider equivalence

Two source totals may enter one canonical market only after:

1. their sporting events resolve to the same verified canonical event;
2. both resolve to `TOTAL_POINTS`;
3. both resolve to `REGULATION`;
4. their exact `Decimal` lines are identical;
5. their selections resolve to the same canonical OVER/UNDER identities;
6. the market support policy accepts the line;
7. normal freshness, status, provenance, and multi-source overlap rules pass.

Labels are not sufficient evidence of equivalence.

## Completeness

A canonical total market is complete only when its registry contains exactly:

- one `OVER` selection;
- one `UNDER` selection.

The market-book layer then requires one eligible quote for each of those selections.
An Over quote at 2.5 cannot complete an Under quote at 3.5.

## Arbitrage evaluation

After all semantic and operational gates pass, the existing provider-independent
two-way arbitrage mathematics is reused unchanged:

`1 / over_odds + 1 / under_odds < 1`

No provider-specific arithmetic is permitted.

Phase 17.2 regression coverage proves a book whose best prices are supplied by two
different real transport schemas, while overlapping observations of the same
bookmaker continue to follow ADR-0012 consolidation.

## Explicitly unsupported variants

The following must not silently enter the generic engine:

- integer totals;
- quarter-line / split Asian totals;
- first-half or other period totals;
- overtime-inclusive totals;
- live/in-play totals;
- team totals;
- player totals;
- non-football totals;
- malformed source totals with incomplete or duplicate Over/Under outcomes.

A later phase may enable any of these only after defining its settlement semantics and
test matrix.
