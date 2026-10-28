# Phase 20.1 — Local HTTP API (synthetic-first)

**Status:** Implemented when this PR is merged. This milestone provides an
HTTP transport for the existing Phase 13 Python `ArbiScanApi` contracts;
**it is not yet the interactive web frontend**. The browser UI is Phase 20.2.

There are no new runtime dependencies. The server uses Python 3.13's
standard-library `ThreadingHTTPServer`. Provider ingestion, actual bookmaker
odds, historical persistence, bet placement, and live scanning are all
deliberately **unavailable** through this local demonstration server.

**Phase 20.2 follow-up:** the HTML/CSS/JavaScript browser UI is now
served at `/` instead of the Phase 20.1 JSON landing document.
The GET JSON API routes remain under `/api/v1`; the root HTML
has `script-src 'self'`, `style-src 'self'` and `connect-src 'self'`
CSP directives and the server exposes only
`/assets/styles.css` and `/assets/app.js` as static assets.
See [the browser-dashboard guide](phase-20-browser-dashboard.md).

## Start on Windows PowerShell

Run in the Arbiscan project root:

```powershell
git pull
uv run python -m scripts.serve_dashboard_api
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).
The default is **empty mode**, so there are no fake odds or simulated
opportunities shown unless explicitly requested. All readiness/approval
gates still say false.

To inspect **clearly labeled synthetic fixtures** (imaginary teams,
fictional providers and future placeholder timestamps), stop the server
with Ctrl+C and start:

```powershell
uv run python -m scripts.serve_dashboard_api --demo
```

Custom port (no public bind option):

```powershell
uv run python -m scripts.serve_dashboard_api --demo --port 8010
```

The web server binds only to `127.0.0.1`, never
`0.0.0.0`/LAN/Public, and contains **no provider API keys**.
There are no API requests to The Odds API, OddsPapi or bookmakers.
Refreshing browser tabs costs **zero odds credits**.

## Read-only endpoints

Every public endpoint is versioned under `/api/v1` and returns JSON.
The `GET /` index currently returns API entry-point JSON and notes that
Phase 20.2 will add the full HTML/CSS/JavaScript interface.

| Endpoint | Existing Python API method / use |
| --- | --- |
| `GET /api/v1/health` | `ArbiScanApi.health` |
| `GET /api/v1/ready` and `/readiness` | `ArbiScanApi.readiness` |
| `GET /api/v1/providers/status` | `ArbiScanApi.providers` |
| `GET /api/v1/sports` | `ArbiScanApi.sports` |
| `GET /api/v1/events` | `ArbiScanApi.events` |
| `GET /api/v1/odds` | `ArbiScanApi.odds` |
| `GET /api/v1/opportunities` | `ArbiScanApi.opportunities` |
| `GET /api/v1/opportunities/{opportunity_id}` | `ArbiScanApi.opportunity` |
| `GET /api/v1/configuration/status` | `ArbiScanApi.configuration` |
| `GET /api/v1/metrics` | `ArbiScanApi.metrics` |
| `GET /api/v1/runtime` | Explicit `data_mode`, no live provider/quotes, no provider calls on refresh |
| `GET /api/v1/openapi.json` | Versioned OpenAPI routes |

Collections support `offset` (0 to 1,000,000) and `limit` (1 to
200) and return `items`, `offset`, `limit`, `total` and `has_more`.

Supported extra filters:

- `events?sport=football&status=synthetic`
- `odds?event_id=synthetic-event-1&provider_id=synthetic-source-a`
- `opportunities?event_id=synthetic-event-1`

Unknown, repeated, malformed or too-long parameters fail with
`400 bad_request`. Missing detail IDs and unknown routes return
`404 not_found`. Errors use the existing `ApiError` code/message
contract and never expose stack traces.

## Honest demo-data and security boundary

- `GET /api/v1/runtime` always reports `data_mode` = `empty` or
  `synthetic`, `live_quote_authorized: false`,
  `live_provider_ingestion: false` and `provider_calls_on_refresh: 0`.
- Every HTTP response includes `X-Arbiscan-Data-Mode`; no real-mode switch
  is available in the Phase 20.1 CLI.
- Synthetic events and quotes have names/IDs prefixed `synthetic-`,
  use imaginary teams in the `Synthetic Test League` and `status=synthetic`.
  Both demo provider statuses report `available=false`.
- API readiness is false, and `active_quotes` and
  `actionable_opportunities` metrics are **zero**. The synthetic
  opportunity detail has `evidence_available=false`. Demo prices and
  ROI are deterministic teaching fixtures, not bettable predictions.
- DNS-rebinding protection validates `Host` and browser `Origin` to
  the current local port. Cross-origin access is not enabled.
  Non-GET methods return `405`. Security headers disable caching,
  sniffing and cross-origin resource use.
- URL paths, pagination and filters are validated before calling the
  existing Phase 13 API. Read responses are dataclasses converted to
  JSON without including provider credentials or raw provider payloads.
- This is a development loopback service, **not** a production-hardened
  network server. Phase 21 covers deployment authentication, rate limits
  and a formal threat model.

## Tests

```powershell
uv run --with pytest==9.1.1 pytest tests/integration/test_phase20_local_http.py
uv run --with pytest==9.1.1 pytest
```

The HTTP integration suite uses an ephemeral **loopback-only test port**
and synthetic sources; it verifies method/path/query hardening,
pagination and filters, strict Host/Origin enforcement, explicit demo
marking, error sanitization, OpenAPI and repeated refreshes with a
provider transport mocked to raise on any external request.

## Next step: Phase 20.2

Build the responsive browser UI in HTML/CSS/vanilla JS against these
read-only routes. Add status/health indicators, event and provider lists,
searchable arbitrage tables, detailed opportunity/provenance displays,
empty/blocked states, and clearly visible synthetic-vs-live labels.
The browser must never call a provider API itself.

**Phase 19 live-odds blockers remain active:** OddsPapi soccer participant
role guarantee, source-specific 1X2 settlement/void equivalence, account
licensing/data-use authorization, and later real-data freshness/scale
validation. A working local HTTP API does **not** authorize any live
quotes or automated wagering.
