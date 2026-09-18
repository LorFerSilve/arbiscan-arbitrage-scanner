# Phase 17.7 completion — tennis game-market identity and score-state semantics

Date: 2026-09-18

## Scope

Phase 17.7 determines whether individual tennis game markets can safely enter the
canonical arbitrage pipeline.

The result is a **semantic foundation with runtime enablement intentionally closed**.

The current canonical model needed one additional hierarchy dimension, while current
public provider evidence was insufficient to activate a stable numbered game-winner
mapping.

## Canonical foundation

Added:

- `MarketKind.GAME_WINNER`;
- `MarketPeriod.GAME`;
- `Market.set_index`.

For a game market:

- `set_index` is the containing set number;
- `period_index` is the game number within that set;
- both are positive and mandatory.

`set_index` is rejected for non-game periods.

The provider-neutral `SourceMarket` preserves the same optional structured
`set_index`, with validation that it can only appear together with a positive game
index.

## Normalization foundation

`MarketSemantic` and `MarketAlias` now support a required set index for GAME
periods.

Strict normalization compares all advanced market parameters:

- line;
- `period_index`;
- `set_index`.

The Phase 17.7 regression proves:

- exact Set 1 / Game 3 identity reaches the market-support gate and is rejected as
  `UNSUPPORTED_MARKET_VARIANT`;
- source Set 2 / Game 3 mapped to canonical Set 1 / Game 3 fails earlier with
  `MARKET_PARAMETER_MISMATCH`;
- source Set 1 / Game 4 mapped to canonical Set 1 / Game 3 also fails earlier with
  `MARKET_PARAMETER_MISMATCH`.

## Canonical completeness

A `GAME_WINNER` market requires exactly two participant selections covering the
event participants and no selection handicaps.

This ensures that when the family is eventually enabled, it will still enter the
ordinary two-outcome engine only as a complete participant pair.

## Provider feasibility

### OddsPapi

Current public tennis coverage demonstrates game-related families such as Game
Handicap, totals, tiebreaks, and other set/game derivatives.

The Phase 17.7 review did not establish a stable documented machine-readable
Set N / Game M Winner identity.

A deterministic negative fixture proves that a generic `Game Handicap` family is
not promoted to `GAME_WINNER`.

### The Odds API

Current public market documentation includes tennis set-level moneyline keys
`h2h_s1` and `h2h_s2`, plus tennis spreads/totals.

The reviewed key list does not provide a fixed individual Set N / Game M Winner key.

No game-winner mapping is added.

## Score-state conclusion

A fixed Set N / Game M market can use the new nested identity if a future provider
supplies both indexes explicitly.

A mutable "current game" or "next game" market cannot be made stable from a label.
It needs provider score-state/version identity and potentially service context.

ArbiScan does not infer those values from score strings or service rotation.

## Tiebreak and settlement conclusion

Tiebreak propositions remain distinct until provider semantics prove how they map.

Retirement, walkover, abandonment, and unfinished-game bookmaker rules also remain
outside the current execution-realism model.

Because no provider game-winner mapping is enabled, no game-level Opportunity or
StakePlan can currently be emitted.

## Code-bearing quality evidence

The code-bearing head
`664c2a4e6919057601585270bbbc7b457444c72f` passed:

- Ruff formatting: pass (`228 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`148 source files`);
- pytest: pass (`316 passed`);
- `pip-audit`: no known vulnerabilities.

The final documentation head must preserve the same quality/security gates.

## Handoff

**Phase 17.7 is technically complete as a fail-closed semantic foundation.**

The next dependency is **Phase 17.8 — basketball spreads/totals and overtime-period
semantics**.

Before basketball enablement, Phase 17.8 must establish:

- canonical `BASKETBALL` sport support;
- regulation versus overtime-inclusive settlement identity;
- exact spread orientation and mirrored participant lines;
- total-points line identity;
- integer/half/quarter settlement behavior where provider rules differ;
- provider-specific market mappings across available transports;
- exact two-participant / Over-Under completeness;
- cross-provider same-line equivalence;
- whether existing generic arbitrage/stake math is sufficient for the supported
  settlement subset;
- fail-closed handling of quarters, halves, alternate lines, and live markets unless
  separately modeled.
