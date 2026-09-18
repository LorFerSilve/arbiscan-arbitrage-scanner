# Normalization engine

Phase 7 defines the deterministic semantic-normalization layer between validated provider/source data and later canonical matching/book construction.

## Safety model

Normalization is **fail closed**. A resolver returns one of:

- `RESOLVED`: exactly one canonical result is supported;
- `UNKNOWN`: no safe result exists or required context is missing;
- `AMBIGUOUS`: multiple candidates remain possible.

Callers must not treat `UNKNOWN` or `AMBIGUOUS` as canonical identity.

This phase deliberately does not perform cross-provider event matching. Event identity belongs to Phase 8.

## Text keys

`normalize_alias_key()` performs only conservative transformations:

1. validate non-empty bounded text;
2. Unicode NFKC normalization;
3. `casefold()`;
4. trim and collapse whitespace.

It intentionally does not strip accents, punctuation, hyphens, team suffixes, gender/age markers, or reserve-team qualifiers. For example, `Bayern München` and `Bayern Munich` resolve to the same participant only when both are explicitly represented as aliases.

## Sport normalization

`SportNormalizer` maps explicit textual aliases to `Sport` values. Entries may be provider-specific. A provider-only alias without provider context remains unresolved.

Examples:

- `football` -> `Sport.FOOTBALL`;
- `soccer` -> `Sport.FOOTBALL` when explicitly configured;
- provider-specific keys can override a generic alias for that provider.

## Competition normalization

`CompetitionNormalizer` resolves aliases to `CompetitionId` with optional constraints for:

- provider;
- region;
- season;
- parent competition.

Shared names are not globally collapsed. `Premier League` can therefore remain ambiguous until region or other context identifies the intended competition. Competition hierarchy and season labels are treated as context rather than decorative metadata.

## Participant normalization

`ParticipantNormalizer` resolves explicit participant aliases with context for:

- sport;
- participant kind;
- provider;
- competition;
- region.

Aliases such as `Manchester United`, `Man United`, `Manchester Utd`, or `MUN` may resolve to one canonical participant when explicitly configured. A generic term such as `United` remains ambiguous if multiple participants are compatible. `Manchester United Women` is not reduced to `Manchester United` by string heuristics.

## Market normalization

`MarketNormalizer` resolves provider terminology into a `MarketSemantic` containing:

- canonical `MarketKind`;
- canonical `MarketPeriod`;
- exact `Decimal` line where required;
- period/set/quarter index where required.

The following are intentionally distinct:

- regulation `MATCH_WINNER_3_WAY` vs `QUALIFICATION_WINNER`;
- full-event vs first-half result;
- total `2.5` vs total `3.5`;
- handicap `-1.0` vs handicap `-1.5`;
- set 1 winner vs set 2 winner.

A parameterized market without its required line, or an indexed period without its index, remains unresolved.

Market aliases may be provider-specific. Provider-specific aliases are only selected when provider context is supplied.

## Odds-format normalization

`normalize_odds()` converts source prices to canonical decimal odds for:

- decimal;
- fractional;
- American;
- implied probability.

All arithmetic uses a private 60-digit `Decimal` context. The result therefore does not change when application code modifies the ambient Decimal precision.

### Formulas

Fractional odds `a/b`:

```text
decimal = 1 + a / b
```

Positive American odds `A`:

```text
decimal = 1 + A / 100
```

Negative American odds `-A`:

```text
decimal = 1 + 100 / A
```

Implied probability `p`:

```text
decimal = 1 / p
```

Implied probability is defined as a unit probability strictly between `0` and `1`. A value such as `40` is rejected rather than guessed to mean `40%`.

Non-finite values, non-positive fractional components, American zero, impossible implied probabilities, non-profitable decimal prices (`<= 1`), and Decimal arithmetic range failures are rejected with `OddsNormalizationError`.

## Phase 17 structured parameter identity

ADR-0013 makes advanced-market parameters part of strict source/canonical identity.

Provider-neutral source records may now preserve:

- `SourceMarket.line` as an exact finite `Decimal`;
- `SourceMarket.period_index` as a positive integer;
- `SourceSelectionQuote.handicap` as an exact finite signed `Decimal`.

These fields are optional so the existing winner-market path remains backward
compatible. Once a source record maps to a canonical market/selection, however, the
structured values must match the canonical values exactly. Missing, unexpected, or
different values produce `MARKET_PARAMETER_MISMATCH` or
`SELECTION_PARAMETER_MISMATCH` and the affected quote is rejected before market-book
construction.

