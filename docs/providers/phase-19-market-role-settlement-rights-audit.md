# Phase 19 — Football 1X2: source roles, bookmaker rules and rights audit

**Review date:** 2026-10-28. **Result:** public evidence documented,
**live quote authorization still blocked**. Zero provider calls were made
during this research and the audit command makes no HTTP requests.

Run:

```powershell
git pull
uv run python -m scripts.audit_phase19_market_evidence
uv run --with pytest==9.1.1 pytest tests/unit/test_phase19_market_evidence_audit.py
```

Both commands run offline. Findings have explicit `source`, `scope` and
`level` (`public_documented`, `user_observed_metadata`,
`missing_attestation`), never an inferred source-rights grant.

## 1. Selected official fixture: observed metadata, not live odds

Official Premier League match `2645278`: Chelsea (home) v Manchester
United (away), 2026-10-31 12:30 UTC.

The user's approved one-shot metadata check on 2026-10-28 reported:

| Source | Field | Value |
| --- | --- | --- |
| The Odds API | event ID | `6601f69175a02f03fb7065aacb538e01` |
| OddsPapi | fixtureId | `id1000001772221358` |
| OddsPapi | tournamentId | `17` |
| OddsPapi | participant1 | `38` Chelsea FC |
| OddsPapi | participant2 | `35` Manchester United |

The ordering is **ALIGNED with this official fixture**. This is useful
direct observation and supports a provisional source-ID association;
it is not a vendor assertion that `participant1Id` always denotes the
home club for *soccer*.

