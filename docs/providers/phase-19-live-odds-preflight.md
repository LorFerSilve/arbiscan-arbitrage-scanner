# Phase 19 — controlled live-odds preflight

**Status:** implemented safety and quota preparation; **no live odds requested**.
**Quote/arbitrage authorization:** blocked pending independent evidence.

The seven previously reported EPL overlaps are *provisional* only. Neither
provider's full original fixture IDs were persisted by the discovery script,
and OddsPapi's `participant1/participant2` metadata has not been independently
verified as home/away for each event. A name/clock match is not that proof.

## What the new commands do

Run in `C:\Users\silve\Documents\Arbiscan`:

```powershell
git pull
uv run python -m scripts.prepare_live_odds
uv run --with pytest==9.1.1 pytest tests/unit/test_live_odds_preparation.py tests/unit/test_football_1x2_semantics.py tests/unit/test_phase19_canonical_event_validation.py
```

The first command (after pulling) **does not need keys or use the network**.
It enumerates unresolved evidence and the *maximum planned budget* for
one future event, not a claim that execution is currently authorized.

To inspect **only currently available quotas** using the local ignored `.env`:

```powershell
uv run --env-file .env python -m scripts.prepare_live_odds --check-quotas
```

This mode is confined by a transport firewall to exactly two unmetered calls:

- The Odds API: `GET https://api.the-odds-api.com/v4/sports` (free; reads quota response headers);
- OddsPapi: `GET https://api.oddspapi.io/v4/account` (unmetered; reads active subscription allowance).

**No `/events`, `/fixtures`, `/markets`, `/odds`, `/settlements`,
bookmaker data, raw payloads or prices are requested or saved.**
Both provider errors and quota failures are sanitized; keys never print.

## Exact reserve for a *future* one-fixture read-only sample

The proposed minimal sample uses at most:

| Provider | Necessary route | Credits / calls |
| --- | --- | --- |
| The Odds API | Free sports/events discovery | 0 odds credits |
| The Odds API | `/sports/soccer_epl/events/{eventId}/odds` with `regions=eu`, `markets=h2h` | At most 1 odds credit |
| OddsPapi | `/sports`, `/tournaments`, `/fixtures` to establish fresh discovery context | 3 billable requests |
| OddsPapi | `/markets` then `/odds?fixtureId={fixtureId}` | 2 billable requests |

The Odds API's cost depends on unique returned markets and selected regions
(one region × one market here). OddsPapi bills even when the response is an
error: *reserve every attempted call before execution* and never retry.
A previous discovery's three used requests are **not re-usable** in a fresh
adapter/process without its in-memory event context. Quota preflight requires
at least **1 remaining The Odds API credit and 5 OddsPapi requests**, but
adequate quota does not authorize using those credits.

Authoritative sources:
- [The Odds API V4 — event-odds usage costs](https://the-odds-api.com/liveapi/guides/v4/)
- [OddsPapi V4 — requests and quota](https://oddspapi.io/us/docs/requests-and-quota)

## Implemented transport safety boundary

`scripts.prepare_live_odds.QuoteProbeTransport` is an **uninvoked** future
request firewall, tested with synthetic transports:

- one exact HTTPS provider host, no URL query strings or fragment;
- **one** The Odds API event-ID-specific odds request, exactly `eu` and
  `h2h`, ISO, decimal, and a single regional charge;
- **one** OddsPapi `/markets` catalog lookup followed by **one**
  `/odds` for exactly the selected external fixture ID;
- market/region/fixture ID substitution, other endpoints (notably settlements),
  malformed IDs, extra rounds and retries are rejected before transport;
- failed/timeout calls consume the reserved request slot. Neither the
  guard nor the CLI creates normalised quotes or evaluates arbitrage.

**Important:** this firewall covers only the final quote-read phase. A future
runner must separately enforce the discovery-stage three-call budget, use the
adapter's in-memory discovered event context, and check the precise provider
rights. It must not assume discovery + quote calls are all allowed merely
because this transport exists.

## Mandatory evidence before any execution

1. Independently validate canonical identity for **one exact** fixture in both
   APIs (including current date/time, league, unique provider IDs and no
   duplicate pairings).
2. Verify OddsPapi participant1/2 relative to an authoritative home/away
   source for **that fixture**; a matching name order alone is not enough.
3. Obtain bookmaker- and region-specific 1X2 settlement terms covering
   90 minutes + stoppage time and postponement, abandonment, voids,
   extra time and nonstandard grading. Do not infer these from API market labels.
4. Verify provider licensing, storage/distribution rights and production
   restrictions (OddsPapi remains production-blocked).
5. Check remaining quota and independently authorize one one-shot *read-only*
   sample with explicit credit caps. Compare quote semantics locally before
   allowing any canonical market-book or arbitrage calculation.

`ReadinessEvidence` defaults all approvals to **false**. This phase does not
accept a CLI flag that overrides those gates or lets paid routes through.
An explicit, separately reviewed future implementation is required to use
the quote transport.
