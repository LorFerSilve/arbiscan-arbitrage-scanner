# Provider documentation

Provider integrations are isolated behind the canonical `ProviderAdapter` boundary. Documents in this directory describe the provider contract, concrete integrations, and phase-specific provider expansion rules.

- [`contract.md`](contract.md) — provider-neutral adapter contract and behavior.
- [`phase-4-completion.md`](phase-4-completion.md) — formal Phase 4 provider-contract completion record.
- [`the-odds-api.md`](the-odds-api.md) — first real odds-data source, including source-vs-price-origin semantics.
- [`phase-16-readiness.md`](phase-16-readiness.md) — mandatory hand-off and implementation sequence for multi-provider expansion.

Before enabling any real source, complete [`../product/provider-integration-checklist.md`](../product/provider-integration-checklist.md). Multi-source work must also follow ADR-0012 under [`../adr/`](../adr/).
