# Provider Integration Checklist

This checklist is mandatory before a real odds provider is enabled in ArbiScan. It exists to prevent technical integration work from getting ahead of data-rights, semantic, and reliability validation.

## 1. Provider identity

- [ ] Canonical provider name defined.
- [ ] Provider type recorded: bookmaker, exchange, aggregator, or other feed.
- [ ] Official technical documentation identified.
- [ ] Stable provider identifier assigned internally.

## 2. Authorized access

- [ ] Access method is official or otherwise explicitly authorized.
- [ ] Required account/subscription is understood.
- [ ] Authentication method is documented.
- [ ] Credential issuance and rotation procedure is understood.
- [ ] No anti-bot circumvention, CAPTCHA bypass, credential abuse, or unauthorized scraping is required.

## 3. Terms, licensing, and permitted use

The following must be reviewed against the provider's current terms before production use:

- [ ] API/data licensing terms.
- [ ] Permitted personal/non-commercial/commercial use.
- [ ] Caching permissions and maximum cache duration.
- [ ] Raw-data storage permissions and retention limits.
- [ ] Normalized/derived-data storage permissions.
- [ ] Redistribution/display restrictions.
- [ ] Attribution requirements.
- [ ] Geographic access restrictions.
- [ ] Restrictions relevant to automated processing.
- [ ] Restrictions relevant to downstream alerts or dashboards.

If any point is unclear, the integration remains non-production until clarified.

## 4. Transport contract

- [ ] Base URLs/endpoints documented.
- [ ] Protocol documented: REST, WebSocket, streaming, polling, etc.
- [ ] TLS/secure transport available.
- [ ] Request timeouts defined.
- [ ] Pagination behavior understood.
- [ ] Compression/content encoding understood.
- [ ] Maximum expected payload size understood.
- [ ] API versioning/deprecation policy understood.

## 5. Rate limits and quotas

- [ ] Per-second/per-minute/per-day limits documented.
- [ ] Burst behavior documented.
- [ ] Quota headers or quota endpoint documented.
- [ ] Rate-limit error semantics documented.
- [ ] Backoff/retry strategy defined.
- [ ] Retry-after semantics used when available.
- [ ] Polling frequency fits both freshness requirements and provider limits.

## 6. Data freshness and timestamps

- [ ] Provider source timestamp fields identified.
- [ ] Timestamp timezone/offset semantics documented.
- [ ] Meaning of each timestamp documented: generated, updated, published, etc.
- [ ] Feed delay, if any, documented.
- [ ] Real-time versus delayed status understood.
- [ ] Clock-skew assumptions documented.
- [ ] ArbiScan ingestion timestamp will be captured independently.
- [ ] Provider-specific freshness threshold can be configured.

## 7. Event model

- [ ] Provider event ID identified.
- [ ] Sport identifier mapping defined.
- [ ] Competition/league identifiers available or derivable.
- [ ] Participant identifiers/names available.
- [ ] Scheduled start time available.
- [ ] Home/away or participant ordering semantics documented.
- [ ] Event lifecycle statuses documented.
- [ ] Postponed/rescheduled/cancelled behavior understood.
- [ ] Duplicate/reissued event-ID behavior understood.

## 8. Market model

For every market enabled from the provider:

- [ ] Provider market ID/name recorded.
- [ ] Canonical ArbiScan market mapping exists.
- [ ] Complete outcome set defined.
- [ ] Selection IDs/names mapped.
- [ ] Settlement semantics documented.
- [ ] Regulation versus overtime/extra-time semantics documented where relevant.
- [ ] Void/push/dead-heat behavior documented where relevant.
- [ ] Market suspension/closure semantics documented.
- [ ] Unsupported variants fail closed.

A textual similarity between two provider market names is not sufficient evidence of semantic equivalence.

## 9. Odds model

- [ ] Odds format documented.
- [ ] Conversion to internal decimal representation tested if needed.
- [ ] Price precision documented.
- [ ] Null/removed/suspended price behavior documented.
- [ ] Selection availability status available or inferable safely.
- [ ] Provider-specific price errors/edge cases captured as fixtures.

