# Canonical domain model

Phase 2 defines the provider-independent language used by every later ArbiScan subsystem.

- [`canonical-model.md`](canonical-model.md) — entities, identity, market semantics, provenance, and invariants.
- [`serialization.md`](serialization.md) — versioned deterministic internal JSON snapshot format.

Normative implementation lives under `src/arbiscan/domain/`. Provider adapters may translate into these types, but provider-specific payload fields and labels must not leak past the adapter/normalization boundary.
