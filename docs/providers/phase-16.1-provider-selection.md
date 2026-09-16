# Phase 16.1 — Provider candidate review and selection

- Status: Complete
- Review date: 2026-09-17
- Current real source: The Odds API
- Selected second-source development target: **OddsPapi**
- Production enablement status: **Blocked pending explicit data-rights clarification and later Phase 16 gates**

## Objective

Phase 16.1 selects the first additional real transport/data source to integrate behind ArbiScan's existing `ProviderAdapter` boundary. The selection is based on correctness, operational independence, compatibility with the current MVP semantics, timestamp/status quality, testability, and legal/licensing clarity rather than raw bookmaker count alone.

This review does **not** authorize production use and does not bypass the mandatory provider integration checklist. It determines which provider Phase 16 should implement first after the Phase 16.2 multi-source provenance hardening work.

## Current-source baseline

The Odds API remains ArbiScan's first real transport source. It exposes bookmaker-level odds, timestamps, European bookmaker coverage, and the existing `h2h` semantics used by the current football/tennis MVP path.

The selected second source must be operationally independent from The Odds API. Bookmakers exposed by an aggregator are price origins, not independent transport sources.

## Candidates reviewed

Three candidates were reviewed:

1. **OddsPapi** — self-service global odds aggregator with REST and WebSocket products.
2. **Sportradar Odds Comparison Core** — enterprise/global odds-comparison product with REST APIs and support-configured access.
3. **Betfair Exchange API** — direct exchange transport with low-latency market-data support.

The first two are the primary like-for-like aggregator candidates. Betfair is included as a direct-source control because it demonstrates the trade-off between source independence and semantic complexity.

## Decision summary

| Criterion | OddsPapi | Sportradar OC Core | Betfair Exchange |
| --- | --- | --- | --- |
| Independent transport from The Odds API | Yes | Yes | Yes |
| Self-service development access | Strong | Limited/support-configured | Moderate/account-dependent |
| Football pre-match 1X2 | Yes | Yes | Yes, but exchange semantics |
| Tennis pre-match winner | Yes | Yes | Yes, but exchange semantics |
| Stable event identifiers | Yes | Yes | Yes |
| Bookmaker/venue attribution | Yes | Yes | Single exchange venue |
| Per-price/source timestamps | Strong | Strong change-log/event support | Strong streaming/version semantics |
| Suspension/status metadata | Yes | Yes | Yes |
| REST polling suitability | Yes | Yes | Yes |
| Streaming path | Yes, paid WebSocket product | Product-dependent APIs | Yes, Exchange Stream API |
| CI fixture feasibility | Technically straightforward; retention terms need clarification | Technically straightforward; contract/addendum dependent | Feasible but licensing/account rules more complex |
| Expected overlap with The Odds API | High | High | Betfair itself overlaps |
| Current MVP semantic fit | **High** | **High** | Medium/low |
| Access/cost friction | Low | High | Medium/high depending use |
| Public terms clarity for ArbiScan storage/display | Incomplete | Contract/addendum based | Commercial/vendor rules apply |
| Phase 16 implementation suitability | **Selected** | Fallback/enterprise candidate | Not selected for first adapter |

## Candidate A — OddsPapi

### Access and transport

Official documentation exposes a versioned REST API (`/v4`) authenticated by API key and a separate WebSocket product. The public REST documentation includes sports, bookmakers, tournaments, fixtures, markets, participants, odds, historical odds, settlements, and scores.

Relevant official resources:

- Documentation overview: https://oddspapi.io/en/docs
- Odds endpoint: https://oddspapi.io/en/docs/get-odds
- Fixtures endpoint: https://oddspapi.io/en/docs/get-fixtures
- Bookmakers endpoint: https://oddspapi.io/en/docs/get-bookmakers
- Requests/quota: https://oddspapi.io/us/docs/requests-and-quota
- WebSocket quickstart: https://docs.oddspapi.io/quickstart
- Terms: https://oddspapi.io/en/legal/terms

The free REST tier is suitable for adapter development and deterministic fixture capture without requiring a production-scale subscription. WebSocket streaming exists but is not required for the first Phase 16 adapter; Phase 16 should first validate the existing polling contract and multi-source coexistence.

### MVP sport and market coverage

OddsPapi documents football/soccer and tennis coverage. Current official sport pages expose:

- football/soccer with a full-time result/1X2 market family;
- tennis with a match-winner market family.

These match ArbiScan's existing narrow MVP semantics closely enough that Phase 16 does not need to pull Phase 17 advanced-market work forward.

Relevant resources:

- Football: https://oddspapi.io/sports/football
- Tennis: https://oddspapi.io/sports/tennis

### Event identity and timestamps

The fixture/odds schemas expose:

