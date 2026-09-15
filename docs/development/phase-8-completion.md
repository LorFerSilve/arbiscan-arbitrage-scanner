# Phase 8 completion — Cross-provider event matching

- Status: Complete, pending the normal protected-branch merge gate
- Date: 2026-09-15
- Roadmap phase: Phase 8 — Cross-provider event matching
- Pull request: #11

## Objective

Phase 8 determines whether independently sourced provider events refer to the same canonical real-world sporting event before their prices may enter the same downstream analysis boundary.

The implementation is deliberately conservative: false negatives are preferable to false positives, and ambiguity never yields a canonical event identity.

## Deliverables

### 8.1 Normalized identity preparation — complete

`prepare_event_evidence()` bridges Phase 7 and Phase 8.

Before event matching:

- sport is canonical;
- competition must resolve through the explicit Phase-7 competition aliases;
- every participant must resolve through the explicit Phase-7 participant aliases;
- competition ambiguity is explicit;
- participant ambiguity/unknown identity is explicit;
- source event and supplied source competition must be structurally compatible.

No fuzzy participant-name matching is introduced.

Primary implementation: `src/arbiscan/normalization/event_identity.py`.

### 8.2 Hard compatibility filters — complete

`EventMatcher` rejects candidates before scoring when known evidence conflicts:

- sport;
- competition;
- participant set;
- participant ordering under `ORDERED` policy;
- conflicting provider event reference;
- scheduled start outside the configured tolerance;
- round/stage when known on both sides;
- venue when known on both sides.

Primary implementation: `src/arbiscan/matching/event_matcher.py`.

### 8.3 Participant order semantics — complete

The matcher requires an explicit `ParticipantOrderPolicy`:

- `ORDERED` preserves identity-bearing ordering such as football home/away;
- `UNORDERED` allows provider presentation order to differ when participant order is not semantic, such as the covered tennis scenario.

Swapped ordered participants are rejected rather than silently reordered.

### 8.4 Temporal compatibility and reschedules — complete

Baseline thresholds:

- ordinary event start tolerance: 30 minutes;
- exact existing provider-reference reschedule tolerance: 48 hours.

A source event with an exact existing provider event reference may survive a larger reschedule within the configured referenced tolerance. A different external event ID for the same provider is a hard conflict.

The strict quote-normalization boundary was updated after review so a nonzero timestamp delta is accepted downstream only when `MatchedCanonicalIdHooks` carries an explicit Phase-8 `MATCHED` decision for that exact source event and canonical event ID. Legacy/static hooks still require exact source/canonical start times.

### 8.5 Confidence scoring and ambiguity rejection — complete

Confidence uses deterministic integer basis points.

Baseline policy:

- minimum confidence: 8500 bps;
- ambiguity margin: 250 bps;
- an exact ordinary match without optional stage/venue/reference evidence scores 9000 bps;
- a candidate below the threshold is rejected;
- multiple eligible candidates within the ambiguity margin produce `AMBIGUOUS` and no matched event ID.

Candidate decisions retain confidence, start-time delta, provider-reference evidence and explanation notes.

ADR-0008 is the normative policy record for weights, thresholds and hard filters.

### 8.6 Downstream event-identity gate — complete

`MatchedCanonicalIdHooks` wraps existing canonical ID hooks and exposes a canonical event ID only when Phase 8 produced `MATCHED` for the exact source external event ID.

If a decision is absent, `AMBIGUOUS` or `REJECTED`, `normalize_source_snapshot()` receives no canonical event identity and fails closed with `UNMAPPED_EVENT` and zero canonical quotes.

This enforces the roadmap invariant that arbitrage analysis cannot cross an unmatched event boundary.

Primary implementation: `src/arbiscan/matching/hooks.py` plus the guarded compatibility logic in `src/arbiscan/normalization/strict.py`.

## Adversarial fixture coverage

The Phase-8 suite includes explicit regressions for the roadmap's high-risk examples:

| Risk | Regression evidence |
| --- | --- |
| same teams on different dates | start outside tolerance is rejected |
| reserve/youth/women lookalikes | `Manchester United Women` does not collapse to `Manchester United` without explicit alias data |
| repeated tennis matchups | equally plausible repeated matchup yields `AMBIGUOUS` |
| swapped participant ordering | ordered football tuple swap is rejected |
| localized/abbreviated names | Phase-7 aliases resolve canonical participants before matching |
| delayed/rescheduled events | exact provider reference permits bounded reschedule; integration test proves quotes can flow after verified match |
| same-name competitions/clubs | ambiguous competition resolution fails before event candidate scoring |
| provider-reference collision | different external ID for already-known provider is hard rejected |
| round/stage conflict | incompatible stage metadata is hard rejected |
| unverified timestamp drift | legacy/static hook mapping still produces `IDENTITY_MISMATCH` |

## Test and quality evidence

On the fully code-bearing Phase-8 head before documentation-only completion commits, the repository quality runner completed successfully with:

```text
uv lock --check      PASS
Ruff format          PASS
Ruff lint            PASS
strict mypy          PASS — 0 issues in 83 source files
pytest               PASS — 122 tests
pip-audit             PASS — no known vulnerabilities
```

The 122-test suite includes all Phase 0–7 regressions plus the new Phase-8 unit and integration coverage.

## Review correction

Automated review identified one P1 integration defect: the matcher correctly accepted bounded start-time differences, but the existing strict normalization bridge still required exact source/canonical timestamps and would therefore reject the matched event before quote creation.

The correction:

1. `MatchedCanonicalIdHooks` now exposes whether a source event has an explicit verified Phase-8 match to a specific canonical event ID;
2. `normalize_source_snapshot()` relaxes exact timestamp equality only for that verified Phase-8 match;
3. static/legacy mappings retain the prior exact-start invariant;
4. integration regressions prove both the verified-reschedule success path and the unverified mismatch rejection path.

## Exit criteria

- **Confidence thresholds defined and measured against deterministic fixtures:** satisfied. Baseline `8500` minimum and `250` ambiguity margin are explicit and tested. They remain conservative baseline calibration until real multi-provider data exists.
- **Ambiguous events fail closed:** satisfied. `AMBIGUOUS` exposes no canonical event ID.
- **No arbitrage opportunity can cross unmatched event boundaries:** satisfied at the quote-normalization boundary. Only `MATCHED` decisions can expose event IDs through `MatchedCanonicalIdHooks`; otherwise zero canonical quotes are produced.
- **Decisions are explainable:** satisfied through candidate evidence and stable rejection reason codes.
- **Provider-specific aliases remain data, not algorithm branches:** satisfied through Phase-7 normalizers used before Phase-8 matching.

## Explicitly deferred

Phase 8 does not implement:

- best-price market-book construction or cross-provider market alignment (Phase 9);
- persistence of match decisions and calibration history (Phase 11 and later observability work);
- ML/fuzzy matching;
- automatic alias discovery;
- production recalibration from observed multi-provider ground truth.

## Merge gate

This completion record does not bypass repository protections. The exact final PR head including ADR-0008 and this file must pass repository quality and CodeQL checks, and all review conversations must be resolved, before squash merge to `main`.