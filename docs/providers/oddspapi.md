# OddsPapi provider candidate

## Status

Selected in Phase 16.1 as the first second-source development target.

Phases 16.3 through 16.8 now provide and validate a strict REST adapter behind the
shared `ProviderAdapter` boundary, cross-source normalization/matching, overlap-safe
coexistence, per-source observability, and an explicit staged transport enablement
gate.

The adapter remains **production-blocked**. The Phase 16 engineering gates are
complete, but production activation still requires explicit confirmation of caching,
raw/normalized retention, display, public-fixture, and applicable geographic/data-use
rights. Technical completion must not be interpreted as provider/legal approval.

Selection rationale and candidate comparison:
[`phase-16.1-provider-selection.md`](phase-16.1-provider-selection.md).

## Provider role

OddsPapi is modeled as a **transport/source provider**. Bookmakers and exchanges
carried inside its payload remain separate **price providers**.

This distinction is mandatory under ADR-0006 and ADR-0012. An OddsPapi observation
of Pinnacle is not a new bookmaker merely because The Odds API also reports Pinnacle.

Phase 16.3 therefore reuses the existing Phase-6 bookmaker price-origin namespace for
exact bookmaker-slug overlaps. This preserves current persisted/test identities and,
more importantly, makes observations of the same bookmaker consolidate as one
executable price origin. Renaming that historical namespace is a separate migration,
not a provider-adapter concern.

## Official resources reviewed

- REST documentation: https://oddspapi.io/en/docs
- `GET /v4/sports`: https://oddspapi.io/en/docs/get-sports
- `GET /v4/tournaments`: https://oddspapi.io/en/docs/get-tournaments
- `GET /v4/fixtures`: https://oddspapi.io/en/docs/get-fixtures
- `GET /v4/markets`: https://oddspapi.io/en/docs/get-markets
- `GET /v4/odds`: https://oddspapi.io/en/docs/get-odds
- `GET /v4/bookmakers`: https://oddspapi.io/en/docs/get-bookmakers
- `GET /v4/account`: https://oddspapi.io/en/docs/get-account
- quota model: https://oddspapi.io/us/docs/requests-and-quota
- WebSocket documentation: https://docs.oddspapi.io/quickstart
- football coverage: https://oddspapi.io/sports/football
- tennis coverage: https://oddspapi.io/sports/tennis
- public terms: https://oddspapi.io/en/legal/terms

Reviewed on 2026-09-17. Provider documentation and terms are external mutable
dependencies and must be rechecked before production enablement.

## Phase 16.3 adapter scope

The REST adapter implements:

- supported-sport discovery;
- tournament discovery;
- fixture discovery;
- pre-match odds snapshots;
- strict source-schema validation;
- shared provider error translation;
- injectable HTTPS transport and bounded per-request timeout;
- health checks;
- account request-allowance telemetry;
- exact transport/source versus bookmaker/price-provider separation.

WebSocket streaming is deliberately not exposed yet even though OddsPapi offers a
WebSocket product. `ODDS_STREAMING` remains undeclared until ArbiScan has an explicit
streaming contract implementation and corresponding correctness tests.

## Current MVP compatibility

The documented feed covers the semantics required by the current ArbiScan MVP:

- football/soccer pre-match full-time result / 1X2;
- tennis pre-match match winner.

Broader OddsPapi markets remain disabled. The adapter resolves eligible market
families from `/v4/markets` rather than relying on a single hard-coded market ID,
because the provider documents multiple IDs for some market families and external
documentation is mutable.

Unsupported market families are ignored fail-closed. A known fixture status other
than pre-match is structurally valid, but all emitted source quotes are suspended so
live/finished data cannot enter the current pre-match execution path.

## Phase 17.2 football regulation totals

Phase 17.2 extends the development adapter to recognize the provider catalog family
`Over Under Full Time` only when its structured semantics are compatible:

- football sport;
- `period=fulltime`;
- `marketType=totals`;
- non-player market;
- positive catalog `handicap`/line;
- exactly the outcomes `Over` and `Under`.

The catalog handicap is retained as exact `SourceMarket.line`. The adapter does not
itself declare every such line safe for arbitrage: strict canonical normalization
applies ADR-0014 and enables only regulation half-goal (`x.5`) totals. Integer and
quarter lines therefore remain fail-closed.

The adapter's non-prematch suspension path also preserves structured Phase-17
parameters instead of discarding the line while changing eligibility state.

This technical extension does **not** change the production decision below. OddsPapi
remains production-blocked until the provider-specific rights questions are resolved.

## Phase 17.3 football Asian handicap

Phase 17.3 recognizes the development catalog family `Asian Handicap` for football
when the market is non-player, uses `period=fulltime`, and exposes exactly outcomes
`1` and `2`.

The catalog handicap is interpreted as the participant-1 line:

- outcome `1` receives `handicap`;
- outcome `2` receives `-handicap`;
- `SourceMarket.line` receives the catalog handicap.

This matches ArbiScan's canonical participant-1 anchor and lets strict normalization
verify market direction and each participant-side handicap independently.

