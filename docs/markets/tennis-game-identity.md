# Tennis game-market identity

Status: **Semantic foundation complete; runtime enablement intentionally closed in Phase 17.7**

## Why a game needs nested identity

A tennis game is not identified by one ordinal alone.

"Game 3" is ambiguous without its containing set:

- Set 1 / Game 3;
- Set 2 / Game 3;
- Set 3 / Game 3;

are different sporting propositions.

Phase 17.7 therefore introduces a canonical nested identity:

- sport: `TENNIS`;
- market kind: `GAME_WINNER`;
- period: `GAME`;
- `set_index`: the containing set number;
- `period_index`: the game number inside that set;
- exactly two participant selections covering the event participants;
- no market line;
- no selection handicap.

The same pair is preserved at the provider-neutral source boundary.

## Strict normalization

Both indexes are semantic parameters.

Strict normalization requires exact equality:

```text
source.set_index    == canonical.set_index
source.period_index == canonical.period_index
```

A Set 1 / Game 3 source market can therefore never be mapped to:

- Set 2 / Game 3;
- Set 1 / Game 4;
- any unindexed "current game" market.

Parameter mismatch is rejected before market-family support is evaluated.

## Runtime support remains closed

Phase 17.7 does **not** enable `GAME_WINNER` for generic arbitrage.

Even a source market carrying the exact canonical set/game pair returns
`UNSUPPORTED_MARKET_VARIANT` until a provider mapping demonstrates all required
machine-readable semantics.

This is deliberate: adding a canonical representation is not evidence that a live
provider exposes the same wager stably.

## Fixed numbered game versus mutable current/next game

A fixed wager such as:

```text
Set 2 / Game 3 winner
```

can be stable if the provider supplies machine-readable set and game indexes.

A label such as:

```text
Current Game Winner
Next Game Winner
Game Winner
```

is not sufficient by itself. Its identity depends on mutable match score state and
possibly service order at the observation time.

ArbiScan will not infer set/game identity from:

- labels;
- current score strings;
- bookmaker display order;
- arrival sequence;
- an assumed service rotation.

A future live-game implementation needs explicit provider score-state/version
semantics before such markets can be canonicalized.

## Server and receiver identity

For an exact fixed Set N / Game M winner market, server identity is not automatically
part of canonical identity: the sporting proposition can be identified by the event,
set, game, and winning participant.

However, if a provider defines a market relative to "next service game", "server to
hold", or another service-relative proposition, server/receiver identity becomes
semantic input and must be modeled explicitly before support.

Phase 17.7 does not collapse service-relative markets into `GAME_WINNER`.

## Tiebreaks

A tiebreak is not assumed to be an ordinary numbered game.

Tennis formats can differ by competition and deciding-set rules. A future provider
mapping must establish whether a quoted tiebreak:

- is represented as an ordinary game index;
- has its own provider market family;
- is a match/set tiebreak proposition with different settlement semantics.

Until then, tiebreak markets remain unsupported.

## OddsPapi feasibility

Current OddsPapi public tennis material demonstrates broad match, set, and game market
families, including Game Handicap, total-games families, tiebreaks, and related
derivatives.

The reviewed public material does not establish a stable machine-readable
`Set N / Game M Winner` identity sufficient for ArbiScan's game-winner canonical
mapping.

Phase 17.7 therefore:

- does not add an OddsPapi game-winner mapping;
- keeps generic `Game Handicap` data outside `GAME_WINNER`;
- includes a negative fixture proving such a family is not promoted accidentally.

References:

- https://oddspapi.io/sports/tennis
- https://oddspapi.io/blog/us-open-odds-api/
- https://oddspapi.io/en/docs/get-markets

OddsPapi remains production-blocked independently of this technical conclusion.

## The Odds API feasibility

Current The Odds API documentation exposes tennis match and set-level keys, including
documented `h2h_s1` and `h2h_s2` set moneylines, plus tennis spreads/totals.

The reviewed market-key list does not provide a fixed individual numbered
`Set N / Game M Winner` key.

Phase 17.7 therefore does not add a game-winner mapping for this transport.

References:

- https://the-odds-api.com/sports-odds-data/betting-markets.html
- https://the-odds-api.com/sports/tennis-odds.html
- https://the-odds-api.com/liveapi/guides/v4/

## Exceptional settlement

Even after stable game identity exists, retirement, walkover, abandonment, unfinished
games, and tiebreak-specific bookmaker rules can affect settlement.

Phase 17.7 does not claim bookmaker-rule-independent executable profit for game
markets. Runtime support remains closed before that problem is reached.

## Enablement checklist

A future `GAME_WINNER` provider mapping may be enabled only when it proves:

1. exact event identity;
2. structured positive set index;
3. structured positive game index;
4. exact two-participant outcome completeness;
5. fixed numbered-game semantics rather than mutable "current/next" state, or an
   explicit score-state/version model;
6. tiebreak distinction;
7. relevant service-relative semantics where applicable;
8. documented settlement treatment for incomplete/abandoned games;
9. deterministic fixtures and strict mismatch regressions.

Until those gates exist, the family remains fail closed.
