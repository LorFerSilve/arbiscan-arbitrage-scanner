# OddsPapi provider candidate

## Status

Selected in Phase 16.1 as the first second-source development target.

**Not production-ready.** Production enablement is blocked pending explicit confirmation of caching, raw/normalized retention, display, and public-fixture rights, and pending completion of the remaining Phase 16 correctness gates.

Selection rationale and candidate comparison: [`phase-16.1-provider-selection.md`](phase-16.1-provider-selection.md).

## Provider role

OddsPapi is modeled as a **transport/source provider**. Bookmakers and exchanges carried inside its payload remain separate **price providers**.

This distinction is mandatory under ADR-0006 and ADR-0012. An OddsPapi observation of Pinnacle is not a new bookmaker merely because The Odds API also reports Pinnacle.

## Official resources reviewed

- REST documentation: https://oddspapi.io/en/docs
- `GET /v4/odds`: https://oddspapi.io/en/docs/get-odds
- `GET /v4/fixtures`: https://oddspapi.io/en/docs/get-fixtures
- `GET /v4/bookmakers`: https://oddspapi.io/en/docs/get-bookmakers
- quota model: https://oddspapi.io/us/docs/requests-and-quota
- WebSocket documentation: https://docs.oddspapi.io/quickstart
- football coverage: https://oddspapi.io/sports/football
- tennis coverage: https://oddspapi.io/sports/tennis
- public terms: https://oddspapi.io/en/legal/terms

Reviewed on 2026-09-17. Provider documentation and terms are external mutable dependencies and must be rechecked before production enablement.

## Current MVP compatibility

The documented feed covers the semantics required by the current ArbiScan MVP:

- football/soccer pre-match full-time result / 1X2;
- tennis pre-match match winner.

Broader OddsPapi markets must remain disabled until their semantics are deliberately introduced by later roadmap work.

## Relevant source fields

The adapter design should preserve at least:

- `fixtureId` as provider event identity;
- participant IDs/names and ordering;
- sport/tournament IDs;
- `startTime`;
- fixture `statusId`/`statusName`;
- top-level `updatedAt`;
- bookmaker slug and bookmaker fixture ID;
- bookmaker active/suspended state;
- bookmaker market ID and market active state;
- bookmaker outcome ID and selection active state;
- `bookmakerChangedAt` when present;
- `changedAt` as the provider-recorded change timestamp;
- decimal price;
- provider-specific maximum-bet `limit` when present, without interpreting it as universally executable account capacity.

Unknown fields/statuses must fail closed where they affect eligibility or semantics.

## Timestamp policy

All documented REST timestamps are UTC ISO-8601.

The adapter must not pretend `bookmakerChangedAt` and `changedAt` have identical provenance:

- `bookmakerChangedAt`: upstream bookmaker-reported change when available;
- `changedAt`: OddsPapi's recorded change time.

Phase 16 implementation must define which timestamp enters canonical freshness evaluation and retain sufficient provenance to audit that choice. Local ArbiScan ingestion time remains independent.

## Rate-limit model

The REST API documents endpoint-specific cooldowns. Current documented examples include:

- odds: 500 ms;
- fixtures: 2000 ms;
- bookmakers: 1000 ms;
- historical odds: 5000 ms.

The account also has a monthly request allowance. Completed error responses can consume quota. Therefore:

- cooldown and quota are separate controls;
- retries must be bounded and quota-aware;
- retrying arbitrary 4xx failures is prohibited;
- account/quota state should be surfaced through provider telemetry when available.

## Credential policy

The REST product uses an API key. No key value may appear in the repository, fixtures, logs, exception text, URLs retained in telemetry, or generated documentation.

The exact environment-variable name will be established during Phase 16.3 and added to `.env.example` with an empty value only after the adapter exists.

## Multi-source overlap

Overlap with The Odds API is expected. This is a deliberate correctness test for Phase 16 rather than something to avoid.

Before mixed-source activation:

- transport-source provenance must be first-class;
- source observation IDs must include transport identity;
- the same bookmaker/selection from two transports must consolidate to one eligible executable price origin;
- equal-time material conflicts must fail closed;
- opportunity evidence must record the chosen transport observation.

## Fixture policy

Until provider rights are clarified:

- do not commit captured live OddsPapi payloads;
- use hand-authored schema-faithful synthetic fixtures for parser scaffolding;
- never include API keys, private account metadata, or opaque data that the public terms do not clearly permit redistributing;
- replace synthetic fixtures with sanitized recorded fixtures only after permission is confirmed.

## Production blockers

The following checklist items remain unresolved from public documentation and require explicit provider confirmation or applicable contractual terms:

- raw payload retention duration;
- normalized/derived odds-data retention rights;
- cache duration and persistence rules;
- dashboard/display permissions for the intended deployment model;
- right to keep sanitized captured responses in a public CI fixture repository;
- any geographic restrictions that apply to API/data usage from Belgium rather than to bookmaker wagering access.

Failure to resolve these items means the provider remains development-only and cannot be marked production-ready.
