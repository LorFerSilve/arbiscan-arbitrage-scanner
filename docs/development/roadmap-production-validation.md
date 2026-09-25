# ArbiScan Production Validation Roadmap

This document restructures the development priorities after architecture review. The focus shifts from broad feature expansion toward proving a complete, reliable arbitrage detection pipeline.

## Strategic goal

Build one fully validated path:

```
Provider data
    -> ingestion
    -> normalization
    -> event matching
    -> market alignment
    -> arbitrage detection
    -> audit record
    -> opportunity output
```

Correctness, traceability and deterministic behaviour take priority over adding more sports or market types.

## Phase 19 — Core validation completion

Objective: finish the internal pipeline validation before further expansion.

Tasks:

- complete internal validation paths;
- ensure domain invariants have regression tests;
- verify deterministic arbitrage calculations;
- document architecture boundaries;
- verify CI quality gates.

## Phase 20 — Multi-provider production pipeline

Objective: enable real arbitrage detection using independent odds sources.

Tasks:

- activate a second production provider;
- validate provider contracts;
- add integration fixtures;
- handle rate limits and provider failures;
- preserve complete quote provenance.

## Phase 21 — Event matching and market compatibility

Objective: prevent false arbitrage caused by incorrect semantic matching.

Tasks:

- canonical participant resolution;
- event confidence scoring;
- market compatibility validation;
- reject ambiguous matches;
- preserve matching explanations.

## Phase 22 — Persistence and replay system

Objective: make opportunities reproducible and auditable.

Tasks:

- store quote provenance;
- store normalized market state;
- store detected opportunities;
- enable historical replay;
- support regression testing from recorded data.

## Phase 23 — Operational observability

Track:

- provider latency;
- quote freshness;
- matching confidence;
- normalization failures;
- detection rate;
- false positives;
- dropped opportunities.

## Phase 24 — MVP consolidation

Prioritize:

1. Football match winner markets.
2. Tennis match winner markets.
3. Additional markets only after full validation.

Deferred:

- motorsport/F1;
- exchange BACK/LAY;
- complex outright markets.

## Future expansion

After MVP validation:

- additional providers;
- more sports;
- more market types;
- exchange integrations;
- advanced analytics.
