# Phase 16.4 completion — fixtures and provider conformance

Date: 2026-09-17

## Scope

Phase 16.4 closes the fixture/conformance gate for the OddsPapi development adapter.
It does not enable the provider for production and does not perform the cross-source
normalization and event-matching work assigned to Phase 16.5.

## Completed implementation

1. Added a reusable `tests/fixtures/providers/oddspapi/` corpus.
2. Kept every OddsPapi fixture hand-authored and schema-faithful; no authenticated
   provider response, live credential, or private account metadata is committed.
3. Added `tests.support.oddspapi.FixtureHttpTransport`, which routes all adapter HTTP
   calls to local fixture bytes and records request metadata without external I/O.
4. Exercised `OddsPapiProvider` through the repository's shared
   `ProviderContractCase` / `assert_provider_conformance` suite.
5. Added fixture-driven parser regressions for:
   - unsupported market families being ignored fail-closed;
   - unknown fixture statuses becoming `MALFORMED_RESPONSE`;
   - odds/discovery participant identity drift being rejected before quote emission;
   - invalid JSON being translated into the shared provider error taxonomy.
6. Added a corpus-level guard that rejects credential/account-secret markers from the
   committed fixture directory.
7. Kept normal CI completely independent of OddsPapi availability and credentials.

## Conformance evidence

The shared provider contract now verifies the second real transport implementation for:

- canonical provider identity;
- deterministic sport discovery;
- deterministic competition discovery;
- deterministic event discovery;
- deterministic odds snapshots;
- provider health;
- rate-limit metadata;
- explicit non-streaming behavior through the shared `UNSUPPORTED` error taxonomy.

The same contract remains used by The Odds API, so both real transport adapters are
held to one provider-neutral behavioral boundary.

## Fixture safety policy

The reusable fixtures remain synthetic because provider retention, caching, display,
and public-fixture redistribution rights are still unresolved. The fixture transport
therefore validates ArbiScan's adapter contract without creating a new data-rights
assumption.

Phase 16.4 does not change the provider's development-only status.

## Handoff

Phase 16.4 is complete. The next roadmap dependency is **Phase 16.5 — normalization
and event-matching validation**.

Phase 16.5 should validate only the currently supported MVP semantics across the two
real transport sources:

- sport and competition identity;
- participant identity and ordering;
- start-time/reschedule behavior;
- canonical event matching;
- football 1X2 / tennis winner market semantics;
- selection semantics;
- status and freshness semantics;
- bookmaker overlap identity without duplicate executable price origins.

Unknown or ambiguous mappings must continue to fail closed.
