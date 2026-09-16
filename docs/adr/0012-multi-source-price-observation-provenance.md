# ADR-0012 — Preserve transport-source identity for overlapping price observations

- Status: Accepted
- Date: 2026-09-17
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

ADR-0006 established a necessary distinction between the source/transport provider that delivers an odds payload and the bookmaker/exchange that originates the executable price. That distinction is already sufficient for one aggregator source because `OddsSnapshot.provider_id` identifies the transport vendor while normalized `OddsQuote.provider_id` identifies the price origin.

Phase 16 introduces a new case: two independent transport sources may expose the same bookmaker price origin for the same canonical event, market, and selection. For example, an aggregator and a direct bookmaker API may both report a price from the same bookmaker.

The current single-source model intentionally keys live canonical quote state primarily by price origin. Without an explicit Phase 16 policy, overlapping observations could create ambiguous provenance, identifier collisions, arbitrary source precedence, or the false impression that two transport observations from one bookmaker are two independent executable prices.

## Decision

Phase 16 multi-source ingestion must preserve both identities as first-class provenance:

1. **transport/source provider** — the independent API/feed through which ArbiScan observed the data;
2. **price provider** — the bookmaker or exchange that actually offers the quoted price.

`OddsQuote.provider_id` remains the price-provider identity used by stake plans, provider filters, and market-book legs. Phase 16 must additionally preserve the transport/source provider explicitly in canonical quote evidence before a second overlapping source is enabled.

A source observation identifier must include the transport/source identity. Two observations delivered by different transport providers must therefore remain distinct audit records even when they refer to the same bookmaker, event, market, selection, and source timestamp.

### Canonical overlap resolution

When multiple eligible transport observations describe the same price provider and canonical selection:

1. stale, inactive, malformed, or otherwise ineligible observations are removed first;
2. observations are compared by the existing effective freshness timestamp policy;
3. the newest trustworthy observation is preferred;
4. if multiple observations have the same effective timestamp and the same semantic price/status, they are equivalent and one may be selected deterministically while all source provenance remains auditable;
5. if multiple observations have the same effective timestamp but conflict materially in price or status, that price-provider/selection slot fails closed for the cycle unless a separately documented trust policy can resolve it;
6. transport observations from the same price provider must never be counted as separate bookmaker outcomes or separate executable legs.

ArbiScan will not silently introduce a hard-coded source-precedence ranking during Phase 16. If operational evidence later justifies explicit source trust tiers, that requires a separate documented decision.

## Rationale

Arbitrage calculations reason about executable price origins, while reliability and auditability reason about data-delivery sources. Treating these as the same identity is incorrect once multiple feeds overlap.

Keeping observations distinct until an explicit consolidation step provides several guarantees:

- one bookmaker cannot be counted twice merely because two APIs reported it;
- conflicting feeds do not resolve by incidental polling order;
- freshness remains explainable per source;
- provider outages and data-quality failures remain attributable to the correct transport source;
- persisted evidence can explain which feed supplied the selected bookmaker price;
- direct and aggregator-delivered observations can coexist without identifier collisions.

## Consequences

### Positive

- Phase 16 can add independent sources without weakening bookmaker-level semantics;
- overlapping coverage becomes deterministic and auditable;
- source-specific health, rate limits, and failures remain distinct from price-provider identity;
- market-book and staking behavior can remain price-provider-centric.

### Negative / trade-offs

- Phase 16 must extend quote provenance and source-observation identity before overlapping feeds are enabled;
- persistence and serialization will need a compatible migration/update;
- live state requires an explicit observation-consolidation step rather than relying on incidental last-write behavior;
- tests must cover same-bookmaker overlap in addition to ordinary cross-bookmaker aggregation.

## Compatibility with the Phase 15 baseline

This decision is mandatory for Phase 16 multi-source enablement. It does not require retroactively changing the single-real-source Phase 15 runtime before Phase 16 begins. The provenance/model migration is the first architectural dependency of Phase 16 whenever the selected second source can overlap an existing price origin.

If a candidate second source is provably non-overlapping, implementation may proceed in parallel, but general Phase 16 completion still requires the overlap-safe model because future providers cannot rely on permanent disjoint bookmaker coverage.

## Alternatives considered

### Treat every transport source as a separate price provider

Rejected. It would make the same bookmaker appear to be multiple executable counterparties and could create false diversification or duplicate arbitrage legs.

### Collapse observations immediately by bookmaker and keep only whichever arrives last

Rejected. Arrival order is not a correctness policy, loses transport provenance, and makes conflicting feeds non-deterministic.

### Assign a fixed preferred data vendor globally

Rejected for the initial Phase 16 design. A static ranking may hide fresher or healthier data and would require evidence-based operational policy that does not yet exist.

### Keep transport identity only inside opaque trace strings

Rejected for multi-source operation. Opaque provenance is useful for audit traces but is insufficient for deterministic overlap resolution, persistence keys, and source-specific telemetry.

## Revisit triggers

Revisit this decision if:

- a richer `DataVendor`/`Bookmaker` type split replaces the shared provider identifier type;
- exchanges require venue/account-specific price-origin semantics;
- operational evidence supports explicit source trust tiers;
- provider licensing requires source-specific display or retention behavior that affects consolidation;
- streaming feeds introduce sequence/version identifiers stronger than timestamps.