- a stable `fixtureId`;
- participant IDs and names;
- sport and tournament IDs;
- scheduled start time;
- fixture status;
- top-level `updatedAt`;
- bookmaker-specific fixture identifiers where available;
- market and selection activation state;
- `bookmakerChangedAt` when supplied by the bookmaker;
- `changedAt` as OddsPapi's recorded change timestamp.

All documented timestamps are UTC ISO-8601. This is a strong fit for ArbiScan's existing distinction between source timestamps and local ingestion time.

### Rate limits and quota

The public REST docs document endpoint cooldowns rather than one global requests-per-second value. Current examples include:

- `/v4/odds`: 500 ms cooldown;
- `/v4/fixtures`: 2000 ms cooldown;
- `/v4/bookmakers`: 1000 ms cooldown;
- `/v4/historical-odds`: 5000 ms cooldown.

The subscription uses a monthly request allowance. Calls to billable endpoints consume one request per call, including completed 4xx/5xx responses. `/v4/account` exposes usage state and remains available after quota exhaustion.

The adapter must model cooldown and monthly quota independently. A generic retry loop is insufficient because repeatedly retrying a billable error can consume quota.

### Status/freshness semantics

OddsPapi exposes bookmaker, market, and selection activity fields. This maps well to ArbiScan's fail-closed status model:

- inactive/suspended bookmaker -> ineligible;
- inactive market -> ineligible;
- inactive selection -> ineligible;
- unknown status/schema -> fail closed.

For freshness, Phase 16 should prefer the most specific trustworthy timestamp available. `bookmakerChangedAt` and `changedAt` are not semantically identical: the former represents the bookmaker-reported change when available, while the latter is the provider's recorded change. The adapter must preserve that distinction rather than collapse both into one undocumented timestamp.

### Expected overlap with The Odds API

Overlap is intentionally expected and is architecturally useful. OddsPapi exposes bookmakers such as Pinnacle, Betfair Exchange, and numerous European books. The Odds API also documents European coverage including Pinnacle, Betfair Exchange, 1xBet, Betsson, and others.

Therefore Phase 16.2/ADR-0012 must be implemented before OddsPapi data is allowed to coexist with The Odds API in an actionable market book. The same bookmaker observed through both transports must remain one executable price origin, with distinct source observations and deterministic consolidation.

### Belgium/EU suitability

OddsPapi exposes Belgium-specific bookmaker feeds such as Unibet BE, Bwin BE, Napoleon Sports BE, and others in its public coverage pages. No Belgium-specific API access prohibition was identified in the public terms reviewed on 2026-09-17.

This is evidence that the feed is technically relevant to the Belgian/EU use case, not a legal conclusion. ArbiScan must not infer wagering legality or data-use rights from bookmaker coverage alone.

### Licensing/retention blocker

The public terms state that users may not resell, repackage, or redistribute OddsPapi data as a standalone product and that misuse/unauthorized distribution can lead to revocation. The public terms reviewed do **not** clearly define:

- permitted raw-payload retention duration;
- normalized/derived data retention;
- caching limits;
- dashboard/display rights for a private or public deployment;
- whether sanitized API fixtures may be committed to a public repository;
- whether historical data may be persisted locally beyond endpoint use.

Because ArbiScan's architecture intentionally persists audit evidence and uses sanitized fixtures in CI, these points are material. **Production enablement and committing real captured fixtures remain blocked until OddsPapi confirms these rights or provides applicable written terms.**

Synthetic hand-authored fixtures derived only from the published schema may be used during early adapter development if they contain no copied proprietary payload values.

### Candidate result

**Selected as the Phase 16 second-source development target**, subject to the compliance blocker above.

Why:

- strong semantic match with current football/tennis MVP;
- low-friction development access;
- explicit event IDs, statuses and useful timestamp fields;
- broad bookmaker overlap that directly exercises ADR-0012;
- independent auth/quota/failure domain from The Odds API;
- no need to introduce exchange-specific staking semantics or advanced markets.

## Candidate B — Sportradar Odds Comparison Core

### Access and product fit

Sportradar's Odds Comparison Core is a global odds-comparison configuration for its v2 Odds Comparison APIs. Official documentation states that Core provides 140+ global bookmakers and includes soccer and tennis. It exposes trial/production access levels, OpenAPI resources, schemas, and support-configured access.

Relevant official resources:

- Core overview: https://developer.sportradar.com/odds/reference/oc-core-overview
- Core FAQ: https://developer.sportradar.com/odds/reference/oc-core-faqs
- Prematch sport-event markets: https://developer.sportradar.com/odds/reference/oc-prematch-sport-event-markets
- Prematch change log: https://developer.sportradar.com/odds/reference/oc-prematch-sport-event-markets-change-log
- Public terms: https://developer.sportradar.com/sportradar-updates/page/terms-and-conditions

