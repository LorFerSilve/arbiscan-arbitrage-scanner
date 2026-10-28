# ArbiScan Arbitrage Scanner

ArbiScan is a multi-bookmaker sports-odds aggregation and arbitrage-detection engine. The product boundary is intentionally scanner-only: it identifies and reports semantically valid opportunities but does not place bets automatically.

## Current status

Phases 0 through 18 of [`roadmap.md`](roadmap.md) are technically implemented
and merged to `main`. **Phase 19 — performance and scalability engineering — is
in progress, not complete.**

Phase 19 has reproducible synthetic benchmarks for detection, matching, provider
polling, multi-source consolidation, SQLite persistence and historical replay.
Profiling-driven indexing, matching-cache, batch-persistence and diagnostic
improvements have landed. PRs #70–#72 validated an eight-step fixture-backed
two-provider replay for partial coverage, expiry, late revisions, skew and recovery.
Those repeated polls are **simulated mutations of retained fixtures**, not
captured real sequential traffic or evidence of production latency. PRs #83–#87
then added safe official-football fixture matching and 1X2 market semantics,
cost-bounded discovery/preflight and a read-only observation of the actual
Chelsea–Manchester United provider fixture identifiers on 2026-10-28.
Provider participant-slot semantics, bookmaker-specific settlement and
account/deployment data-rights **remain unapproved**; no quotes have been
authorized for that match.

The implemented core includes:

- provider-neutral canonical event/market/selection/quote models;
- deterministic Decimal-based arbitrage mathematics and stake allocation;
- strict async provider adapters with two real transport schemas;
- semantic normalization and cross-provider event matching;
- multi-source price-origin provenance and same-bookmaker consolidation;
- canonical best-price market books;
- realtime ingestion, freshness/stale control, rate-limit handling, and provider isolation;
- persistence/audit evidence and opportunity reconstruction;
- opportunity lifecycle/actionability revalidation;
- transport-neutral service/API contracts;
- system/provider observability;
- read-only dashboard projection and alert deduplication;
- advanced football totals/handicaps/BTTS/DNB, indexed tennis set winners, and
  full-event basketball half-point spreads/totals;
- canonical motorsport race/qualifying/session identity with race-winner, podium, and
  H2H completeness gates, while runtime F1 evaluation remains intentionally disabled;
- generalized tournament/championship outright candidate completeness plus an explicit
  settlement-safety profile for deciding when generic N-outcome math is sufficient;
- a separate exchange settlement path with explicit BACK/LAY identity, lay liability,
  matched-liquidity limits, commission scope, and net-market commission;
- deterministic historical replay over canonical quote corpora, including opportunity
  duration, latency sensitivity, stale-data counterfactuals, provider comparisons,
  matching precision/recall, and theoretical-versus-actionable analysis.

The project remains development software. OddsPapi is technically integrated but
remains blocked from production activation pending the documented provider-rights
clarifications. Phase 19 exit criteria are not met without permissioned real-world
multi-poll validation and representative deployment-load measurements.

## Planned Phase 20 — Local Web Dashboard MVP

The [roadmap](roadmap.md) now includes **Phase 20: Web Dashboard MVP**, after
the immediate Phase 19 market-identity, bookmaker-settlement and provider-rights
review. This is a **planned** local-only browser app, not a feature currently
available to launch.

It will reuse the existing Phase 13 Python API service and Phase 15 read-only
dashboard models, filtering, HTML rendering and alerts. The first deliverable
uses **deterministic synthetic data**, HTML/CSS/vanilla JavaScript, and a
small Python HTTP adapter; it requires no odds credentials or paid API
calls. It will show scanner/provider status, events, opportunity filters,
exact source attribution, quote freshness, ROI, stakes, payout, assumptions
and blocked/stale states. Later live-data integration remains explicitly
gated on Phase 19 provider, market, settlement, rights and freshness evidence.

