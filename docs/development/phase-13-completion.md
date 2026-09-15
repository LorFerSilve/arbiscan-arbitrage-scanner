# Phase 13 — Service/API layer completion record

Phase 13 introduces a stable client-facing application boundary without exposing persistence or provider implementation details.

## Delivered

- immutable typed request/response contracts;
- bounded pagination and event/odds/opportunity filtering;
- stable machine-readable error model;
- health and readiness contracts;
- provider-status, sports, events, current-odds, opportunity-list, opportunity-detail/provenance, safe-configuration, and metrics surfaces;
- an `ApiDataSource` protocol that prevents clients from depending on persistence internals;
- OpenAPI 3.1 route documentation;
- fail-closed deployment policy requiring authentication and rate limiting before non-local exposure;
- scanner-only configuration contract with no execution capability or secret-bearing fields;
- contract/security tests.

## Architecture review

FastAPI was evaluated as the roadmap's recommended HTTP technology. Phase 13 keeps the core transport-neutral instead of adding a runtime web dependency before a network listener is required. This follows the repository dependency policy and preserves a clean adapter boundary for a future FastAPI transport.

## Exit criteria

- clients require no direct access to persistence internals: satisfied by `ApiDataSource` and `ArbiScanApi`;
- API contracts are tested: covered by `tests/unit/test_api_service.py`;
- security boundaries are documented: ADR-0011 and `ApiSecurityPolicy`;
- OpenAPI documentation exists: `arbiscan.api.openapi_document`.