The adapter preserves integer and quarter lines as structured source semantics, but
the canonical support policy permits only regulation-time half-goal lines into the
generic arbitrage/stake pipeline. OddsPapi's documented settlement vocabulary
includes PUSH, HALF-WIN and HALF-LOSS, so those richer variants are deliberately not
flattened into ordinary two-outcome payout math.

This market-family extension does **not** change the provider's production status.
OddsPapi remains production-blocked until the independent rights/licensing questions
below are resolved.

## Relevant source fields

The adapter preserves or validates at least:

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
- decimal price.

Provider-specific maximum-bet `limit` remains deliberately uninterpreted in Phase
16.3; it must not be treated as universally executable account capacity.

Unknown statuses or malformed fields fail closed where they affect eligibility or
semantics.

## Timestamp policy

All documented REST timestamps are UTC ISO-8601.

The adapter does not pretend `bookmakerChangedAt` and `changedAt` have identical
provenance:

- `bookmakerChangedAt`: upstream bookmaker-reported change when available;
- `changedAt`: OddsPapi's recorded change time.

For canonical freshness, Phase 16.3 uses `bookmakerChangedAt` when it is present and
falls back to `changedAt` otherwise. This is conservative: a provider-observation
timestamp cannot make an older bookmaker-reported quote appear fresher.

OddsPapi records timestamps at selection granularity while ArbiScan's provider-neutral
`SourceMarket` timestamp is market-scoped. The adapter therefore emits one source
market observation per bookmaker/market/outcome/player quote. Each observation keeps
its own chosen source timestamp, while later identity hooks may map those observations
back to one canonical market. Local ArbiScan ingestion time remains independent.

## Rate-limit model

The REST API documents endpoint-specific cooldowns. Current documented examples
include:

- odds: 500 ms;
- fixtures: 2000 ms;
- bookmakers: 1000 ms;
- historical odds: 5000 ms.

The account also has a request allowance. Completed error responses can consume
quota. Therefore:

- cooldown and quota are separate controls;
- retries must be bounded and quota-aware;
- arbitrary 4xx failures are never marked retryable;
- HTTP 429 and transient 5xx failures may be retried by the shared resilience layer;
- account request-limit/request-count state is surfaced as provider rate-limit
  metadata when available.

## Credential policy

The REST product uses an API key in the `apiKey` query parameter.

The ArbiScan environment variable is:

```text
ODDSPAPI_API_KEY
```

Only an empty placeholder is committed in `.env.example`. No key value may appear in
repository fixtures, logs, exception text, retained telemetry URLs, or generated
documentation. The adapter configuration excludes the API key from `repr` and
comparison output.

## Multi-source overlap

Overlap with The Odds API is expected. This is a deliberate correctness test for
Phase 16 rather than something to avoid.

For mixed-source activation, Phases 16.2 through 16.8 now enforce and test:

- first-class transport-source provenance;
- collision-safe source observation IDs containing transport identity;
- consolidation of the same bookmaker/selection across transports into one eligible
  executable price origin;
- fail-closed equal-time material conflicts;
- opportunity evidence recording the selected transport observation;
- source-specific normalization/matching/conflict telemetry;
- explicit adapter enablement before a transport can be polled;
- deterministic rollback to a primary-only source set.

These guarantees satisfy the Phase 16 technical coexistence gate. They do not resolve
the independent production-rights questions below.

## Fixture policy

Until provider rights are clarified:

- do not commit captured live OddsPapi payloads;
- use hand-authored schema-faithful synthetic payloads for parser tests;
- never include API keys, private account metadata, or opaque data that the public
  terms do not clearly permit redistributing;
- replace synthetic fixtures with sanitized recorded fixtures only after permission is
  confirmed.

Phase 16.3 unit tests follow this policy. Formal reusable provider fixtures and shared
conformance coverage are intentionally deferred to Phase 16.4.

## Production blockers

The following checklist items remain unresolved from public documentation and require
explicit provider confirmation or applicable contractual terms:

- raw payload retention duration;
- normalized/derived odds-data retention rights;
- cache duration and persistence rules;
- dashboard/display permissions for the intended deployment model;
- right to keep sanitized captured responses in a public CI fixture repository;
- any geographic restrictions that apply to API/data usage from Belgium rather than
  to bookmaker wagering access.

Failure to resolve these items means the provider remains development-only and cannot
be marked production-ready.


## Phase 16.8 staged-enablement policy

`TransportSourceEnablementPolicy` is the application-boundary gate for transport
participation. Disabled adapters are filtered before the realtime ingestion runtime,
so they cannot issue requests, contribute quotes, or affect provider health state.

The supported rollout pattern is:

1. keep The Odds API as the required primary transport;
2. run OddsPapi only in deterministic fixture/test or otherwise explicitly approved
   environments while production-rights questions remain open;
3. after provider/legal approval, enable the second transport explicitly with the
   staged multi-source policy;
4. if operational or semantic evidence regresses, restore the primary-only policy.
   Rollback does not require changes to arbitrage mathematics or canonical models.

Phase 16.8 regression tests prove both the dual-source state and the primary-only
rollback state using the two real adapter schemas.

## Production activation decision

**Current decision: not approved for production activation.**

The unresolved items in the Production blockers section remain external prerequisites.
Until they are resolved and recorded, production-like composition should keep OddsPapi
out of the enabled transport set. This is intentionally stricter than technical
integration readiness.
