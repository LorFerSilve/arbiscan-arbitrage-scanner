# Football both teams to score

Status: **Supported in Phase 17.4 for pre-match regulation-time football only**

## Canonical semantics

A supported both-teams-to-score (BTTS) market is represented as:

- sport: `FOOTBALL`;
- market kind: `BOTH_TEAMS_TO_SCORE`;
- period: `REGULATION`;
- no numeric line;
- no period index;
- required selections: exactly one `YES` and one `NO`.

The market answers one question only: whether both canonical event participants score
at least one goal within the regulation-time settlement scope.

## Outcome completeness

A canonical BTTS market is complete only when it contains exactly:

- one `YES` selection;
- one `NO` selection.

No participant, draw, over/under, or handicap selection belongs to this market.

The market-book layer then requires one eligible quote for each of those two canonical
selections before arbitrage evaluation is possible.

## Settlement boundary

Phase 17.4 enables **pre-match regulation-time** BTTS only.

The following remain distinct and unsupported unless a later market specification
enables them explicitly:

- first-half BTTS;
- second-half BTTS;
- live/in-play BTTS;
- team-specific scoring props;
- player scoring props;
- any provider market whose settlement scope is not demonstrated to match canonical
  regulation-time BTTS.

Provider labels alone are not sufficient evidence of equivalence.

## The Odds API mapping

The provider documents the soccer additional market key `btts` as Both Teams to
Score with outcomes `Yes` and `No`. It also documents period-specific variants such
as `btts_h1`, so ArbiScan treats the exact market key as part of source market
identity.

For explicitly configured `btts`:

- exactly two outcomes are required;
- outcome labels must be exactly one Yes and one No;
- no `point` parameter is accepted;
- `SourceMarket.line` remains `None`;
- selection handicaps remain `None`.

The default provider configuration remains `h2h`; Phase 17.4 does not silently add
BTTS requests.

Official provider references:

- https://the-odds-api.com/sports-odds-data/betting-markets.html
- https://the-odds-api.com/sports/fifa-world-cup-odds.html

## OddsPapi mapping

Phase 17.4 accepts the catalog family only when all of the following are true:

- market name is `Both Teams To Score`;
- football sport;
- non-player market;
- `period=fulltime`;
- `marketType=totals`;
- `handicap=0`;
- outcome set is exactly `Yes` and `No`.

A first-half record with the same human-readable market name is not promoted to
canonical regulation-time BTTS.

Official provider references:

- https://oddspapi.io/en/docs/get-markets
- https://oddspapi.io/sports/football

OddsPapi remains production-blocked independently of this technical market support.

## Cross-provider equivalence

Two BTTS observations may enter the same canonical market only after:

1. both source events resolve to the same canonical event;
2. source market identity resolves through the provider-specific full-time BTTS
   mapping;
3. canonical market kind is `BOTH_TEAMS_TO_SCORE`;
4. canonical period is `REGULATION`;
5. source outcomes resolve exactly to canonical YES/NO identities;
6. ordinary freshness, status, transport provenance, overlap, and price-origin rules
   pass.

No line normalization or settlement-aware payout extension is required because BTTS
is an ordinary exhaustive two-outcome win/lose market.

## Arbitrage and staking

Once the market passes all semantic and operational gates, the existing
provider-independent two-way arbitrage and stake-allocation logic is reused unchanged.

Phase 17.4 regression coverage proves a cross-source book where:

- Bet365 supplies the best YES price through The Odds API;
- Betfair supplies the best NO price through OddsPapi;
- overlapping Pinnacle observations consolidate under ADR-0012;
- the resulting opportunity passes through conservative stake allocation.

No provider-specific arithmetic is introduced.

## Explicitly unsupported variants

The following must not silently enter this canonical market:

- `btts_h1` / first-half BTTS;
- second-half BTTS;
- in-play BTTS;
- malformed source markets missing Yes or No;
- duplicate or alternative source outcomes;
- source BTTS carrying unexpected numeric point semantics;
- non-football YES/NO markets.
