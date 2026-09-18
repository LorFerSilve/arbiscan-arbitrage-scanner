# ADR-0019 — Model nested tennis game identity but keep runtime support closed without stable score-state semantics

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Phase 17.6 established that a tennis set number is structural market identity. A game
introduces another hierarchy level.

A game ordinal alone is ambiguous. Set 1 / Game 3 and Set 2 / Game 3 are different
bets even though both may have the same two players and the same human-facing
"Game 3 Winner" label.

The previous canonical `Market` model carried only one indexed period value and
could not represent both dimensions simultaneously.

Provider feasibility adds a second problem. Current public provider material exposes
many tennis game-related families, but the Phase 17.7 review did not establish an
exact stable machine-readable Set N / Game M Winner mapping on either existing
transport. Some game markets may be score-relative or service-relative.

## Decision

### Canonical model

Add:

- `MarketKind.GAME_WINNER`;
- `MarketPeriod.GAME`;
- `Market.set_index`.

For `MarketPeriod.GAME`:

- `set_index >= 1` is mandatory;
- `period_index >= 1` remains mandatory and represents the game number inside the
  set.

`set_index` is invalid on non-game periods.

### Source model

`SourceMarket` also carries optional `set_index`.

When supplied:

- it must be a positive integer;
- it requires a positive `period_index`.

### Normalization

`MarketSemantic` and `MarketAlias` can require both indexes.

Strict normalization compares:

- line;
- period index;
- set index;

before market support.

Set or game mismatch returns `MARKET_PARAMETER_MISMATCH`.

### Outcome completeness

A canonical `GAME_WINNER` requires exactly two participant selections covering the
event participants and no handicaps.

### Runtime support

`GAME_WINNER` remains unsupported in the Phase 17.7 market-support policy.

A fully structured source market still fails with `UNSUPPORTED_MARKET_VARIANT`
until a provider-specific mapping proves stable machine identity and settlement.

### Mutable score-state markets

"Current game", "next game", display-order, or score-derived labels do not establish
canonical game identity.

ArbiScan will not reconstruct game identity from mutable score text or assumed tennis
service rotation.

If future provider data exposes only relative current/next-game semantics, a separate
score-state/version model must be designed before enablement.

### Tiebreak and service-relative propositions

Tiebreak identity and service-relative propositions are not implicitly collapsed into
ordinary `GAME_WINNER`.

Provider semantics must demonstrate whether these are:

- exact numbered games;
- separate market kinds;
- score-state-relative wagers.

## Rationale

Nested structured identity prevents a false arbitrage created by mixing quotes from
different games.

Separating semantic representability from provider enablement preserves the project's
fail-closed rule: the domain may know how to express a concept without pretending a
provider feed has proven that concept.

The additional `set_index` field is the smallest extension that preserves the
existing meaning of `period_index` for SET/PERIOD/QUARTER markets while allowing
GAME to represent its parent set.

## Consequences

### Positive

- Set 1 / Game 3 and Set 2 / Game 3 cannot collide canonically;
- source/canonical set and game indexes are independently auditable;
- game labels cannot silently become canonical identity;
- future exact numbered-game providers can integrate without another domain redesign;
- current provider uncertainty remains fail closed.

### Negative / trade-offs

- one more optional parameter exists on canonical and source market records;
- no tennis game opportunity is emitted by Phase 17.7;
- service-relative and tiebreak markets still need dedicated semantic review;
- live score-state versioning remains unresolved.

## Alternatives considered

### Reuse only period_index for game number

Rejected. The containing set would be lost, allowing cross-set collisions.

### Encode set and game into one integer/string

Rejected. Composite presentation values are harder to validate and invite provider
parsing into canonical identity.

### Parse set/game from provider labels

Rejected under ADR-0013. Labels are not structured identity.

### Treat "current game" as a fixed game market

Rejected. Its referent changes as the match progresses.

### Require server identity on every fixed numbered game

Not adopted as a universal invariant. For a true fixed Set N / Game M winner, event +
set + game + participant identifies the proposition. Service identity becomes
mandatory only when provider settlement or market definition is service-relative.

### Enable OddsPapi Game Handicap as GAME_WINNER

Rejected. Handicap over games is a different market family and does not prove
individual numbered-game winner identity.

## Revisit triggers

Revisit this ADR when:

- a provider documents exact Set N / Game M market identifiers;
- live score-state/version data becomes a planned capability;
- service-relative game markets enter scope;
- tiebreak-specific markets are implemented;
- bookmaker-specific game settlement rules enter the execution model.