Primary official fixture:
[Premier League match 2645278](https://www.premierleague.com/en/match/2645278/chelsea-vs-manchester-united/info).

## 2. OddsPapi first/second participant versus soccer home/away

The official [GET fixtures](https://oddspapi.io/us/docs/get-fixtures)
and [GET fixture](https://oddspapi.io/us/docs/get-fixture) references
call `participant1Id` and `participant2Id` the **first** and **second**
participants. They do not explicitly promise that those IDs always
encode soccer home and away positions.

An [OddsPapi NFL article](https://oddspapi.io/blog/nfl-prediction-market-liquidity/)
**does** describe `participant1` as the home team in its NFL schedule.
That observation is sport-specific; projecting it onto soccer would be a
new unsupported assumption.

For soccer, OddsPapi's
[GET markets catalogue](https://oddspapi.io/us/docs/get-markets)
and [soccer grading article](https://oddspapi.io/blog/football-data-api-betting-predictions/)
document sport `10`, market `101` (`Full Time Result`, period
`fulltime`) with `101=1` (home), `102=X` (draw), `103=2` (away),
settled on 90 minutes + stoppage. These are **market outcome identities**,
not a proof of fixture participant1/2 ordering. `scores.periods.fulltime`
is also ordered by the fixture participants, so the score must not be
silently treated as home/away without orientation evidence.

**Decision:** the historical official aligned fixture is insufficient to
claim a general provider participant-slot contract. Require an explicit
vendor soccer field definition or a separately reviewed per-fixture
home/away attestation with independent source identity and no ambiguous
or reversed pairings before using 1X2 selections in live market books.

## 3. Pinnacle: public soccer rules, not a booked 1X2 market

Official
[Pinnacle betting rules](https://www.pinnacle.bet/en/future/betting-rules):

- Ordinary soccer **match markets** default to 90 minutes + injury or
  stoppage time, **excluding** extra time, penalties and golden goals,
  unless the market says otherwise.
- If a match is started but uncompleted beyond **12 hours** from kickoff,
  its uncompleted periods are generally void. Already completed periods
  normally retain action.
- If the **referee ends** the match after at least **85 minutes**,
  Pinnacle's soccer rule exceptionally gives all periods action.
  Do not treat every fixture interrupted after minute 85 as an ordinary
  full-time result; the referee/official result and market matter.
- Neutral venues and changes of venue have distinct rules; Pinnacle
  expressly cautions that listed home-first orientation is attempted,
  not guaranteed, and the official governing body's home designation
  can control settlement.
- Rules have a precedence order: specific market rules before sport
  rules before general rules.

These rules are more specific than an API's broad `h2h` or `Full Time
Result` title. They are **not** applied to Bet365, SBOBet or any other
bookmaker. Neither provider has returned a verified *Pinnacle quote*
for this fixture; hence no per-provider comparison or settlement
equivalence for a concrete pair of source markets has been proved.

The offline `review_bookmaker_soccer_1x2` helper classifies public
Pinnacle rules conservatively. It returns `settlement_approved=False`
for normal completion as well as abandonment, extra time, venue changes
and unknown cases: publishing rules is not binding an actual vendor quote
to an identical bookmaker and settlement contract. This is a deliberate
gate, not an assertion that Pinnacle rules are unknown.

## 4. Public terms / licence rights

- [The Odds API terms](https://the-odds-api.com/terms-and-conditions.html),
  **updated 31 August 2026**: explicitly allow indefinite retention,
  research, analytics, derived-value calculations, websites/mobile apps,
  dashboards and commercial UI subject to conditions; raw **standalone**
  odds feed resale/repackaging/redistribution is restricted. Verification
  with a bookmaker and compliance with local law remain the user's
  responsibility. **Public terms favorable to a local analysis tool do
  not authorize every account, bookmaker brand use or jurisdiction.**
- [OddsPapi terms](https://oddspapi.io/en/legal/terms): prohibit selling,
  repackaging or redistributing odds as a standalone data product, allow
  account revocation, and direct uncertain use cases to support. Unlike
  The Odds API, these terms do **not explicitly promise** the same
  general retention, commercial-derivative-dashboard or replay rights.
  Obtain **written scope clarification** for the actual account and
  intended local storage/replay/dashboard/commercial workflow before
  enabling raw captures or redistributing derived material.

**Decision:** `provider_data_rights_approved` remains false; it cannot
become true merely because a terms page was read. The detailed legal
assessment for Belgian operation and any bookmaker-facing display is
outside the scope of this engineering audit.

## 5. Release/no-spend gate for the observed fixture

| Gate | Evidence | Decision |
| --- | --- | --- |
| Official Chelsea home / Man United away, kickoff | official schedule and user-run metadata | **Observed** |
| Exact source fixture IDs | user-run metadata above | **Observed, not a canonical execution grant** |
| Soccer outcome IDs and 90-minute period | official OddsPapi docs | **Documented** |
| OddsPapi soccer fixture participant1/2 home/away contract | only first/second field definition; NFL example | **BLOCKED** |
| A *specific* Pinnacle 1X2 market offered on both APIs | no price/bookmaker-identity records | **BLOCKED** |
| Pinnacle ordinary and interrupted-game public rules | official Pinnacle rulebook | **Documented, market binding missing** |
| The Odds API generic UI/retention rights | official public terms | **Documented, subject to conditions** |
| OddsPapi account storage/replay/derived-dashboard rights | generic non-redistribution terms | **BLOCKED pending provider confirmation** |
| Production marketbook/arbitrage permission | missing role/market/right/freshness gates | **BLOCKED** |

`scripts.prepare_live_odds.ReadinessEvidence` continues to default
all four authorization prerequisites to false; this public audit does
**not** set them true or introduce an authorization override.

### Next useful action

1. **Obtain written OddsPapi clarification** for soccer participant1/2
   roles, market 101 identity across bookmakers and the subscribed
   account's local storage/replay/derived dashboard usage. Do not submit
   credentials or pay for API requests to ask this.
2. Independently verify bookmaker-specific 1X2 terms for a **concrete**
   market quote after approval, including postponement/abandonment,
   neutral venue, interruption and extra time. One published Pinnacle
   rulebook is not proof the same market is offered by both vendors.
3. **Proceed to Phase 20.1 (local read-only Python HTTP server) and
   Phase 20.2 (HTML/CSS/JS dashboard with clearly marked synthetic
   data)** while waiting for any external provider reply. The local
   dashboard requires no odds provider credit and must not pretend
   these Phase 19 blockers are closed.

For broader Phase 19 data/fixture context, see
[`phase-19-independent-fixture-evidence.md`](phase-19-independent-fixture-evidence.md).
