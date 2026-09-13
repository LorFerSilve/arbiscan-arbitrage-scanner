# ADR-0006 — Separate aggregator source identity from bookmaker price origin

- Status: Accepted
- Date: 2026-09-13
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Phase 6 introduces ArbiScan's first real odds-data integration through an odds aggregator. The Phase 4/5 model was sufficient for synthetic and direct-source providers because one adapter corresponded to one price origin. A real aggregator invalidates that assumption: one upstream API response may contain prices from many bookmakers or exchanges.

If every normalized quote inherited only the aggregator provider ID, prices from distinct bookmakers would be collapsed into one identity. This would destroy provenance, make provider inclusion/exclusion unreliable, and could cause later market-book construction to reason incorrectly about where executable prices originate.

Real aggregator payloads also expose freshness below the request/snapshot level. Different bookmaker markets in one response may have different update timestamps.

## Decision

ArbiScan distinguishes two identities at the provider boundary:

1. **source/transport provider** — the adapter and API from which ArbiScan obtained the payload;
2. **price provider** — the bookmaker or exchange that actually offers a quoted price.

`OddsSnapshot.provider_id` identifies the source/transport provider.

`SourceMarket.price_provider` may identify an underlying bookmaker/exchange when an aggregator supplies that information. For a direct provider this field may remain absent, in which case the source provider is also the price provider.

During canonical normalization:

```text
quote provider = source market price_provider OR snapshot/source provider
```

`OddsQuote.provider_id` therefore always represents the origin of the executable price, not merely the transport vendor.

`SourceMarket.source_timestamp` additionally preserves the most specific market-level provider timestamp available. Freshness evaluation uses that timestamp before falling back to a snapshot-level source timestamp or ingestion time.

Raw provenance retains both identities so the delivery path remains auditable.

## Rationale

Arbitrage is inherently cross-price-origin analysis. Correct attribution is therefore not optional metadata; it is a correctness invariant.

Keeping the aggregator as snapshot provenance while storing the underlying bookmaker on quotes gives later systems enough information to:

- choose prices across actual bookmakers;
- enforce bookmaker allow/deny policies;
- diagnose stale feeds per bookmaker;
- retain the vendor path used to acquire the data;
- support future direct adapters for the same bookmaker without conflating transport and price origin.

Market-level timestamps similarly prevent one fresh bookmaker update from making stale prices in the same aggregator response appear fresh.

## Consequences

### Positive

- multi-bookmaker aggregator data can be represented without losing price provenance;
- Phase 9 can construct books using true bookmaker identity;
- freshness becomes more granular and correct;
- direct providers remain compatible through the fallback rule;
- aggregator and direct-bookmaker adapters can coexist later.

### Negative / trade-offs

- source records carry additional metadata;
- one aggregator snapshot may create many distinct canonical quote-provider identities;
- later provider registries/persistence must distinguish data vendors from bookmakers/exchanges;
- deduplication across a direct bookmaker feed and the same bookmaker observed through an aggregator will require explicit policy.

## Alternatives considered

### Treat the aggregator as the provider for every quote

Rejected because it loses bookmaker provenance and makes cross-bookmaker reasoning semantically incorrect.

### Create one adapter instance per bookmaker returned by the aggregator

Rejected because those are not independent transports: authentication, quota, failures and request lifecycle belong to the aggregator API. Modeling them as separate adapters would misrepresent operational behavior.

### Encode bookmaker identity only in raw source IDs

Rejected because downstream domain logic must not parse opaque IDs to recover essential semantics.

## Revisit triggers

Revisit this decision if:

- the canonical provider model is split into explicit `DataVendor` and `Bookmaker` entities;
- exchange back/lay semantics require a richer price-origin model;
- Phase 9 establishes deduplication rules between direct and aggregator-delivered prices from the same bookmaker;
- a future provider returns prices whose origin is intentionally anonymous or composite.
