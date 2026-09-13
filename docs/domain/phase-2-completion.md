# Phase 2 completion record

Status: **Complete pending CI verification on the Phase 2 pull request**

## Roadmap exit criteria

### All later subsystems can communicate through canonical types

Satisfied by the public `arbiscan.domain` API and immutable core entities for sports, competitions, participants, events, markets, selections, odds quotes, providers, provider references, opportunities, and stake plans.

### No provider-specific field is required by the arbitrage engine

Canonical event/market/selection identity is provider-independent. Provider-local identifiers exist only in explicit provenance/reference objects and quote source metadata. Core opportunity/stake-plan schemas refer to canonical IDs and `ProviderId`, not provider payload fields or labels.

### Canonical schemas are documented and thoroughly unit-tested

Satisfied by:

- `docs/domain/canonical-model.md`;
- `docs/domain/serialization.md`;
- ADR-0003;
- unit coverage for construction validation, immutable/type-sensitive identity, non-team events, explicit market semantics, source provenance, timezone normalization, exact decimal precision, serialization round trips, malformed data, and fail-closed decoding.

## Deliberate Phase 2 boundaries

- Phase 2 does not implement arbitrage formulas or stake allocation algorithms; Phase 3 owns those calculations.
- Phase 2 does not generate canonical IDs; later normalization/matching work owns identity resolution strategy.
- Phase 2 does not implement provider adapters.
- Phase 2 does not decide freshness thresholds; later ingestion/freshness phases own operational freshness policy.
- The JSON codec is an internal canonical snapshot format, not the future public HTTP API contract.
