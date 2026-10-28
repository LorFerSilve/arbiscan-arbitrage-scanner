# Phase 19 — Provider attestation and settlement evidence packet

**As of 28 October 2026:** No billable or unmetered provider calls were
made for this update. Public documentation was rechecked independently.
The evidence pack is an **offline request/review aid**, not an odds probe,
bookmaker-approval service or substitute for external written replies.

## Newly identified soccer-specific role evidence

[OddsPapi's own 1 October 2026 soccer grading example](https://oddspapi.io/blog/football-data-api-betting-predictions/)
maps `participant1Score` to its local `home` variable and
`participant2Score` to `away` for a 250-fixture European football
analysis. It also uses `fulltime` for 90-minute results, distinguishes
`result` after extra time, and maps market `101` outcomes to 1/X/2.

This is **direct soccer-specific, public vendor evidence** and stronger
than the previously found NFL example. However, the canonical
[GET fixture](https://oddspapi.io/us/docs/get-fixture) and
[GET fixtures](https://oddspapi.io/us/docs/get-fixtures) field references
still explicitly define `participant1Id` and `participant2Id` as
the *first* and *second* participants, not as an unconditional soccer
home/away API invariant. OddsPapi's blog example cannot certify that
exceptions never occur (e.g. neutral venues, reversed records) or the
semantics of one actual bookmaker's marketed quote.

The specific observed fixture, Chelsea v Manchester United,
official Premier League match `2645278`, remains:
The Odds API event `6601f69175a02f03fb7065aacb538e01`;
OddsPapi `id1000001772221358`, participant1 Chelsea `38`,
participant2 Manchester United `35`. This is aligned for **one event**
only, not universal execution permission.

## Vendor correspondence to request (not sent)

Use OddsPapi's [official contact form](https://oddspapi.io/en/contact)
or the support channel shown in the
[official terms](https://oddspapi.io/en/legal/terms).
Send **no API keys, passwords or personal subscription tokens**.
Ask for a written, attributable response; avoid sending this chat's
internal file paths or stored credential files.

### A. OddsPapi — soccer participant roles and settlement identifiers

Subject: Clarification of V4 soccer participant ordering and full-time 1X2

Hello OddsPapi support,

We are integrating V4 soccer/football data into a local read-only
analysis dashboard. Your GET fixture(s) docs define
`participant1Id`/`participant2Id` as first/second participants,
while your 1 October 2026 football-grading article uses
`participant1Score` as home and `participant2Score` as away.

1. For `sportId=10` (soccer), are `participant1Id` and
   `participant2Id` **contractually** home and away respectively for
   **every** fixture? Please describe exceptions or changes for
   neutral venues, postponed/relocated events, corrections and any
   bookmaker-specific reversal.
2. For soccer `marketId=101` (`Full Time Result`, period
   `fulltime`), are outcome IDs `101/102/103` always home/draw/away
   and the contract always 90 minutes + stoppage, excluding extra
   time/penalties? Do different bookmakers or bet types use different
   rules despite sharing a label or market ID?
3. For a market returned via `/v4/odds`, which fields identify the
   **actual bookmaker**, its market/period contract, and any rulebook
   or void-condition override? We need to verify identical
   bookmaker/market semantics across two independent source feeds
   before comparing prices.

A short written clarification or link to a binding V4 field contract
would be appreciated.

### B. OddsPapi — actual subscription data rights

Subject: Written confirmation of local analysis, storage and dashboard use

Hello OddsPapi support,

Our intended use is a local, password-protected development machine
in **Belgium**. We plan to store timestamped bookmaker odds locally,
replay history for debugging/backtests and show bookmaker-attributed
data plus derived arbitrage/ROI calculations in our **own local
dashboard**. We do **not** resell or redistribute a standalone odds
feed, offer a third-party API or automate placing bets.

Please confirm in writing for our subscribed plan whether these uses
are allowed, any retention limits, required attribution, screenshot/
export restrictions, dashboard/replay constraints, permitted commercial
versus personal-use distinctions and geographic or bookmaker-specific
licensing restrictions. If account-level verification is needed,
please indicate a secure method that does not involve sharing API
keys in email.

We have read your public terms prohibiting standalone feed
redistribution; those terms do not explicitly settle every local
retention/replay/dashboard use case.

### C. Bookmaker / feed support — exact 1X2 void/settlement rules

For the **same specified bookmaker slug and market contract** returned
from *both* vendors, obtain or independently review the official
bookmaker's policy for:

- regulation time + stoppage, excluding extra time/penalties;
- abandonment, referee-ended >=85-minute cases if Pinnacle,
  late completion/void thresholds and postponed or rescheduled matches;
- neutral venues/relocation and governing body's home designation;
- market-specific exceptions overriding the general soccer rules;
- an exact example market identifier **from each feed** (no need to
  buy additional requests just to ask about documented semantics).

[Pinnacle's official soccer and general rules](https://www.pinnacle.bet/en/future/betting-rules)
are already reviewed. **Do not apply Pinnacle rules to any other
bookmaker**. Even for Pinnacle, a genuine cross-feed bookmaker-market
identity is not established by the published rulebook alone.

## Offline attestation record

This command has no external provider/network access:

```powershell
git pull
uv run python -m scripts.review_phase19_attestations
uv run python -m scripts.review_phase19_attestations --template
```

The first command reports three missing external attestations and all
four original Phase 19 quote-readiness blockers. `--template` prints a
minimal JSON skeleton; if desired, save it manually to a **local**
`phase19-response.json` in a secure location outside your repository.

Once real responses arrive, fill the skeleton with one metadata-only
record per gate. The records require:

- `gate`: `soccer_role_semantics`,
  `bookmaker_settlement`, or `oddspapi_data_rights`;
- `issuer`: `OddsPapi` for roles/rights, `Pinnacle` for
  the concrete Pinnacle settlement gate;
- `channel`: `vendor_support_reply` or
  `official_bookmaker_rules`;
- `received_on`, `reviewed_on`: dates in `YYYY-MM-DD`;
- `source_reference`: non-secret provider reply or document locator,
  `reviewer`: identity of the manual reviewer;
- role gate: `sport=soccer`, `fixture_field_meaning`,
  `home_away_exception_policy`, `applicability`;
- settlement gate: `bookmaker_slug=pinnacle`,
  `market_name=soccer_regulation_1x2`, `regulation_period`,
  `abandoned_match_policy`, `postponement_policy`,
  `neutral_venue_policy`, `cross_feed_market_evidence`;
- rights gate: `subscription_scope`, `storage_retention`,
  `local_replay`, `derived_dashboard`, `jurisdiction=Belgium`,
  `redistribution_limits`.

Then run locally:

```powershell
uv run python -m scripts.review_phase19_attestations --packet phase19-response.json
```

**Do not commit the vendor correspondence or account-specific terms to a
public repository.** This is a metadata-only file and the command
neither saves its content nor prints responses. There is a strict
32 KiB read cap, fixed gate list, forbidden unknown keys and no
credential fields. Arbitrary claims in a user-edited JSON file are
untrusted and **cannot prove an issuer's identity**: complete metadata
returns `READY_FOR_MANUAL_REVIEW`, **never APPROVED**.

## Exit criteria and next action

A third-party response may close a *documentation uncertainty* only
after checking its authenticity, effective date, sport, exact market,
subscription, bookmaker and territory. A verified role definition
does not automatically prove bookmaker-market settlement parity.

**No existing `ReadinessEvidence` flag is set by this tool. Quote
authorization remains blocked.** Once a genuine provider response
is received and assessed, implement the corresponding narrowly scoped
code contract/test and independently verify *a real bookmaker market
from each feed* under an explicitly approved, quota-limited test.
Only after that can a separate decision on quote observations and
Phase 20.4 integration be made.
