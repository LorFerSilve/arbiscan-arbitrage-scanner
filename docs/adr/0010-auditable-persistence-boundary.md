# ADR-0010: Auditable persistence boundary

- Status: Accepted
- Date: 2026-09-15

## Context

Phase 11 requires durable evidence sufficient to reconstruct emitted opportunities while keeping live detection independent from database availability. Persistence must preserve canonical semantics, UTC timestamps, idempotency, query indexes, migrations, retention, and an audit trail.

## Decision

ArbiScan defines persistence as a downstream side effect of canonical detection, never as an input required for the arbitrage engine to produce a mathematically valid result. The reference implementation is `SqliteAuditStore`, using only the Python standard library so CI remains deterministic and network-free.

Canonical domain objects are stored as the existing versioned deterministic JSON snapshots. Persistence therefore does not create a second set of domain schemas that can drift from the canonical model. Snapshot rows carry event/provider/time projection columns solely for indexed retrieval.

Opportunity persistence is transactional: the opportunity, its exact ordered quote set, and an optional stake plan are committed together. Reusing a canonical ID with different content fails closed. Reconstruction deserializes through the canonical codec and verifies that the stored quote ordering exactly matches the opportunity's referenced quote IDs.

The schema maintains append-only creation audit events. Quote retention may delete old unreferenced quote snapshots, but quotes used by persisted opportunities are protected indefinitely unless a future explicit evidence-retention migration defines otherwise.

## PostgreSQL and Redis evaluation

PostgreSQL remains the preferred production durable backend once deployment requires concurrent multi-process writers, stronger operational tooling, replication, or larger analytical workloads. A future PostgreSQL implementation should preserve this repository contract and migration semantics rather than leak SQL models into the domain layer.

Redis is not a durable source of audit truth. It may later be used for ephemeral caches, coordination, rate-limit state, or stream fan-out, but persisted opportunity evidence must remain in a durable store.

SQLite is accepted now because Phase 11 needs a concrete, migration-tested persistence implementation without adding infrastructure or a third-party runtime dependency. It is appropriate for deterministic CI, local development, and single-process deployments; it is not a claim that SQLite is the final horizontally scaled production database.

## Failure semantics

Persistence errors raise `PersistenceError`; they are never converted into successful writes or silently ignored inside the store. Callers may continue scanning after surfacing/recording the persistence failure, but must not claim that an opportunity is durably auditable unless the transactional write succeeded.

## Consequences

- Previously persisted opportunities can be reconstructed from canonical evidence.
- Domain serialization remains the single schema authority.
- Retention cannot accidentally destroy evidence referenced by an opportunity.
- Database outages do not require coupling database reads into live arbitrage detection.
- Production PostgreSQL remains an implementation choice behind the persistence boundary rather than a domain dependency.
