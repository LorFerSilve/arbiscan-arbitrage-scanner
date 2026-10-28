# Phase 19 — Independent event reference and provider-rights review

Reviewed: **28 October 2026**. This is an evidence record, not a live quote
or bookmaker approval, and it contains **no API odds responses** or secrets.

## Selected fixture — Chelsea vs Manchester United

| Field | Independently documented |
| --- | --- |
| Official competition | 2026/27 Premier League, matchweek 9 |
| Home team | Chelsea FC, men's first team |
| Away team | Manchester United FC, men's first team |
| Kickoff | **31 October 2026, 12:30 UTC / 13:30 Europe/Brussels** |
| Stadium | Stamford Bridge, London |
| Official Premier League ID | **2645278** |

Primary sources:

- [Premier League — official match 2645278](https://www.premierleague.com/en/match/2645278/chelsea-vs-manchester-united/info)
- [Chelsea FC — men's 2026/27 fixture list](https://www.chelseafc.com/en/news/article/chelseas-2026-27-premier-league-fixtures-announced)
- [Manchester United FC — October 2026 Premier League fixtures](https://www.manutd.com/en/matches/mens-team/fixtures?competition=premier-league&month=2026-10)
- [Premier League — all 380 fixtures](https://www.premierleague.com/en/news/4675097/all-380-fixtures-for-season-2026-27)

Dates/venues can be rescheduled; a future runtime match must check the
current official listing rather than assuming this historical observation is
permanently accurate.

## What the implementation verifies

`python -m scripts.audit_official_fixture` displays the immutable reviewed
source reference **without internet access or credentials**.
`audit_official_chelsea_manchester_united(review)` accepts an existing
Phase-7/8 `CanonicalReview` and checks:

- exactly one provisional pair refers to Chelsea **at home** against
  Manchester United **away**;
- The Odds API's event has explicit home/away roles and the `soccer_epl`
  competition key;
- both sources' kickoff times are within five minutes of the independent
  12:30 UTC reference;
- OddsPapi's two participant names are identical to the official home/away
  identities (allowing only a trailing ` FC`), in aligned or reversed order;
- OddsPapi's roles are structurally `participant1` and `participant2`
  and its status indicates pre-match.

The result distinguishes `ALIGNED`, `REVERSED` and `CONFLICT`.
**ALIGNED does not mean verified OddsPapi home/away roles.** The official
Premier League match ID **2645278 is not an OddsPapi or The Odds API fixture
ID**. Neither provider's exact opaque fixture ID was included in the
user's original seven-line live summary, and no network request is made
to recover it. The implementation cannot manufacture this ID mapping.

Both `can_fetch_quotes` and `provider_ids_independently_verified`
deliberately remain `False`. This module does not create
`MatchedCanonicalIdHooks` or enable arbitrage calculations.

The existing quota-bounded discovery script will show the independent
reference comparison if the user *later* chooses to rerun discovery. **Do not
rerun paid discovery simply to generate this line.** The offline command is
free and sufficient for the public independent-fixture audit.

## Bookmaker example: Pinnacle, not yet connected to a live provider quote

[Pinnacle's published betting rules](https://www.pinnacle.bet/en/future/betting-rules),
reviewed on 28 October 2026, state:

1. Soccer match markets normally settle on the **90 minutes plus injury/
   stoppage time**; extra time, penalties and golden goals are excluded,
   unless the specific market says otherwise.
2. Uncompleted soccer periods are generally void if the match is not
   completed within **12 hours** of kickoff. Completed periods retain action.
3. One important exception: if the referee ends a match after at least
   **85 minutes**, its rule treats all periods as having action.
4. The general rules separately cover matches that never start (12 hours),
   venue changes, and an event interrupted for a longer time. Specific
   soccer/market rules prevail where applicable.
5. Pinnacle's rules explicitly acknowledge that posted date/time and its
   third-party live scoreboard may be inaccurate.

**This is evidence of Pinnacle's public rules only.** It is not proof that
either paid API will return a Pinnacle 1X2 quote for the selected event,
that the bookmaker's offering is legal in the user's jurisdiction, or that
another bookmaker applies these same rules. A 90-minute result and the
special 85-minute case must not be conflated with a universal
`WIN/LOSE` result for every abandoned fixture.

A future quote pipeline must bind the underlying bookmaker slug and its
specific 1X2 market to reviewed terms for the relevant jurisdiction.
The currently available 1X2 semantic validator addresses *normal*
full-time scores; it is **not** a comprehensive void/abandonment engine.

## Current official API licence terms

[The Odds API's terms (updated 31 August 2026)](https://the-odds-api.com/terms-and-conditions.html)
explicitly permit storing their data, using it in analytical dashboards,
calculating derived values, and displaying it in user-facing applications,
including commercial ones under conditions. They prohibit reselling or
redistributing a raw standalone odds feed.

[OddsPapi's terms](https://oddspapi.io/en/legal/terms) prohibit reselling,
repackaging or redistributing their data as a standalone product. They tell
users to contact OddsPapi if a specific usage model is uncertain.

**Do not equate reviewing public terms with account-specific authorization.**
Whether the current subscription, jurisdiction, storage practices and
proposed deployment/commercial use are permitted is not verified here.
No terms are used to auto-set `provider_data_rights_approved=True`.
The independent fixture evidence likewise does not override the other
three `ReadinessEvidence` blockers.

## Remaining proof required before a paid live 1X2 sample

1. Obtain the exact **current** The Odds API event ID and OddsPapi fixture
   ID, matched to the same official Premier League fixture and verified
   with all identity, kickoff and participant-order constraints.
2. Independently establish the **meaning** of OddsPapi participant1/2
   home/away slots for that fixture, rather than just their presentation
   order relative to another provider's source.
3. Match a **specific** bookmaker and its regulation-time 1X2 market;
   check market rules, void/refund/abandonment/venue handling for the
   account/jurisdiction; never generalize Pinnacle rules to others.
4. Resolve provider account terms, local law and storage/display rights.
5. Recheck nonbillable quotas before **separately approved**, capped paid
   requests. The permitted future probe and quota budget are documented
   in [phase-19-live-odds-preflight.md](phase-19-live-odds-preflight.md).

This evidence audit **uses zero metered or unmetered API requests**.
