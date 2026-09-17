# Phase 16.3 completion — OddsPapi second provider adapter

Date: 2026-09-17

## Scope

Phase 16.3 adds the selected second-source development adapter, OddsPapi, behind the
existing `ProviderAdapter` contract. It does **not** production-enable the provider
and it does not consume the Phase 16.4 fixture/conformance dependency.

## Completed implementation

1. Added `OddsPapiProvider` and `OddsPapiConfig` with secret-safe configuration.
2. Added REST discovery for supported sports, tournaments, and fixtures.
3. Added pre-match odds snapshot parsing through the provider-neutral source models.
4. Restricted eligible semantics to the current ArbiScan MVP: football full-time
   result / 1X2 and tennis match winner.
5. Added strict structural validation for every field that affects event identity,
   market semantics, quote eligibility, freshness, or price.
6. Preserved transport-source identity as `provider:oddspapi` while bookmaker quotes
   reuse the existing Phase-6 price-origin namespace for exact bookmaker-slug
   overlaps. This prevents the same bookmaker from becoming two executable legs
   merely because two aggregators observed it.
7. Defined the OddsPapi freshness policy: prefer `bookmakerChangedAt`; fall back to
   `changedAt`. Selection-level source timestamps are retained by emitting one
   provider-neutral source-market observation per selection quote.
8. Fail closed on non-pre-match fixture states by suspending all quote observations.
9. Added shared provider-error translation: authentication/authorization and ordinary
   client errors are non-retryable; HTTP 429 and transient 5xx failures are
   retryable; transport failures remain generic and secret-free.
10. Added health validation and account request-allowance mapping to
    `RateLimitSnapshot`.
11. Added the empty `ODDSPAPI_API_KEY` placeholder to `.env.example`.
12. Added hand-authored, schema-faithful unit payloads only. No captured provider
    payload or real credential is committed.

## Safety and compatibility decisions

### Development-only gate

The public provider terms do not yet establish the project's required raw-data
retention, normalized-data retention, display, caching, and public-fixture rights.
The adapter therefore remains development-only. Phase 16.3 does not change that
production-readiness decision.

### Existing bookmaker identifier namespace

The first real provider currently emits bookmaker identities such as
`bookmaker:the-odds-api:pinnacle`. Renaming those IDs in the same change would create
an unrelated persistence/API migration. OddsPapi therefore deliberately emits the
same existing ID for the same exact bookmaker slug. Despite the historical namespace
name, it functions as the shared price-origin identity; OddsPapi transport identity
is retained separately.

A future dedicated migration may rename that namespace, but Phase 16 overlap safety
does not require a cosmetic ID migration.

### Market catalogue instead of fixed IDs

OddsPapi documentation is mutable and provider-authored material currently shows
different IDs for equivalent market families in different examples. The adapter uses
`/v4/markets` metadata and semantic family names, period/type constraints, sport, and
outcome cardinality rather than assuming one eternal numeric market ID.

## Test coverage added

The Phase 16.3 unit suite covers:

- API-key redaction from configuration/telemetry;
- football and tennis sport discovery;
- tournament and fixture discovery;
- filtering of unsupported market families;
- bookmaker price-origin preservation;
- per-selection freshness timestamp selection;
- pre-match-only fail-closed behavior;
- account quota conversion;
- retryability boundaries for 429 versus ordinary 4xx failures;
- malformed health payload handling.

All test payloads are synthetic and hand-authored from the public schema. Formal
shared-provider conformance fixtures remain intentionally unimplemented here.

## Handoff

Phase 16.3 is complete at the adapter boundary.

The next roadmap dependency is **Phase 16.4 — fixtures and provider conformance**:

- add reusable schema-faithful OddsPapi fixture files within the provider-rights
  policy;
- exercise `OddsPapiProvider` through the shared provider contract conformance suite;
- add parser regressions for malformed/edge payloads;
- keep normal CI independent of live external APIs and credentials.

Phase 16.5 should then validate cross-source event, market, selection, and bookmaker
matching against overlapping The Odds API observations.
