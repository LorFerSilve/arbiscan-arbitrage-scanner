# Phase 5 completion record

Status: **Complete pending final CI verification on this completion-record commit**

## Roadmap objective

Phase 5 must prove that ArbiScan's provider abstraction, canonical domain model, and arbitrage mathematics compose into a complete logical pipeline without network access or external infrastructure.

The implemented deterministic path is:

```text
synthetic FakeProvider matrix
    -> provider ingestion
    -> strict Phase 5 normalization
    -> explicit canonical event/market/selection identity
    -> minimal best-price market book
    -> Phase 3 arbitrage evaluation
    -> Opportunity output
```

This is an architecture proof, not a premature implementation of the broader Phase 7 normalization engine, Phase 8 fuzzy/cross-provider matcher, or Phase 9 production market-book builder.

## Exit criterion: complete logical pipeline works without network access

Satisfied.

`run_vertical_slice()` orchestrates the entire network-free path from provider adapters to canonical `Opportunity` values. It consumes only the Phase 4 `ProviderAdapter` contract and the existing Phase 2/3 canonical model and mathematics.

The pipeline requires no:

- outbound network access;
- provider credentials;
- database;
- queue or cache service;
- wall-clock lookup;
- external API fixture server.

All evaluation times, source timestamps, source IDs, canonical IDs, prices, and failures are deterministic fixture data.

## Exit criterion: deterministic fixtures exercise success and failure paths

Satisfied by the Phase 5 synthetic matrix.

### Synthetic Alpha

Covers:

- a mapped 1X2 event participating in a profitable cross-provider arbitrage;
- a complete mapped 1X2 event with no arbitrage;
- a stale snapshot whose prices must not enter an actionable book;
- a suspended market;
- a malformed decimal price.

### Synthetic Beta

Covers:

- the same canonical profitable and non-profitable events through different source IDs;
- complementary prices proving that best-price selection can combine eligible quotes from multiple providers;
- a high-priced lookalike event that intentionally has no canonical mapping and therefore fails closed.

### Synthetic Gamma Outage

Covers a deterministic provider timeout while healthy providers continue through the pipeline. The outage becomes an ingestion diagnostic rather than aborting the scan.

## Explicit identity boundary

Phase 5 introduces a small `CanonicalRegistry` plus `StaticCanonicalIdHooks` for known source-to-canonical mappings.

This mechanism is deliberately strict:

- unknown events are not guessed;
- unknown markets are not guessed;
- unknown selections are not guessed;
- participant selections must reference a participant in the registry and in the corresponding canonical event;
- event/market/selection graph references are validated before use.

The lookalike fixture proves that similar names and attractive odds alone cannot cross the identity boundary.

General aliases, fuzzy participant matching, confidence scoring, rescheduling heuristics, and ambiguity resolution remain Phase 7/8 responsibilities.

## Strict Phase 5 normalization

The narrow normalizer converts only explicitly mapped synthetic source records whose semantics are already known.

It fails closed on:

- missing canonical identity hooks;
- unmapped events, markets, or selections;
- identity conflicts;
- snapshots ingested after the requested `as_of` time;
- future source timestamps;
- stale snapshots;
- inactive/suspended markets and selections;
- unsupported odds formats;
- malformed or non-positive decimal prices;
- source/canonical market ownership conflicts.

Snapshot ingestion time is validated independently from provider source time so replay/as-of evaluation cannot use information that was not yet available at the requested evaluation instant.

Broad odds-format conversion and provider terminology normalization remain Phase 7 work.

## Ingestion isolation and snapshot ownership

`collect_snapshots()` executes adapters through the Phase 4 resilience boundary and isolates provider failures as diagnostics.

Before a fetched snapshot can be associated with an event, ingestion verifies both:

- `snapshot.provider_id == adapter.provider.id`;
- `snapshot.external_event_id == requested SourceEvent.external_id`.

