# Canonical domain model

## Purpose

The canonical domain model is the provider-independent contract between ingestion, normalization, matching, arbitrage detection, persistence, API, and presentation layers.

A provider adapter may know that one source calls a team `Home`, another calls it `1`, and another uses a localized team name. Downstream code must not. Once data crosses into the canonical model, identity and semantics are explicit.

## Design rules

1. Canonical entities are immutable (`frozen` dataclasses with slots).
2. Canonical IDs are opaque, strongly typed value objects. `EventId("x")` and `MarketId("x")` are distinct identities even when their text is equal.
3. Odds, monetary values, probabilities, totals, and handicaps use `Decimal`; binary floats are rejected at runtime where exact decimal semantics are required.
4. Every stored timestamp is timezone-aware and normalized to UTC at construction.
5. Canonical enums represent semantic values. Provider strings are never accepted as substitutes for enums.
6. Unknown or malformed semantics fail closed. Adapters/normalizers must not create a canonical object by guessing.
7. Provider-local identifiers remain provenance/reference data. The core arbitrage model operates on canonical event, market, selection, quote, and provider IDs.

## Core entities

### `Sport`

A closed canonical enum currently containing football, tennis, and motorsport. New sports require an explicit model change rather than arbitrary free-form strings.

### `Competition`

Contains:

- `CompetitionId`;
- canonical `Sport`;
- canonical name;
- optional region;
- optional season.

### `Participant`

Represents teams, individuals, drivers, constructors, or another explicitly classified participant. Every participant belongs to one canonical sport.

### `Provider`

Represents an odds source by `ProviderId`, display name, and semantic provider kind (bookmaker, aggregator, exchange, or synthetic). Credentials, URLs, rate limits, and provider SDK details do not belong in the domain entity.

### `ProviderEventReference`

Maps one provider to its local event identifier. A canonical event may contain at most one event reference per provider.

### `ProviderMarketReference`

Maps one provider to its local event and market identifiers. A canonical market may contain at most one market reference per provider.

### `Event`

Contains:

- `EventId`;
- `Sport`;
- `Competition`;
- one or more canonical participants;
- UTC-normalized scheduled start;
- `EventStatus`;
- optional provider event references.

The model intentionally does **not** hard-code home/away or exactly two participants. This allows tennis, racing, and future outright-style events to share the same canonical identity layer.

Invariants include:

- competition sport equals event sport;
- all participants belong to the event sport;
- participant IDs are unique within the event;
- provider references are unique by provider;
- scheduled timestamps are timezone-aware.

### `Market`

A market has explicit semantics through `MarketKind` and `MarketPeriod` rather than an unstructured provider label.

Initial kinds:

- `MATCH_WINNER_2_WAY`;
- `MATCH_WINNER_3_WAY`;
- `TOTAL_POINTS`;
- `HANDICAP`;
- `SET_WINNER`;
- `OUTRIGHT_WINNER`.

Parameterized total and handicap markets require an exact `Decimal` line. Other current market kinds reject a line. Indexed periods such as set/quarter/period require a positive `period_index`.

Examples that are deliberately distinct:

- regulation-time winner vs full-event winner;
- total 2.5 vs total 3.5;
- first set winner vs second set winner.

### `Selection`

A selection encodes the outcome meaning directly:

- participant;
- draw;
- over;
- under;
- yes;
- no.

Participant selections reference a canonical `ParticipantId`. A provider's strings such as `Home`, `1`, `Arsenal`, or localized equivalents are normalization inputs, not canonical selection semantics.

Optional signed `handicap` is permitted only for participant selections.

### `OddsQuote`

An odds quote contains both canonical identity and source provenance:

- `QuoteId`;
- `ProviderId`;
- canonical `EventId`, `MarketId`, and `SelectionId`;
- exact decimal price greater than `1`;
- source event, market, and selection identifiers;
- optional provider/source timestamp;
- required ingestion timestamp;
- `QuoteStatus`;
- optional trace ID;
- optional raw-source reference.

The arbitrage engine does not need provider payload shapes or labels. Source identifiers are retained for auditability, debugging, and traceability.

### `Opportunity`

Defines the canonical output schema for a theoretical arbitrage opportunity:

- canonical event and market IDs;
- the selected quote IDs;
- implied probability sum below `1`;
- positive theoretical margin;
- detection timestamp;
- lifecycle status.

Phase 3 owns the mathematics that produces this entity. Phase 2 only defines and validates its representation.

### `StakePlan`

Defines the canonical representation of a rounded/executable stake plan and its `StakeAllocation` items.

A plan records:

- opportunity identity;
- ISO-style three-letter currency code;
- bankroll ceiling;
- quote/selection/provider-specific allocations;
- each allocation's expected payout;
- guaranteed payout (the minimum allocation payout);
- guaranteed profit;
- creation timestamp.

The plan validates that total stake does not exceed bankroll and that guaranteed profit equals guaranteed payout minus total staked amount. Phase 3 is responsible for calculating these values correctly.

## Identity boundary

Canonical IDs are generated/resolved outside these value objects. Phase 2 deliberately does not prescribe a UUID, hash, database sequence, or natural-key generation algorithm. Matching/normalization phases may establish those policies later without changing consumers' type contracts.

## Provider independence

Provider-specific information permitted in canonical objects is limited to explicit provenance/reference fields:

- `ProviderId`;
- provider-local source IDs;
- trace/raw-source references.

No downstream calculation should require a provider field name, bookmaker-specific market code, localized selection label, response JSON shape, or authentication detail.

## Validation philosophy

Type hints are not treated as runtime validation. Constructors verify critical ID, enum, timestamp, decimal, tuple-member, uniqueness, and cross-field invariants. Invalid canonical data therefore fails at the boundary where it is constructed rather than propagating deeper into the pipeline.
