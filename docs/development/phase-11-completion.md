# Phase 11 — Persistence and auditability

Phase 11 establishes a durable audit boundary for canonical evidence so detected opportunities can be reconstructed without coupling the live scanner to a particular production database technology.

## Implemented boundary

- `SqliteAuditStore` provides a dependency-free transactional reference implementation for durable canonical evidence;
- schema migrations are explicit, versioned, and idempotent;
- canonical quotes, opportunities, and optional stake plans are serialized through the canonical domain serialization layer rather than provider-specific payload schemas;
- opportunity-to-quote ordering is persisted explicitly so the evidence set can be reconstructed deterministically;
- repeated writes of the same identifier are idempotent only when the canonical payload is identical;
- an identifier collision with different canonical content fails closed instead of silently overwriting evidence;
- retention can purge old unreferenced quotes while preserving quotes required to reconstruct persisted opportunities;
- indexes support event/time, provider/time, opportunity evidence, and audit-event access patterns.

## Storage decision

The roadmap asked Phase 11 to evaluate durable structured persistence rather than prematurely hard-code a distributed production stack. The current implementation deliberately uses SQLite as the reference audit store because it proves migrations, transactions, reconstruction, retention, and failure semantics without adding an external runtime dependency.

This is not a claim that SQLite is the final deployment database. PostgreSQL or another durable backend may be introduced later behind the same persistence boundary when workload and deployment requirements justify it. Changing the backend must preserve the current reconstruction and fail-closed invariants.

## Correctness and failure behavior

Persisting an opportunity requires exactly the quotes referenced by that opportunity. Optional stake-plan evidence must belong to the same opportunity. Reconstruction validates the stored canonical payloads through the domain layer and rejects incomplete or inconsistent evidence.

Persistence errors are surfaced as `PersistenceError`; they do not mutate canonical calculations or silently convert incomplete evidence into a valid record.

## Validation evidence

The persistence regression suite verifies:

- migration idempotency;
- deterministic opportunity reconstruction from persisted canonical quotes;
- rejection of incomplete evidence sets;
- rejection of same-ID/different-payload collisions;
- retention of old quotes when they remain referenced by an opportunity.

The primary regression coverage is `tests/unit/test_persistence_store.py`.

## Exit-criteria mapping

- **A previously emitted opportunity can be reconstructed from persisted evidence:** `reconstruct_opportunity` returns the canonical opportunity, ordered quote evidence, and optional stake plan.
- **Persistence failure does not silently produce corrupted signals:** invalid/colliding evidence fails closed and persistence remains outside the mathematical correctness path.
- **Migrations are tested:** migrations are explicit, versioned, and covered for repeated application.

## Deliberately deferred

Production database selection, replication, backup/restore automation, horizontal scale, and deployment-specific high availability remain later deployment/scaling concerns. Phase 16 may extend persisted provenance to preserve multiple independent transport-source observations without weakening the current audit guarantees.