The prior security hardening, packaging and production-release phases
have been preserved as **Phases 21, 22 and 23**, respectively. See the
[Phase 20 specification](docs/product/phase-20-web-dashboard-mvp.md).
**The immediate next task remains Phase 19 public/offline evidence review;**
no additional metered API calls are needed for roadmap planning.

### Phase 20.1: local read-only HTTP API (implemented)

The first Phase 20 milestone exposes the existing Python API contracts as
a **loopback-only JSON server**, with no provider requests, bookmaker keys,
live-odds authorization, trading or persistence. It is **not yet the
interactive browser UI**, which is Phase 20.2.

```powershell
uv run python -m scripts.serve_dashboard_api
# Optional synthetic demonstration with clearly fictional events/quotes:
uv run python -m scripts.serve_dashboard_api --demo
```

Open `http://127.0.0.1:8000/` for the local API landing JSON, or
`http://127.0.0.1:8000/api/v1/runtime` to verify the explicit data mode.
All endpoints are under `/api/v1`; the default is an **empty** source,
while `--demo` opts into synthetic fixtures. Browser refresh spends
**zero** API credits. No public/LAN bind is supported.

See [Phase 20.1 routes, security and local tests](docs/development/phase-20-local-http-api.md).
The next coding milestone is **Phase 20.2: the actual interactive web UI**.

### Phase 20.2: interactive local web dashboard

A **responsive HTML/CSS/vanilla JavaScript interface** now sits on the
Phase 20.1 loopback Python API. Start it with:

```powershell
uv run python -m scripts.serve_dashboard_api --demo
```

Open **http://127.0.0.1:8000/**. You can review local scanner readiness,
fictional events/quotes, provider status, theoretical ROI, apply sport,
provider, search and ROI filters, and inspect each opportunity's quote
origin. Use the same command *without* `--demo` for an intentionally empty
dashboard. All demos are visibly synthetic and **not executable**;
the UI never calls OddsPapi or The Odds API.

**No investment/stake plan is invented.** The current Phase 13
opportunity-detail API does not yet supply a verified allocation or
post-rounding payout. The UI transparently shows that such fields are
unavailable. Phase 20.3 will add enhanced end-to-end UI acceptance,
and a backend-first stake projection where justified.

See [Phase 20.2 launch and UI security](docs/development/phase-20-browser-dashboard.md).

## Current market scope

Enabled advanced semantics remain intentionally narrow:

1. football pre-match regulation winner, push-free half-goal totals/handicaps, BTTS,
   and settlement-aware Draw No Bet;
2. tennis pre-match two-way match winner plus documented Set 1 / Set 2 winner;
3. basketball full-event half-point totals and spreads, with regulation/sub-period,
   integer/quarter-line, alternate, and live variants fail-closed;
4. motorsport/F1 canonical winner/podium/H2H identity is modeled, but all such
   markets remain runtime-disabled until provider and DNS/DNF/disqualification/
   dead-heat settlement equivalence is proven;
5. broader tournament/championship outright identity now requires a complete,
   homogeneous candidate set and explicit settlement-safety evidence; runtime support
   remains closed until a provider path proves that evidence;
6. exchange BACK/LAY payout semantics are modeled separately from bookmaker quotes,
   including lay liability, visible matched liquidity and commission on positive net
   exchange-market winnings. No live exchange transport is enabled yet.

## Next Phase 19 gate

1. Confirm each provider permits the required local capture, retention and offline
   replay. Do not collect or commit payloads where permission is unclear.
2. Obtain **authorized, time-ordered observations from both sources for matching
   events**, covering price changes, outcome loss, source skew, outages and recovery.
   Keep raw captures and credentials outside the repository.
3. Validate matching and normalization, then freshness, consolidation and
   fail-closed book construction against those sequences. Record only permitted,
   non-sensitive aggregate results and reproducible semantic digests.
4. After correctness passes, profile on the intended deployment hardware, establish
   measured latency/throughput targets, and recheck any optimization for parity.

See [the Phase 19 baseline](docs/development/phase-19-performance-baseline.md)
for existing measurements, limitations and commands. No real-capture data is yet
available in the repository.

