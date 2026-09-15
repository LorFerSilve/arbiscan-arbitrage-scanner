# ADR-0011: Transport-neutral service/API boundary

## Status

Accepted for Phase 13.

## Decision

ArbiScan exposes a typed application API in `arbiscan.api`. Client-facing contracts are immutable dataclasses and the application service depends on an `ApiDataSource` protocol rather than SQLite tables, provider payloads, or other persistence internals.

The Phase 13 endpoint surface is documented as OpenAPI 3.1 by `openapi_document()`: health/readiness, provider status, sports, events, current odds, opportunities, opportunity provenance, safe configuration status, and metrics. Collection queries use bounded offset pagination and explicit filters.

A concrete HTTP framework is intentionally not added in this phase. FastAPI remains the preferred candidate for a future HTTP transport, but adding it now would introduce a runtime/transitive dependency set before ArbiScan needs an actual network listener. The transport-neutral contract lets a FastAPI adapter be added without coupling domain/application code to that framework.

## Security boundary

The default policy is loopback-only. A non-local bind is rejected unless authentication and rate limiting are both explicitly enabled. Public contracts contain no credential fields, provider secrets, or raw configuration values. The scanner-only boundary remains unchanged: this API exposes observations and opportunities, not wager execution or fund movement.

## Consequences

- clients do not need direct persistence access;
- transport adapters can be replaced without changing application contracts;
- OpenAPI routes and error semantics are explicit and testable;
- no new supply-chain dependency is introduced for Phase 13;
- an externally reachable HTTP adapter must implement the documented authentication and rate-limiting policy before it can be enabled.
