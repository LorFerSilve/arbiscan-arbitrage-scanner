# Phase 19 — Football 1X2 side/settlement semantics (fail closed)

Status: source-documented semantic contract, **not** live quote authorization.
Date: 2026-10-28.

## Source evidence (no metered API requests)

1. [OddsPapi V4 `GET /markets`](https://oddspapi.io/us/docs/get-markets) explicitly documents soccer `sportId=10`, `marketId=101`, `marketName=Full Time Result`, `period=fulltime`, `marketType=1x2`, no handicap or player props, three outcomes `101=1`, `102=X`, `103=2`.
2. [OddsPapi's football-market guide](https://oddspapi.io/blog/football-odds-api-soccer-data/) identifies `101=Home`, `102=Draw`, `103=Away`.
3. [OddsPapi's score/settlement discussion](https://oddspapi.io/blog/football-data-api-betting-predictions/) distinguishes `scores.periods.fulltime` (90-minute score) from `scores.periods.result` (post-extra-time final score). We must **never** grade a 90-minute bet on `result`.
4. [OddsPapi V4 fixtures](https://oddspapi.io/us/docs/get-fixtures) describes `participant1Id` as the **first** participant and `participant2Id` as the **second**, without a universally binding football home/away invariant. [OddsPapi 1X2 outcome naming](https://oddspapi.io/en/docs/get-odds) is bookmaker market-side evidence, not proof that every fixture's participant1 is home.
5. [OddsPapi V4 settlements](https://oddspapi.io/en/docs/get-settlements) documents `WIN`, `LOSE`, `PUSH`, `HALFWIN`, `HALFLOSS`, `CANCELLED`, and `UNDECIDED`; 90-minute 1X2 winning outcomes should resolve to exactly one WIN and two LOSE **on a normally completed match**. All other statuses require explicit separate policy handling.
6. [The Odds API's betting-market catalog](https://the-odds-api.com/sports-odds-data/betting-markets.html) specifies soccer `h2h` includes the draw. It does **not** certify every underlying bookmaker's abandonment, delay, extra-time, or dispute handling.

## Implementation

`src/arbiscan/normalization/football_1x2.py` is a pure semantic contract:

- only exact OddsPapi soccer market `101`, outcome IDs `101/102/103` and labels `1/X/2`, type `1x2`, period `fulltime`, zero handicap, no player props are compatible with `MATCH_WINNER_3_WAY / REGULATION`;
- no source participant position is used to assign a home/away market side;
- a three-outcome The Odds API soccer `h2h` can be recognized only with exact source event home/away team names and a unique draw, not fuzzy names or selection order;
- explicit normalized team IDs can establish whether OddsPapi `participant1/participant2` are aligned or reversed **relative to a specific home/away reference**; they cannot independently prove OddsPapi's fixture-role semantics;
- regulation-time scores are checked as nonnegative integers; a draw remains a draw even if the later match winner changes in extra time;
- if verified score and OddsPapi 1X2 grades are supplied for offline review, *all* three IDs must be present, only exact WIN/LOSE allowed, and exactly the expected winner wins;
- OddsPapi's production adapter now refuses malformed or altered market 101 shapes (unknown market IDs, swapped outcome IDs, non-regulation periods, partial three-way, etc.).

## Authorization boundaries

**No provider odds are requested by this change.** The live EPL discovery still makes no odds calls and maintains its existing OddsPapi 3-request cap. The Phase-19 canonical identity comparison has only provisional matches. It has **zero quote-eligible matches**.

Before ever combining odds from the two feeds, require:

1. a verified per-fixture home/away reference and source participant role agreement; do not assume that `participant1=home` from naming order alone;
2. a definitive Phase-8 match and explicit canonical `MarketId` /`SelectionId` mappings for `REGULATION` 1X2, not simply similar market labels;
3. evidence of underlying bookmaker settlement rules for 90 minutes + stoppage time and any extra-time, abandonment/postponement/void handling. Market names alone are not sufficient;
4. complete active fresh quotes and all three distinct outcomes, passing the existing Phase-9 market-book gate.

No automatic mapping to `result` or to `FULL_EVENT` should be made from OddsPapi `fulltime`. Do not create Phase-8 quote-authorizing hooks for the current read-only review, even if all synthetic tests pass.