Structurally valid but cached/misrouted snapshots are rejected as malformed responses. Regression tests cover both wrong-provider and wrong-event responses.

## Minimal best-price book

For each canonical Phase 5 market, the vertical-slice service:

1. obtains the expected canonical selections from the registry;
2. considers only normalized eligible quotes for that exact market and selection;
3. deterministically selects the highest decimal price per outcome;
4. reports an incomplete-book diagnostic when any expected outcome is absent;
5. passes exactly one active quote per expected outcome to the existing Phase 3 `evaluate_market()` function;
6. creates an `Opportunity` only from a positive arbitrage evaluation.

The Phase 3 mathematics package is reused unchanged. Provider ingestion and synthetic fixtures do not leak into the mathematics core.

Provider allow/deny policies, settlement-variant alignment, richer construction diagnostics, and production-grade market-book assembly remain Phase 9 work.

## End-to-end integration evidence

`tests/integration/test_phase5_vertical_slice.py` proves that:

- exactly the intended cross-provider event emits an arbitrage opportunity;
- its winning outcome prices come from both Synthetic Alpha and Synthetic Beta;
- a complete non-arbitrage event is evaluated but emits no opportunity;
- the provider timeout is isolated and healthy data still proceeds;
- stale odds are rejected;
- suspended markets are rejected;
- malformed prices are rejected;
- the unmapped lookalike event is rejected;
- incomplete canonical books produce diagnostics rather than false opportunities;
- repeated runs produce equivalent quotes, diagnostics, evaluations, opportunities, and book issues;
- a configured minimum-profit threshold can suppress an otherwise theoretical opportunity.

## Review findings resolved during Phase 5

The pull-request review identified four correctness issues before completion:

1. **Package import cycle:** eagerly exposing synthetic fixtures through the provider package caused fresh-interpreter imports of matching/normalization to fail. The reverse dependency was removed and an import-boundary regression test now executes those imports in a clean interpreter.
2. **Snapshot ownership:** ingestion could previously associate a structurally valid cached/misrouted snapshot with the wrong provider or requested event. Provider and event ownership are now checked explicitly before acceptance.
3. **As-of causality:** a historical source timestamp could previously mask an ingestion timestamp later than the evaluation instant. `ingested_at` is now independently required to be at or before `as_of`.
4. **Participant-selection graph integrity:** a participant selection could reference a participant outside its canonical event. The registry now validates both global participant existence and event membership.

Each finding has dedicated regression coverage and was revalidated through the full repository quality gate.

## Verified quality/security result before this completion-record commit

On Phase 5 head `1d52fcf22487d6f16e19bb330b0f85efb7c96b74`:

- `uv lock --check`: passed;
- Ruff format: **88 files already formatted**;
- Ruff lint: passed;
- strict mypy: **no issues in 58 source files**;
- pytest: **71 tests passed**;
- `pip-audit`: **no known vulnerabilities found**;
- CodeQL Actions: passed;
- CodeQL Python: passed;
- GitHub code-scanning PR check: passed with no new alerts in changed code.

The completion-record commit itself must pass the same repository quality and security gates before PR #7 may be merged.

## Deliberate Phase 5 boundaries

Phase 5 does **not**:

- integrate a real bookmaker or odds-data API;
- perform generic alias/participant normalization;
- convert arbitrary odds formats;
- perform fuzzy cross-provider event matching;
- infer market semantics from provider labels;
- implement a production market-alignment engine;
- persist quote history or opportunities;
- implement alerting or wager execution.

Those concerns remain assigned to later roadmap phases.

## Result

After final CI verification, Phase 5 establishes the first complete deterministic ArbiScan vertical slice. The architecture can ingest multiple provider implementations, isolate a provider outage, reject unsafe source data, resolve only explicit canonical identities, construct a minimal cross-provider book, execute the proven Phase 3 mathematics, and emit only the intended arbitrage opportunity — entirely within CI and without external services.