## Free-tier quota preflight (no billable odds calls)

Before any authorized live-data validation, set `THE_ODDS_API_KEY` and
`ODDSPAPI_API_KEY` in the local ignored `.env` file, then run:

```text
uv run --env-file .env python -m scripts.check_provider_quotas
```

This intentionally makes only **two metadata calls** via the existing
production adapters: The Odds API `/sports` (no odds quota charge) and
OddsPapi `/account` (unmetered). It prints each remaining-credit count
when available, but never prints API keys, saves responses, or requests
events/odds. Do **not** include the `.env` file or captured account
responses in issues or pull requests.

For the first live test, use a manual budget of at most **10 credits per
provider** and keep automated polling disabled. This is a chosen project
cap, not a vendor guarantee or a built-in enforcement mechanism. The
Odds API's default `eu` region and `h2h` market normally cost one
credit per returned odds market; **OddsPapi catalog/discovery calls also
consume one request each**, so count every request, not just odds polls.
Do not retain restricted OddsPapi market payloads until applicable
data-retention/replay rights are confirmed (see [issue #76](https://github.com/LorFerSilve/arbiscan-arbitrage-scanner/issues/76)).

## One-shot football event overlap discovery

After confirming remaining quota with the preflight, inspect the first live
English Premier League event overlap **without fetching odds**:

```text
uv run --env-file .env python -m scripts.discover_live_overlap
uv run --env-file .env python -m scripts.discover_live_overlap --execute --odds-only
uv run --env-file .env python -m scripts.discover_live_overlap --execute
```

The first command prints the request plan and performs **zero HTTP calls**.
The second command verifies EPL fixture discovery through **only The Odds API**
(the provider documents `/sports` and `/sports/{sport}/events` as zero-usage
metadata endpoints), even if OddsPapi credentials are configured. This makes
The Odds API HTTP failures diagnosable **without spending any OddsPapi credits**.
If the free-only run returned `The Odds API discover_events (upstream; HTTP 422)`,
the Oct 2026 Phase-19 version of the script had been transmitting subsecond
`commenceTimeFrom` / `commenceTimeTo` values. The free events endpoint
documents timestamp examples with second precision. The one-shot script now
fetches unfiltered league events (only `dateFormat=iso`) and restricts the
results to the next seven days **in memory**, preserving the discovery window
without requesting odds or saving provider data. The date-parameter hypothesis
has not yet been verified against the live endpoint; rerun only the free-only
command first. The shared provider adapter retains its stricter original
query behavior elsewhere.

The final command should run **only after** The Odds API check succeeds. It repeats
the free source discovery first, then asks OddsPapi for its EPL competition and
fixtures, up to three paid metadata requests. All calls use the existing
adapters; no odds prices are fetched. Provider errors now identify the source
and a sanitized HTTP status when available; response bodies, URLs containing
keys and credentials are not printed.

If discovery stops with `discover_competitions (malformed_response)`
after exactly one OddsPapi billable call, **do not rerun the full
discovery**. Instead use the narrow, one-request schema diagnostic:

```text
uv run --env-file .env python -m scripts.diagnose_oddspapi_sports
```

This checks the free `/account` quota first, then permits **at most
one billable `/sports` request** and never calls `/tournaments`, fixtures
or odds. It reports the precise sanitized parser field path (not raw
provider JSON or secrets), or that football sport resolution succeeded.
Review this local diagnostic before changing provider parsing rules.
The first live failure did not retain a response, so its exact cause
cannot be reconstructed without another permitted observation.

A transport-level endpoint allowlist enforces **zero billable The Odds API
requests** and at most **three OddsPapi requests** (`/sports`,
`/tournaments`, `/fixtures`) even on failure. No odds endpoint is permitted,
there is no retry loop, and no provider payload is stored. If a competition is
missing/ambiguous or two fixtures disagree, the command stops or produces no
candidate rather than guessing. One-to-one candidates are **not canonical
event matching proof**; source event identity and settlement semantics must
still be verified before a later controlled odds comparison.

### Phase 19: audited soccer participant roles, bookmaker settlement and rights

The no-network audit now distinguishes **observed fixture ordering**, public
football `1/X/2` market definitions, published Pinnacle 90-minute and
abandonment rules, and public data-licence terms from **actual permissions
to process live quotes**:

```powershell
uv run python -m scripts.audit_phase19_market_evidence
uv run --with pytest==9.1.1 pytest tests/unit/test_phase19_market_evidence_audit.py
```

No keys, network, API credits, odds or files. The review confirms that
OddsPapi's explicit `participant1=home` example is **NFL-specific**,
not a soccer-wide provider guarantee. Actual bookmaker-market equivalence,
the subscribed OddsPapi account's storage/replay/dashboard rights and
live quote eligibility remain blocked.

See the [public evidence and next-action matrix](docs/providers/phase-19-market-role-settlement-rights-audit.md).
The **local synthetic Phase 20 web dashboard** can be built without
waiting for provider replies; live-data integration remains gated.

### Phase 19: source-specific fixture IDs (metadata only)

For the official Chelsea v Manchester United fixture on
**31 October 2026**, a one-shot optional diagnostic now reports the
actual The Odds API event ID and OddsPapi fixture/participant IDs only
when its strict home/away reference and Phase-7/8 matching succeed.

```powershell
uv run --env-file .env python -m scripts.discover_live_overlap --execute --verify-official
```

The diagnostic costs **up to 3 OddsPapi billable discovery calls**,
uses **0 odds credits**, and requires the user's own local API keys.
It first requires a unique, safe, official-reference match in the free
The Odds API events feed; otherwise it does not contact OddsPapi.
Observed participant order does **not** certify OddsPapi home/away
slot semantics. It does not approve any quote or arbitrage evaluation.
See [the exact verification scope and offline tests](docs/providers/phase-19-independent-fixture-evidence.md).

### Phase 19: independent official EPL fixture evidence

The independently published Chelsea v Manchester United fixture for
**31 October 2026, 12:30 UTC** has been cross-checked against the
Premier League and both clubs. The official match ID is **2645278**.
To see the no-network reference report:

```powershell
uv run python -m scripts.audit_official_fixture
```

The existing EPL discovery code can compare a Phase-7/8 provisional
pair to this official home/away and kickoff reference, and report whether
OddsPapi participant order appears aligned/reversed. However, the official
match ID is **not** either provider's ID. The orientation of OddsPapi's
participant1/2 fields, underlying bookmaker settlement terms, and data-use
rights are still **unverified**. No odds or quote authorization is enabled.
See [official event, Pinnacle and API rights evidence](docs/providers/phase-19-independent-fixture-evidence.md).

### Phase 19: controlled live-odds preflight (no paid requests)

Before any priced source snapshot, run the new **offline** readiness report:

```powershell
uv run python -m scripts.prepare_live_odds
```

To check only the free/unmetered provider quota endpoints (no odds credits,
no OddsPapi billable requests), with local keys in `.env`:

```powershell
uv run --env-file .env python -m scripts.prepare_live_odds --check-quotas
```

The future *single-fixture* quote probe is limited to one The Odds API
`eu/h2h` event-odds call (at most one usage credit), plus a maximum
of five OddsPapi billable calls for **fresh** event discovery and
catalog+odds retrieval. These are **planned limits, not incurred costs**.
The new strict future quote transport rejects other hosts/routes,
market/region expansion, repeat calls and different fixture IDs.
It is not invoked by either command. Until home/away orientation,
bookmaker-specific settlement rules and provider rights are verified,
**quote approval remains blocked** and arbitrage evaluation is disabled.
See [the detailed preflight protocol](docs/providers/phase-19-live-odds-preflight.md).

### Phase 19: football 1X2 market-side and settlement contract

The offline Phase-19 rules now explicitly recognize OddsPapi **soccer market
101**, outcome **101=home**, **102=draw**, **103=away**, and
`fulltime` as the **regulation-time** result. All other 1X2 market variants
fail closed unless separately approved. The code can check 90-minute score
consistency against a complete WIN/LOSE settlement triplet, but does not
make any provider requests to do so. The OddsPapi fixture
`participant1/participant2` fields are not treated as an independently
verified home/away ordering, nor as proof of any bookmaker's void rules.
**No automatic odds comparison or quote authorization is enabled.**
Read [the Phase-19 1X2 contract](docs/markets/football-1x2-identity-settlement.md).

To test the source contract offline (without installing pytest permanently):

```text
uv run --with pytest==9.1.1 pytest tests/unit/test_football_1x2_semantics.py tests/unit/test_phase19_canonical_event_validation.py
```

### Phase 19: read-only canonical identity review

After the discovery candidate lines, the same bounded script now performs a
**local-only**, read-only identity review. It passes provider fixture data
through Phase-7 explicit competition/team aliases and Phase-8 canonical event
matching with a temporary reference catalog anchored to The Odds API. The
explicit Phase-19 English Premier League team vocabulary covers only the 14
club names from the first successful seven-pair discovery; unknown names,
women/youth/reserve team lookalikes, wrong league regions, duplicate
identities, conflicts and ambiguous fixtures fail closed. The review uses
a strict five-minute clock difference even though general Phase-8 defaults
are wider. No live API calls are added.

**Important:** the temporary reference catalog is NOT an independently
verified canonical registry. The OddsPapi fixture documentation calls
the two sides `participant1` and `participant2`, without promising
that they are home and away, in that order. Therefore an identity match
is reported only as **provisional**; even a matching name order is not
proof of home/away semantics. The tool reports **zero quote-eligible
canonical matches** and never yields canonical quote ID hooks.
Market-period and settlement equivalence have not yet been verified.
The current alias review is an offline diagnostic, not authorization to
fetch odds or calculate arbitrage.

The matched-event check intentionally recognizes only exact case-insensitive
team names after stripping a trailing FC/CF suffix. Names with other aliases
may not match. Do not weaken this guard automatically: review the affected
provider labels first. Keep any console output with provider-specific event
data local and do not paste raw payloads, IDs or API keys into public issues.

## Development

The project uses Python 3.13, uv, Ruff, mypy, pytest, pre-commit, and GitHub Actions. See [`docs/development/setup.md`](docs/development/setup.md) for the reproducible setup and quality commands.

The full local/CI quality gate is:

```text
uv run python scripts/quality.py --all
```

CI uses deterministic fixtures and does not require live provider credentials.

## Documentation

- Development status and phase completion records: [`docs/development/`](docs/development/)
- Product requirements: [`docs/product/requirements.md`](docs/product/requirements.md)
- Non-goals: [`docs/product/non-goals.md`](docs/product/non-goals.md)
- Risk register: [`docs/product/risk-register.md`](docs/product/risk-register.md)
- Provider integration checklist: [`docs/product/provider-integration-checklist.md`](docs/product/provider-integration-checklist.md)
- The Odds API integration: [`docs/providers/the-odds-api.md`](docs/providers/the-odds-api.md)
- Phase 16 readiness: [`docs/providers/phase-16-readiness.md`](docs/providers/phase-16-readiness.md)
- Phase 16.1 provider selection: [`docs/providers/phase-16.1-provider-selection.md`](docs/providers/phase-16.1-provider-selection.md)
- OddsPapi onboarding record: [`docs/providers/oddspapi.md`](docs/providers/oddspapi.md)
- Dashboard/alert boundary: [`docs/product/dashboard-and-alerts.md`](docs/product/dashboard-and-alerts.md)
- Historical replay/backtesting: [`docs/analysis/historical-replay-and-backtesting.md`](docs/analysis/historical-replay-and-backtesting.md)
- Architecture decisions: [`docs/adr/`](docs/adr/)
- Development roadmap: [`roadmap.md`](roadmap.md)
