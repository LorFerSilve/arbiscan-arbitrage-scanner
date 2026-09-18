# Provider documentation

Provider integrations are isolated behind the canonical `ProviderAdapter` boundary. Documents in this directory describe the provider contract, concrete integrations, and phase-specific provider expansion rules.

- [`contract.md`](contract.md) — provider-neutral adapter contract and behavior.
- [`phase-4-completion.md`](phase-4-completion.md) — formal Phase 4 provider-contract completion record.
- [`the-odds-api.md`](the-odds-api.md) — first real odds-data source, including source-vs-price-origin semantics.
- [`phase-16-readiness.md`](phase-16-readiness.md) — mandatory hand-off and implementation sequence for multi-provider expansion.
- [`phase-16.1-provider-selection.md`](phase-16.1-provider-selection.md) — completed candidate review and selection of the first second-source development target.
- [`oddspapi.md`](oddspapi.md) — OddsPapi onboarding record, technical mapping notes, and unresolved production blockers.

Phase 16.1 through Phase 16.8 are technically complete. OddsPapi is the validated
second real transport source for the Phase 16 architecture, including provenance,
normalization/matching, overlap-safe coexistence, persistence, observability, and
staged enablement/rollback.

OddsPapi is **not approved for production activation yet**. Its provider-specific
data-rights, retention, display, fixture, and geographic-use questions remain external
blockers documented in [`oddspapi.md`](oddspapi.md). The explicit transport-source
enablement gate ensures those unresolved questions cannot be treated as equivalent to
technical readiness.

The next roadmap dependency is **Phase 17 — advanced market support**.

Before enabling any real source in a production-like environment, complete
[`../product/provider-integration-checklist.md`](../product/provider-integration-checklist.md).
Multi-source work must also follow ADR-0012 under [`../adr/`](../adr/).
