# ADR-0008 — Fail-closed cross-provider event matching

- Status: Accepted
- Date: 2026-09-15
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

ArbiScan must determine whether events obtained from different odds sources refer to the same real-world sporting event before their prices can ever participate in one canonical market book. This is a correctness-critical boundary: a false-positive event match can fabricate an arbitrage opportunity between prices that settle on different events.

Provider event identifiers are source-local. Participant names, competition labels and scheduled start times can vary between providers because of abbreviations, localization, clock differences, rescheduling, data latency or provider-specific presentation. Names alone are therefore not event identity.

Phase 7 already established explicit fail-closed normalization for sport, competition and participant semantics. Phase 8 consumes those canonical identities; it does not introduce fuzzy text matching as a shortcut around unresolved normalization.

## Decision

ArbiScan uses a deterministic staged event matcher with explicit `MATCHED`, `AMBIGUOUS` and `REJECTED` outcomes.

### 1. Identity preparation is mandatory

Before event candidates are scored:

- the source sport is already canonical;
- the source competition must resolve to one canonical `CompetitionId` through Phase-7 alias data;
- every source participant must resolve to one canonical `ParticipantId` through Phase-7 alias data;
- unknown or ambiguous competition/participant resolution makes the event ineligible for matching.

No fuzzy name similarity is used by the Phase-8 matcher.

### 2. Hard compatibility filters precede confidence scoring

A canonical candidate is rejected before scoring when any known identity-bearing evidence conflicts:

- sport differs;
- competition differs;
- participant set differs;
- participant ordering differs when the caller explicitly declares order identity-bearing;
- the same provider is already attached to the canonical event through a different external event ID;
- scheduled-start delta exceeds the applicable tolerance;
- round/stage conflicts when known on both sides;
- venue conflicts when known on both sides.

A hard incompatibility can never be offset by a high score in another field.

### 3. Participant order semantics are explicit

`ParticipantOrderPolicy.ORDERED` means tuple order is identity-bearing. This is appropriate where the source/canonical contract encodes semantics such as football home/away ordering.

`ParticipantOrderPolicy.UNORDERED` means the participant set is identity-bearing but presentation order is not. This is appropriate for sources/markets such as tennis where player order may be arbitrary.

The matcher does not silently infer which policy applies from participant names.

### 4. Time tolerances

Baseline configuration:

- ordinary start-time tolerance: **30 minutes**;
- exact existing provider-event-reference tolerance: **48 hours**.

The wider referenced tolerance exists for verified reschedules: if the canonical event already carries the exact same provider event ID, that durable identity evidence can survive a materially changed scheduled start. A conflicting provider reference is instead a hard rejection.

The quote-normalization boundary continues to require exact scheduled-start equality for legacy/static mappings. A nonzero start-time difference is accepted downstream only when `MatchedCanonicalIdHooks` carries an explicit Phase-8 `MATCHED` decision for that exact source event and canonical `EventId`.

### 5. Deterministic confidence policy

Confidence is represented in integer basis points (`0..10000`) rather than floating-point arithmetic.

Baseline evidence weights:

| Evidence | Weight |
| --- | ---: |
| sport exact | 500 bps |
| competition exact | 1500 bps |
| canonical participants exact | 4500 bps |
| participant-order policy satisfied | 500 bps |
| time proximity | 0–2000 bps |
| round/stage exact when available | +400 bps |
| venue exact when available | +300 bps |
| exact existing provider event reference | +1000 bps |

The result is capped at 10000 bps.

Baseline acceptance policy:

- minimum confidence: **8500 bps**;
- ambiguity margin: **250 bps**.

If no candidate reaches the minimum, the result is `REJECTED`. If two or more eligible candidates remain within 250 bps of the best candidate, the result is `AMBIGUOUS`; no canonical event ID is exposed.

These thresholds are an initial conservative calibration derived from the current deterministic fixture set. They are not claimed to be statistically optimal. Real multi-provider observations must be collected before changing them, and any relaxation requires adversarial regression evidence.

### 6. Explanations are retained

Every surviving candidate records:

- confidence;
- start-time delta;
- whether an exact provider reference was used;
- textual evidence notes.

Rejected candidates/preparation steps emit stable reason codes. Matching therefore remains explainable and auditable rather than producing only a boolean.

### 7. Matching gates canonical quote creation

A provider event is allowed to expose a canonical event ID to `normalize_source_snapshot()` only through a `MATCHED` Phase-8 decision when the Phase-8 gate is used.

`AMBIGUOUS`, `REJECTED` and absent decisions resolve to no event ID and therefore produce `UNMAPPED_EVENT`, with no canonical quotes.

This is the binding enforcement of the invariant that an arbitrage opportunity cannot cross an unmatched event boundary.

## Rationale

False-positive event matches are materially more dangerous than false negatives. Missing one potential opportunity only reduces coverage; combining prices from different fixtures can create a fictitious opportunity that appears mathematically valid.

The staged design therefore separates identity compatibility from confidence. Confidence can rank compatible candidates, but it cannot override a contradiction in sport, competition, participant identity, participant order, provider-reference identity, stage, venue or allowed temporal bounds.

Using canonical IDs from Phase 7 also keeps provider naming conventions out of the matching algorithm and allows manual alias improvements without embedding provider-specific string rules in core logic.

## Consequences

### Positive

- ambiguous event relationships fail closed;
- same participants on different dates are not conflated;
- ordered and unordered sports/source semantics are modeled explicitly;
- exact provider IDs can support verified reschedules without weakening legacy mappings;
- matching decisions are deterministic and explainable;
- downstream quote creation is explicitly gated on a successful match;
- later Phase-9 market-book construction can assume event identity has already passed this boundary.

### Negative / trade-offs

- conservative thresholds intentionally create false negatives;
- alias/catalog coverage remains operationally important;
- round/stage and venue currently use optional matching side-car metadata because those fields are not yet part of the canonical `Event` schema;
- confidence weights are heuristic baseline policy, not a learned/statistically calibrated model;
- persistence of match decisions and long-term calibration telemetry are deferred to later persistence/observability phases.

## Alternatives considered

### Fuzzy participant/event name similarity

Rejected as a core identity mechanism because similar names can refer to reserve, youth, women, localized or same-name clubs. Phase 7 explicit aliases must establish participant identity first.

### Names plus start time only

Rejected because repeated matchups, tournaments, same-name clubs and reschedules make that evidence insufficiently reliable.

### Provider event IDs only

Rejected because provider IDs are generally source-local and not available as cross-provider identity keys. They remain strong evidence when a canonical event already stores a reference for the same provider.

### Always require exact timestamps

Rejected because small provider clock differences and real reschedules are legitimate. Instead, tolerance is bounded and only verified Phase-8 decisions may carry non-exact times through quote normalization.

### Learned/ML matcher

Rejected for the correctness-critical baseline. The deterministic model is inspectable, reproducible and testable. A future learned signal could only be considered as additional evidence behind the same fail-closed invariants and would require a separate decision.

## Revisit triggers

Revisit this ADR when:

- real multi-provider production data supports measured false-positive/false-negative calibration;
- canonical `Event` gains first-class round/stage or venue fields;
- sports with fundamentally different participant/event identity semantics are added;
- provider cross-reference networks become available;
- persistence/observability enables longitudinal matcher-quality measurement;
- any proposal would allow low-confidence or ambiguous matches to reach arbitrage analysis.