### Technical strengths

Sportradar is technically strong for ArbiScan:

- stable Sportradar sport/event/competitor IDs;
- explicit event statuses and reschedule/replacement information;
- bookmaker IDs;
- market/outcome removal semantics;
- one-second cache TTL on key prematch market/change-log endpoints;
- a change-log endpoint that reports sport events whose odds changed in the previous five minutes and includes an odds-update timestamp;
- global Core coverage including soccer and tennis.

This would make a robust Phase 16 source.

### Access/licensing constraints

OC Core is not simply enabled by creating a generic free key: the official documentation says Core access is configured at API-key level by Sportradar Support. Commercial rights, retention and redistribution are governed by the applicable agreement/order form/addenda rather than by a simple public self-service policy.

That is positive from a legal clarity perspective once contracted, but it creates substantial access friction for the current project. A production integration should only begin after receiving the applicable data-use terms and an enabled key.

### Rate limits

The public endpoint documentation exposes cache TTL/update frequencies, but this review did not find one authoritative public OC Core requests-per-second quota that can safely be encoded into ArbiScan. Actual call limits therefore need to be confirmed from the account/package contract or Sportradar support before implementation tuning.

### Candidate result

**Not selected as the first Phase 16 adapter, retained as the enterprise fallback candidate.**

The technical fit is excellent, but support-configured access, likely commercial friction, and contract-specific usage rights make it less suitable for the first development iteration than OddsPapi. If OddsPapi cannot provide acceptable retention/display/fixture rights, Sportradar becomes the preferred fallback rather than weakening ArbiScan's compliance boundary.

## Candidate C — Betfair Exchange API

### Technical strengths

Betfair provides a documented Exchange API for market navigation, odds/volumes and account operations, plus a low-latency Stream API for market-price updates.

Official resources:

- Exchange API: https://developer.betfair.com/exchange-api/
- Vendor/licensing FAQ: https://developer.betfair.com/vendor-program/faq/
- Vendor process: https://developer.betfair.com/vendor-program/the-process/

As a direct venue it provides a truly independent transport and avoids aggregator-to-aggregator overlap for the Betfair venue itself.

### Why it is not the first Phase 16 target

Betfair's price semantics are exchange-specific: back/lay sides, liquidity, commission and executable volume matter. Treating exchange back odds as ordinary bookmaker prices without modeling those constraints would weaken Phase 12 actionability semantics.

Betfair also distinguishes private API use from distributed/commercial software and documents vendor/business licensing requirements and fees. These requirements make it a poor first source for a phase whose goal is multi-provider transport coexistence without pulling new execution/market semantics into scope.

### Candidate result

**Rejected for the first Phase 16 adapter.** It remains a plausible later direct-source integration after exchange semantics are modeled explicitly.

## Selected provider decision

ArbiScan will implement **OddsPapi** as the first second-source adapter after Phase 16.2.

The selection is intentionally scoped as follows:

1. OddsPapi becomes the Phase 16 development/integration target.
2. Phase 16.2 provenance hardening is implemented before mixed real-source market books are enabled.
3. Early adapter tests may use synthetic schema-faithful fixtures that do not copy proprietary live values.
4. Real captured OddsPapi payloads must not be committed to the public repository until fixture-retention permission is confirmed.
5. Production enablement remains blocked until caching, raw/normalized retention, dashboard/display, and fixture-use rights are explicitly confirmed.
6. If those rights cannot be obtained on acceptable terms, implementation pivots to Sportradar OC Core rather than bypassing the provider checklist.

## Phase 16.2 hand-off requirements created by this decision

Because the selected source overlaps heavily with The Odds API, Phase 16.2 is now unambiguously required before the new adapter can participate in actionable scanning.

The next implementation step must therefore:

- add explicit transport-source identity to quote/source-observation evidence;
- update source-observation identifiers so two transports cannot collide;
- preserve existing bookmaker/price-provider identity;
- implement deterministic overlap consolidation;
- fail closed on materially conflicting equal-time source observations;
- migrate persistence/serialization compatibly;
- add tests for The Odds API + OddsPapi same-bookmaker overlap.

No OddsPapi-specific exception should be added to the arbitrage core, staking core, or canonical market-book semantics.

## Phase 16.1 exit criteria

- [x] At least two plausible providers compared against Phase 16 requirements.
- [x] Access and licensing constraints documented.
- [x] Football/tennis and market compatibility documented.
- [x] Timestamp/status behavior documented.
- [x] Expected bookmaker overlap documented.
- [x] One provider selected for the first Phase 16 adapter.
- [x] Compliance blockers recorded rather than silently accepted.
- [x] Next dependency identified as Phase 16.2 multi-source provenance hardening.
