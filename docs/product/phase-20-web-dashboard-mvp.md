# Phase 20 — Local web dashboard MVP: implementation plan

**Status:** Planned. This document is a delivery specification, **not** an
assertion that an interactive web app already runs.

**Purpose:** Give ArbiScan a useful browser interface **before** full
production rollout, without weakening its scanner-only and market correctness
boundaries. The initial local dashboard uses **deterministic synthetic data or
approved read-only internal projections**. It does not need real provider
credentials or billable API access.

## Existing foundation (do not rebuild)

- Phase 13: `arbiscan.api.ArbiScanApi`, read-only response contracts and
  pagination/filtering, OpenAPI schema. This is a Python *application service*,
  not yet a complete deployed HTTP web server.
- Phase 15: `arbiscan.dashboard` immutable opportunity/leg projection,
  filtering, HTML-escaped rendering, and deduplicated change/expiry alerts.
  It is **not** a full browser application with navigation and live updates.
- Phases 11/12/14/18: persistence, lifecycle, operational metrics, and replay
  provide existing source-of-truth boundaries. No duplicate ROI/stake
  arithmetic in JavaScript.

## Delivery order

### 20.1 — Read-only HTTP and user-flow contract

- Inventory the Phase 13 API objects, the Phase 15 dashboard projections and
  available persistence/service adapters.
- Define a **local-only** Python HTTP adapter for versioned read-only
  `/health`, `/readiness`, `/providers/status`, `/events`,
  `/odds`, `/opportunities`, `/opportunities/{id}`, and `/metrics`.
  Reuse existing responses instead of returning raw provider payloads.
- Select the lightest maintainable HTTP implementation during the
  implementation PR; add no second odds/arbitrage backend and no separate
  Node.js service unless requirements justify it.
- Default bind `127.0.0.1` only. A non-loopback deployment needs the
  Phase 21 security controls (authentication, rate limiting and threat review).

### 20.2 — Browser UI (HTML/CSS/vanilla JavaScript)

A compact responsive page with:
- overview of scanner readiness, provider health, last update, unavailable
  data and quote freshness;
- searchable/sortable/filterable opportunity table: sport, competition,
  provider/bookmaker, minimum ROI, minimum profit and lifecycle state;
- opportunity detail: original match, time/competition, normalized 1X2
  market, exact outcome/provider/decimal price, quote timestamp/age,
  stake allocation, payout, net/gross assumptions and evidence provenance;
- explicit stale/expired/invalidated badges or empty states, never a
  stale opportunity displayed as currently actionable;
- **demo/fixture mode** visually distinguished from real provider-backed
  data; an empty live mode never fabricates profitable opportunities;
- basic polling or manual refresh using local read endpoints; no
  paid API calls triggered by browser refresh.

### 20.3 — Testable MVP, no live-provider dependency

- A single documented local start command and verified Windows path;
- deterministic fixture data for screenshots, unit/UI integration tests
  and CI; source-selectable empty/no-opportunity/blocked-provider states;
- no odds-provider key in HTML, JavaScript, logs or HTTP responses;
- accessible labels, keyboard navigation, mobile-friendly layout,
  clear number/currency/timestamp formatting;
- XSS escaping, input validation, read-only routes, safe local-only
  default, no arbitrary file access, and status error handling;
- regression tests verify no calculation drift between backend and UI,
  that demo data cannot be confused with live, that blocked Phase 19
  candidates remain blocked, and that refreshing does not spend API
  credits or generate duplicate alerts.

### 20.4 — Connect real scanner projections after evidence gates

This substep is **conditional**, not a prerequisite for the offline MVP:

- use the existing canonical market books, lifecycle and API projection
  layer only after Phase 19 verifies event identities, the underlying
  bookmaker's 90-minute settlement/void semantics, rights and ingestion
  freshness against real data;
- display exact best-price attribution and quote timestamps from the
  engine, with unknown/unsupported fields stated as such;
- keep provider access/quotas controlled by backend ingestion policy,
  independent from dashboard refresh rate;
- no automated bet placement, bookmaker logins or balance transfers.

## Exit criteria

The **local MVP** passes when a user can start one Python-backed web app
and inspect health, provider/event metadata, filtered synthetic opportunity
projections, detailed calculation/provenance and empty/blocked states, using
a normal browser, with tests demonstrating source-of-truth correctness,
security boundaries and **zero provider calls in fixture mode**.

The **live-data integration milestone** is separately accepted only
when Phase 19's explicit provider/market/legal gates permit those specific
feeds, and observations are tested against real source behavior.
Completion of the local MVP **does not** make ArbiScan production-ready
or satisfy the existing Phase 19 performance exit criteria.

**2026-10-28 evidence milestone:** Phase 19 published-document review
distinguishes OddsPapi's ambiguous soccer participant1/2 slots,
documented 1/X/2 outcome IDs, publicly specified Pinnacle settlement
exceptions and the differing The Odds API/OddsPapi terms. Findings
and their explicit remaining blockers:
[`phase-19-market-role-settlement-rights-audit.md`](../providers/phase-19-market-role-settlement-rights-audit.md).
This audit does **not** unblock live odds. Once this review has been
recorded, Phase 20.1's local synthetic HTTP/UI work can proceed without
waiting for external clarifications.

## What happens next (as of 2026-10-28)

1. Close the Phase 19 live market-equivalence blockers for the observed
   Chelsea (home)–Manchester United (away) fixture: OddsPapi's
   participant1/participant2 **semantic role**, specific bookmaker
   regulation/abandonment/void rules, and account/deployment data-use
   authorization. Real IDs have been observed by the user on 2026-10-28:
   The Odds API `6601f69175a02f03fb7065aacb538e01`;
   OddsPapi `id1000001772221358`, tournament `17`,
   participant1 `38` (Chelsea FC), participant2 `35`
   (Manchester United). These are observations, **not approved live odds**.
2. Avoid repeated metered discovery and any quote calls until a
   separately approved single-event read-only plan is justified.
3. Begin Phase 20.1/20.2 as a **local synthetic-data UI** once the
   Phase 19 blocker review is documented. Unfinished live-provider
   approvals do not force building the local UI to wait indefinitely.
4. After local Phase 20 MVP, finish the outstanding Phase 19 real-data
   performance/scale evidence and undertake Phase 21 hardening,
   Phase 22 packaging and Phase 23 release readiness before deployment.
