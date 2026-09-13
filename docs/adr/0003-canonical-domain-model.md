# ADR-0003 — Immutable canonical domain model

- Status: Accepted
- Date: 2026-09-13
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

ArbiScan must combine odds from heterogeneous providers without leaking provider-specific naming, payload shapes, market codes, timestamp behavior, or numeric representations into the arbitrage engine. Incorrect identity or numeric semantics could create false arbitrage signals.

The project therefore needs one canonical in-process model before provider adapters are implemented.

## Decision

ArbiScan will use immutable Python standard-library dataclasses and closed enums as its canonical domain model.

The model uses:

- strongly typed opaque ID value objects for canonical identities;
- `Decimal` for odds, money, probabilities, totals, and handicap values where exact decimal semantics matter;
- timezone-aware `datetime` values normalized to UTC;
- tuples for immutable ordered collections;
- runtime validation in constructors in addition to static typing;
- explicit provider-reference objects for provenance, without provider-specific payload fields in core entities;
- a versioned closed-registry JSON codec for internal canonical snapshots.

The first canonical market semantics are explicitly enumerated rather than accepted as free-form strings.

## Rationale

### Provider isolation

The arbitrage engine should compare canonical selections and prices, not bookmaker labels or response schemas. Strong canonical identities create that boundary.

### Numerical correctness

Binary floating-point values are unsuitable for claims about guaranteed monetary profit. `Decimal` preserves exact decimal input and makes later rounding policy explicit.

### Invalid states

Frozen value objects, enums, explicit IDs, UTC-aware timestamps, and constructor validation prevent many malformed states from entering downstream components.

### Dependency minimization

The domain core does not require a runtime validation/serialization framework. This keeps the most important model portable, inspectable, and independent from a third-party library lifecycle.

## Consequences

### Positive

- downstream systems share one stable semantic vocabulary;
- provider adapters can be tested against a precise target model;
- exact decimal values survive serialization round trips;
- timezone ambiguity is eliminated at canonical construction;
- domain objects are safe to share without mutation races;
- provider-specific details are constrained to provenance fields.

### Negative / trade-offs

- adding new sports or market semantics requires an explicit code/schema change;
- standard-library validation is more verbose than framework-generated validation;
- the internal serializer is custom code that must remain versioned and tested;
- identity-generation strategy is intentionally deferred and must be defined by matching/normalization work later.

## Alternatives considered

### Pydantic models

Pydantic provides strong validation and serialization ergonomics but would introduce a runtime dependency into the canonical core before one is required. It may be reconsidered for API-boundary DTOs later without replacing the internal domain model.

### Plain dictionaries

Rejected because arbitrary dictionaries make invalid states easy to represent, weaken static typing, and allow provider-specific fields to spread through the system.

### Binary floating point

Rejected for odds/money/profit-relevant values because representation and rounding error can invalidate guaranteed-profit claims near arbitrage thresholds.

### Free-form market and selection strings

Rejected because semantically different markets can have deceptively similar labels and provider/localization differences would leak into downstream logic.

## Revisit triggers

Reconsider this ADR if:

- measured serialization or construction overhead becomes material at production ingest rates;
- an external contract requires a schema framework that cannot map cleanly to these dataclasses;
- new market families demonstrate that the current explicit semantic model cannot evolve without excessive coupling;
- persistence/API requirements justify a generated schema layer while preserving the same canonical invariants.
