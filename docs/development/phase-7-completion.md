# Phase 7 completion — Normalization engine

- Status: Complete, pending the normal protected-branch merge gate
- Date: 2026-09-15
- Roadmap phase: Phase 7 — Normalization engine
- Pull request: #10

## Objective

Phase 7 converts heterogeneous provider terminology and odds encodings into deterministic canonical semantics while failing closed on unknown or ambiguous meaning.

Cross-provider event identity is deliberately excluded and remains Phase 8.

## Deliverables

### 7.1 Sport normalization — complete

- explicit sport aliases;
- optional provider-specific aliases;
- deterministic `RESOLVED`, `UNKNOWN`, or `AMBIGUOUS` outcomes;
- no fuzzy sport guessing.

Primary implementation: `src/arbiscan/normalization/aliases.py`.

### 7.2 Competition normalization — complete

- explicit aliases and abbreviations;
- provider context;
- region/localization context;
- season context;
- parent-competition hierarchy;
- same-name competitions remain ambiguous without sufficient context.

Primary implementation: `CompetitionAlias` / `CompetitionNormalizer`.

### 7.3 Participant normalization — complete

- explicit aliases and abbreviations;
- localized aliases;
- sport and participant-kind context;
- provider, competition, and region context;
- ambiguous short names fail closed;
- no suffix/gender/reserve-team stripping or fuzzy identity assertion.

Primary implementation: `ParticipantAlias` / `ParticipantNormalizer`.

### 7.4 Market normalization — complete

Canonical semantic resolution includes:

- market kind;
- market period;
- exact Decimal line;
- indexed period/set/quarter context;
- optional provider-specific aliases.

The canonical model now explicitly distinguishes `QUALIFICATION_WINNER` from match-winner markets.

Coverage proves distinctions including:

- regulation result vs qualification winner;
- full-time vs first-half result;
- total 2.5 vs total 3.5;
- handicap -1.0 vs handicap -1.5;
- indexed set-winner markets.

Primary implementation: `src/arbiscan/normalization/markets.py`.

### 7.5 Odds format normalization — complete

Supported source formats:

- decimal;
- fractional;
- American;
- implied probability.

Conversions use a private 60-digit Decimal context and are independent of ambient process precision. Invalid inputs and Decimal arithmetic signals are converted to `OddsNormalizationError`.

The existing strict source-to-canonical bridge now uses this normalization for all currently modeled source odds formats. One malformed/extreme quote is rejected with `MALFORMED_PRICE` without aborting other valid selections in the snapshot.

Primary implementation: `src/arbiscan/normalization/odds.py` and `src/arbiscan/normalization/strict.py`.

## Architectural decisions

ADR-0007 records the binding fail-closed normalization policy:

- explicit alias data over fuzzy guessing;
- conservative text-key normalization;
- context-aware resolution;
- explicit unresolved states;
- market settlement semantics and parameters are identity-bearing;
- deterministic Decimal odds conversion;
- semantic normalization remains separate from Phase-8 event matching.

## Test and quality evidence

On the fully code-bearing Phase-7 head, the repository quality runner completed successfully with:

```text
uv lock --check      PASS
Ruff format          PASS
Ruff lint            PASS
strict mypy          PASS — 0 issues in 76 source files
pytest               PASS — 105 tests
pip-audit             PASS — no known vulnerabilities
```

The 105-test suite includes all existing Phase 0–6 regressions plus Phase-7 coverage for aliases, localization, ambiguity, hierarchy/season context, market periods/lines, all source odds formats, Decimal-context independence, arithmetic overflow containment, and strict-bridge failure isolation.

## Review corrections

Automated review identified two odds-normalization correctness risks:

1. non-terminating conversions depended on the caller's ambient Decimal context;
2. extreme Decimal arithmetic could leak `decimal.Overflow` and abort a snapshot.

Both were corrected and covered by regressions before completion evidence was recorded.

## Exit criteria

- **Canonicalization is deterministic:** satisfied through exact alias/context lookup and private-context Decimal conversion.
- **Unknown semantics are explicit/rejected:** satisfied through `UNKNOWN` / `AMBIGUOUS` resolution states and strict source-price rejection.
- **Normalization has broad fixture coverage:** satisfied by the Phase-7 unit/integration regressions and the unchanged Phase 5/6 vertical-slice suite.

## Explicitly deferred

Phase 7 does not implement:

- cross-provider event matching or confidence scoring (Phase 8);
- fuzzy event identity;
- best-price market-book construction (Phase 9);
- cross-provider completeness policy (Phase 9).

## Merge gate

This record does not bypass repository protections. The exact final PR head, including this completion document, must still pass repository quality and CodeQL checks and have all review conversations resolved before squash merge to `main`.