Canonical IDs therefore cannot hide a line mismatch. For example, an explicit hook
that accidentally maps a source total 3.5 market to canonical total 2.5 still fails
closed.

## Phase 17.2 supported-market gate

Exact identity alone does not imply that the generic arbitrage engine can model a
market's settlement outcomes. After source/canonical parameters match, strict
normalization applies the explicit market-support policy.

Phase 17.2 adds football regulation `TOTAL_POINTS` support only for positive
half-goal lines (`x.5`). Canonical totals require exactly one `OVER` and one
`UNDER` selection.

Unsupported variants produce `UNSUPPORTED_MARKET_VARIANT` before quote creation.
This includes integer totals with possible PUSH settlement, quarter lines with split
settlement, non-regulation totals, totals in other sports, and advanced market
families not yet enabled by the roadmap.

See [football regulation totals](../markets/football-regulation-totals.md) and
ADR-0014.

## Phase 17.3 Asian handicap identity and settlement gate

Football `HANDICAP` markets use an explicit ordered-participant sign convention:
`Market.line` is participant 1's signed handicap and participant 2's canonical
selection must carry its exact negation. Canonical handicap markets require exactly
those two participant selections.

The provider-neutral source boundary preserves both the market line and each
selection's signed handicap. Strict normalization therefore checks both layers:
a matching market ID cannot hide an opposite market line, and a matching selection ID
cannot hide a wrong-side handicap.

Phase 17.3 classifies Asian lines as half-goal, integer, quarter, or unsupported and
models WIN, HALF_WIN, PUSH, HALF_LOSS and LOSS settlement semantics. The existing
generic arbitrage/stake pipeline is enabled only for regulation-time football
half-goal handicaps. Integer and quarter variants emit
`UNSUPPORTED_MARKET_VARIANT` before quote construction because their PUSH or split
payout states require a settlement-aware guaranteed-return model.

See [football Asian handicap](../markets/football-asian-handicap.md) and ADR-0015.

## Phase 17.4 football BTTS identity

Phase 17.4 adds canonical `BOTH_TEAMS_TO_SCORE` as a non-parameterized
regulation-time football market with exactly one `YES` and one `NO` selection.

Provider identity is deliberately stronger than generic outcome labels:

- The Odds API mapping is the exact `btts` source market key;
- OddsPapi mapping requires `Both Teams To Score`, `period=fulltime`,
  `marketType=totals`, `handicap=0`, and exact Yes/No outcomes.

Period variants are not aliases of the regulation market. In particular, OddsPapi
first-half records are filtered before source quotes are emitted, and The Odds API
period-specific keys such as `btts_h1` are not part of the regulation BTTS alias set.

The generic market-support gate accepts only football `REGULATION` BTTS. After
canonical YES/NO completeness is established, the ordinary two-way arbitrage and
stake-allocation path is reused unchanged.

See [football BTTS](../markets/football-btts.md) and ADR-0016.

## Strict quote bridge integration

`normalize_source_snapshot()` still requires explicit canonical ID hooks for event, market, and selection identity. Phase 7 changes its price behavior: all currently supported `SourceOddsFormat` values are passed through `normalize_odds()` before an `OddsQuote` is created.

An invalid or extreme source price produces a `MALFORMED_PRICE` issue for that selection. It does not abort the rest of the snapshot.

This preserves the existing Phase 5/6 vertical slice while making odds-format handling generic and deterministic.

## Boundaries with later phases

Phase 7 does not:

- infer that two provider events are the same event;
- apply fuzzy participant matching to establish event identity;
- select the best quote per outcome;
- determine market completeness across providers.

Those concerns remain Phase 8 (event matching) and Phase 9 (market alignment / best-price book construction).

## Test coverage

The Phase-7 tests cover, among other cases:

- whitespace/case/Unicode alias-key behavior;
- provider-specific sport aliases;
- same-name competitions in different regions;
- season and competition hierarchy context;
- participant abbreviations and localization;
- ambiguous team names;
- no automatic women/reserve-name collapse;
- regulation vs qualification markets;
- first-half vs full-event periods;
- exact total/handicap lines;
- indexed set markets;
- provider-specific market aliases;
- all four source odds formats;
- caller Decimal-context independence;
- decimal overflow containment;
- strict-bridge conversion and per-selection failure isolation.
