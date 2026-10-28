# Phase 20.3 — Browser acceptance and engine-owned demo staking

**Scope:** Offline/local-only acceptance of the Phase 20.2 web app and a
read-only **synthetic** stake projection from the existing Phase 3
arbitrage engine. Real odds and wagering remain blocked by Phase 19.

## What changed

- The synthetic football 1X2 odds now pass through the canonical
  `evaluate_market`, `build_opportunity` and `allocate_stakes` Python
  functions. No JS percentage/profit/stake business logic was added.
- `GET /api/v1/opportunities/{id}` gains a **backward-compatible optional**
  `stake_plan` field (null by default). The synthetic demo contains
  `currency`, `bankroll`, `total_staked`, `guaranteed_payout`,
  `guaranteed_profit`, per-leg `stake`, `expected_payout`,
  `decimal_price`, and conservative model assumptions.
- The browser detail panel displays these already-computed strings only
  after explicitly checking `synthetic=true`, the demo source mode,
  expected quote IDs/providers/prices and the absent external evidence.
  This is **not** a real usable/guaranteed bet and all amounts are
  labeled fictional model outputs.
- The fixed demo bankroll is **EUR 100.00**; stakes use the core's EUR 0.01 increments, payouts
  round down conservatively, and the combined stake cannot exceed
  bankroll. No trading fees, tax, bookmaker stake limits, void/abandonment
  difference or jurisdiction-specific constraints are assumed satisfied.
- The default mode without `--demo` remains empty; the demo
  remains inactive, `ready=false`, `evidence_available=false`,
  `actionable_opportunities=0` and no live-provider quotes.
- The static UI remains XSS-resistant by using DOM `textContent`,
  a tight CSP, no CDN requests and a 127.0.0.1-only HTTP listener.

## Test procedure

Unit tests and Python integration suite:

```powershell
uv run --with pytest==9.1.1 pytest tests/unit/test_phase20_stake_projection.py
uv run --with pytest==9.1.1 pytest tests/integration/test_phase20_local_http.py
uv run --with pytest==9.1.1 pytest
```

Actual Chromium browser acceptance (dev/test-only dependency, not an
ArbiScan runtime requirement):

```powershell
uv run --with playwright==1.56.0 python -m playwright install chromium
uv run --with playwright==1.56.0 python browser_e2e/acceptance.py
```

The `browser` job in GitHub CI installs pinned Chromium test dependencies
and runs this suite automatically. It covers:

- Desktop 1440x900 and mobile 390x844 viewport, no horizontal body overflow;
- visible demo/empty labels, zero actionable live opportunities;
- matching a fixture via free-text search, minimum ROI, provider and sport
  filters, and restored results when filters are cleared;
- opening the details and seeing Python-computed stake payouts, source
  metadata, missing verification and all risk assumptions;
- keyboard Escape and click-to-close detail drawer;
- safe refreshes with unchanged provider API consumption (none);
- simulated broken HTTP API, clearing previously displayed opportunities,
  and visible error/blocked status;
- browser `pageerror` and off-localhost network request detection.

## Windows manual accessibility checklist

With `uv run python -m scripts.serve_dashboard_api --demo` running,
open `http://127.0.0.1:8000/`:

1. Use Tab, Shift+Tab and Enter without a mouse; filters and detail
   buttons must be reachable. Opening a detail moves focus into the
   dialog; Escape closes it and focus returns to the opportunity button.
2. At 200% browser zoom and narrow widths, confirm that the sidebar,
   filters, table-scrolling container, detail drawer and warning labels
   remain legible and do not obscure critical state.
3. Use the browser's reduced-motion mode. Verify that the UI remains
   usable and no animation is required to understand data.
4. Turn off JS or block `/api/v1/events`: no demo rows should be
   represented as fresh live opportunities.
5. Start without `--demo`: confirm no ROI or example market is shown.

**These browser checks do not constitute a full WCAG certification.**
Phase 21 includes broader accessibility, security and deployment reviews.

## Acceptance / next gate

Phase 20.3 passes when the Python full suite, real Chromium test job,
security checks and review are green, and the local UI can be inspected
manually. The next step is Phase 20.4 **only after** independent Phase 19
source-role, settlement, licence and freshness approvals. Until those
external issues are resolved, improve demo/UI documentation and quality
without attempting paid live odds.