## 10. Stake and execution metadata

These fields are not required for basic theoretical-arbitrage detection, but their availability must be recorded:

- [ ] Minimum stake information available?
- [ ] Maximum stake/limit information available?
- [ ] Stake increment rules available?
- [ ] Commission/fee information available?
- [ ] Currency information available?
- [ ] Account-specific limits/prices possible?

If these are unavailable, ArbiScan must not imply that theoretical profitability is fully executable.

## 11. Error behavior

- [ ] Authentication failures understood.
- [ ] Rate-limit failures understood.
- [ ] Temporary provider failures understood.
- [ ] Invalid request errors understood.
- [ ] Partial-data responses understood.
- [ ] Maintenance/outage behavior understood.
- [ ] Retryable versus non-retryable failures classified.

## 12. Security

- [ ] Credentials stored only through approved runtime secret handling.
- [ ] Credentials never appear in `.env.example` values.
- [ ] Authorization headers and secrets are redacted from logs.
- [ ] Provider payload is validated as untrusted input.
- [ ] URLs or payload fields cannot inject unsafe log/UI content without encoding.
- [ ] Dependency requirements introduced by the adapter have been reviewed.

## 13. Testing requirements

Before enabling the provider:

- [ ] Representative raw fixtures exist where retention terms permit.
- [ ] Contract/parser tests exist.
- [ ] Malformed-payload tests exist.
- [ ] Unknown status fails closed.
- [ ] Unknown market fails closed.
- [ ] Stale quote is rejected.
- [ ] Suspended/closed quote is rejected.
- [ ] Complete supported market normalizes successfully.
- [ ] Event mapping behavior is tested.
- [ ] Provider failures do not break unrelated providers.

## 14. Observability

- [ ] Request count and failure metrics available.
- [ ] Rate-limit events measurable.
- [ ] Last-successful-update time measurable.
- [ ] Ingestion latency measurable.
- [ ] Stale-quote count measurable.
- [ ] Parsing/normalization failures measurable.
- [ ] Provider health can be surfaced without leaking credentials.

## 15. Multi-source coexistence requirements

These checks are mandatory for Phase 16 and later whenever another real transport/data source is introduced.

- [ ] Transport/source provider identity is explicitly distinguished from bookmaker/exchange price-origin identity.
- [ ] The source has an operationally independent authentication/quota/failure domain from already enabled sources if it is intended to satisfy the Phase 16 independent-source criterion.
- [ ] Expected bookmaker/price-origin overlap with existing sources is documented.
- [ ] Overlapping observations preserve both transport-source and price-origin provenance as required by ADR-0012.
- [ ] The same bookmaker observed through multiple transports cannot be counted as multiple executable price providers.
- [ ] Source-observation identifiers remain collision-safe across independent transports.
- [ ] A deterministic overlap-resolution policy exists for fresher/equivalent observations.
- [ ] Same-time materially conflicting observations fail closed unless an explicit documented trust policy resolves them.
- [ ] Source-specific outages, throttling, stale data, and malformed responses cannot corrupt unrelated provider state.
- [ ] Cross-source event matching is covered by adversarial fixtures before shared market books are enabled.
- [ ] Persisted opportunity evidence can identify both the selected price origin and the transport source from which it was observed.
- [ ] Source-specific telemetry can diagnose overlap/conflict behavior without parsing opaque trace strings.

Multiple bookmakers returned by a single aggregator do not by themselves satisfy the Phase 16 requirement for multiple independent real data sources.

## 16. Production-readiness decision

A provider can be marked production-ready only if:

1. authorized access is confirmed;
2. usage/storage/redistribution constraints are documented;
3. all enabled markets have explicit canonical semantics;
4. freshness/status behavior is understood;
5. contract tests pass;
6. secrets are handled safely;
7. known unresolved risks are recorded in the risk register;
8. no unresolved issue can cause silent false-positive arbitrage detection;
9. for Phase 16+, all applicable multi-source coexistence requirements above are satisfied before joint enablement.
