# Phase 5 synthetic provider and vertical slice

## Purpose

Phase 5 proves that ArbiScan's Phase 2 canonical model, Phase 3 mathematics, and
Phase 4 provider boundary compose into one deterministic pipeline without a
network, credentials, database, or external service.

The implementation is deliberately narrower than the later production engines.
It proves architecture; it does not pre-implement fuzzy matching, broad odds
format conversion, persistence, or general market alignment.

## Pipeline

```text
FakeProvider matrix
  -> deterministic ingestion
  -> strict synthetic normalization
  -> explicit canonical-ID catalog
  -> best valid quote per expected outcome
  -> Phase 3 evaluate_market()
  -> Opportunity
```

## Synthetic matrix

The default scenario contains three synthetic providers.

`Synthetic Alpha` supplies:

- one profitable cross-provider 1X2 event;
- one complete no-arbitrage 1X2 event;
- one stale snapshot whose prices would otherwise look attractive;
- one suspended market;
- one market containing a malformed decimal price.

`Synthetic Beta` supplies:

- matching source identities for the profitable and no-arbitrage events;
- complementary prices so the profitable event selects best quotes from both
  Alpha and Beta;
- a high-priced lookalike event on a different start time that intentionally has
  no canonical mapping.

`Synthetic Gamma Outage` exposes the same canonical profitable event but fails
its odds-fetch operation with a deterministic timeout under the scenario's
bounded provider policy.

## Identity boundary

Phase 5 uses `StaticCanonicalIdHooks` and `CanonicalRegistry`.

Mappings are explicit. An unknown event, market, or selection returns `None`.
There is no fuzzy string matching and no attempt to infer identity from similar
names. This is intentional: broad participant normalization and confidence-based
cross-provider matching remain Phase 7 and Phase 8 work.

The lookalike fixture demonstrates the fail-closed rule: even extreme odds from
an unmapped event cannot enter a canonical market book.

## Normalization boundary

Phase 5 accepts only source records already marked as decimal odds. It validates:

- explicit event/market/selection identity;
- canonical event start-time compatibility;
- snapshot freshness;
- market and selection activity;
- finite decimal prices greater than 1.

Unknown odds formats are rejected rather than converted. General odds-format and
market-semantic normalization belongs to Phase 7.

## Minimal market-book construction

The vertical-slice service selects the best eligible quote for every expected
canonical selection before calling the Phase 3 mathematics core.

This is intentionally a minimal proof. The production-grade book builder,
provider inclusion policies, richer diagnostics, and settlement-variant
alignment remain Phase 9.

## Failure isolation

Provider errors are captured by the ingestion layer as diagnostics and do not
abort unrelated providers. Source-normalization failures are similarly recorded
and omitted from the canonical book.

Stale, suspended, malformed, incomplete, and unmapped data therefore cannot
create an `Opportunity`.

## Determinism

The scenario uses fixed provider IDs, source IDs, timestamps, prices, event
times, and canonical mappings. Rebuilding the same scenario and running the
pipeline produces equivalent canonical quote/evaluation/opportunity values.

No test requires:

- outbound network access;
- provider credentials;
- system clock access;
- a database;
- external queues or caches.
