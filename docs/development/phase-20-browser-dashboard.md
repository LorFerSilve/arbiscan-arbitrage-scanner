# Phase 20.2 — Interactive local web dashboard

**Status:** Implemented in PR #91 (after merge).
**Scope:** a usable local-only HTML/CSS/vanilla JavaScript browser dashboard,
driven exclusively by the **existing** Phase 13 Python API served by Phase 20.1.

The browser performs **no** direct calls to OddsPapi, The Odds API, bookmaker
sites, payment providers or external CDNs. The browser may only read the
loopback server's `/api/v1` JSON routes. There are no new Python or JS package
dependencies, login forms, paid odds calls, bet placement or persistence.

## Launch in Windows PowerShell

In the project root:

```powershell
git pull
uv run python -m scripts.serve_dashboard_api --demo
```

Open **http://127.0.0.1:8000/** in a browser. `Ctrl+C` shuts down the
server. The `--demo` flag opts into a **fictional** game, quotes and a
theoretical ROI. All demo provider statuses are inactive; scanner
readiness and real actionability are false. The dashboard title and
every relevant data status say synthetic/demo; the actual Chelsea v
Manchester United provider metadata is **not** used as a betting signal.

To inspect empty/blocked states rather than the fictional dataset:

```powershell
uv run python -m scripts.serve_dashboard_api
```

The server continues to bind **only** to `127.0.0.1`. Opening the site
from another machine requires a future, security-reviewed deployment.
A different loopback port is supported with `--port 8010`.

## Browser features

- Responsive workspace navigation, status/health dashboard and four
  summary cards (approved live opportunities, demonstrative opportunities,
  events and provider count).
- Full search by fixture/competition/market/ID; sport, provider and
  minimum theoretical ROI filters; sort by ROI, detected date or name.
- Opportunity table with explicit **NOT EXECUTABLE** and **DEMO** context.
  Selecting a row opens a keyboard-accessible side drawer with the
  relevant backend market ID, raw implied sum, theoretical ROI, timestamp,
  selections, provider attributions, decimal prices and evidence status.
- Provider health and upcoming fixture summaries, empty-data and
  API-unavailable/error states. Refresh calls **only** the localhost
  application API and **never** triggers bookmaker/odds discovery.
- Existing `/api/v1` API routes remain unchanged; the static assets
  are allowlisted as `/` (HTML), `/assets/styles.css` and
  `/assets/app.js`. The app is served from the **same origin** as API.
- No script or stylesheet pulled from a third party; no `innerHTML`
  with server data. CSS supports narrow/mobile viewports, visible keyboard
  focus and reduced-motion preferences.

## Calculation and evidence safety

- ROI is the backend's precomputed `guaranteed_profit_rate` **formatted
  as a percentage**; JavaScript is **not** an arbitrage/stake calculator.
  The synthetic opportunity is not bettable, even if its theoretical
  rate is positive.
- The Phase 13 opportunity-detail contract currently gives quote IDs and
  evidence availability but **no verified stake plan**, stake per leg,
  payout or guaranteed post-rounding profit. The drawer explicitly
  says **Inzetplan: Niet beschikbaar**, rather than guessing or
  recomputing these figures in JavaScript. Showing actual allocated
  stakes and guaranteed payout is a later backend projection integration
  milestone, not a truthfulness concession.
- Quote dates from the synthetic sample are placeholders; the UI does not
  represent them as live or fresh data. The phase 19 source-role,
  settlement/void, licence and real-capture gates are unchanged.
- If the backend indicates live ingestion/quote authorization unexpectedly,
  unknown data mode, invalid data-mode headers, non-ready/ready mismatch
  or a failed refresh, the browser **hides cached market rows** instead
  of treating them as fresh or executable.
- `GET /api/v1/runtime` reports the true mode and
  `live_quote_authorized=false`, including in synthetic mode.
  `/api/v1/readiness` remains false.

## HTTP security

- Strict exact static asset allowlist, no dynamic arbitrary file reads.
  Path percent-encoding, traversal, unknown routes and asset query args
  cannot read other files.
- Same-origin `Content-Security-Policy` for HTML:
  `default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'`;
  no inline script/style, no cross-origin CORS.
- Strict localhost `Host`/`Origin` checks (Phase 20.1), 405 for writes,
  `Cache-Control: no-store`, `nosniff`, `X-Frame-Options: DENY`,
  a referrer policy and cross-origin resource protection.
- Browser actions are data reads or local filters, not provider
  commands or state-changing endpoints.

**Phase 20.3 update:** the detail drawer can now render a synthetic
stake projection **only** when the Python backend supplies an explicit
`synthetic=true` plan, matching expected quote IDs and odds. It
shows the model's stake per outcome, conservatively rounded expected
payout, total staked, minimum model payout and model profit with
assumptions. No live stake plan is ever inferred. Chromium E2E
coverage and Windows manual accessibility checks are documented in
[Phase 20.3 browser acceptance](phase-20-browser-acceptance.md).

## Tests and remaining work

```powershell
uv run --with pytest==9.1.1 pytest tests/integration/test_phase20_local_http.py
uv run --with pytest==9.1.1 pytest
```

Integration tests inspect actual HTML/CSS/JS HTTP responses, MIME types,
the CSP, blocked arbitrary asset paths/query strings and remote hosts,
empty/demo API behavior, controls, data safety, and zero outbound vendor
I/O. The existing Python quality gates (Ruff, mypy, pytest, security
audit, CodeQL) are still enforced.

**Next: Phase 20.3** — manual visual and accessible browser acceptance on
Windows/mobile dimensions, richer end-to-end UI interaction tests, and a
backend-provided `DashboardOpportunity` projection containing actual
engine-calculated stakes and provenance **when** a permissible synthetic
stake plan exists. Phase 20.4 (real scanner connection) still requires
the explicit Phase 19 vendor rights and settlement approvals.
