# ADR-0007 — Use explicit, fail-closed semantic normalization

- Status: Accepted
- Date: 2026-09-15
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Phase 7 moves ArbiScan from provider-specific terminology toward canonical sport, competition, participant, market, and odds semantics. This layer directly influences which prices may later be compared. An incorrect normalization can therefore create a false comparison even when the arbitrage mathematics itself is correct.

Provider terminology is not globally unique. Names such as `Premier League`, `United`, `Winner`, or `Match Winner` can represent different entities or settlement rules depending on sport, provider, region, competition, season, event context, and market period.

Text similarity alone is insufficient for correctness. Likewise, market labels that look similar may settle differently: regulation-time winner is not qualification winner, first-half result is not full-time result, and different total/handicap lines are different canonical markets.

## Decision

ArbiScan normalization is deterministic and fail-closed.

### Explicit resolution outcomes

Semantic resolution returns one of:

- `RESOLVED` — exactly one canonical result is supported by the supplied alias data and context;
- `UNKNOWN` — no safe result can be established, including cases where required context is absent;
- `AMBIGUOUS` — multiple canonical candidates remain compatible.

Only `RESOLVED` results may be consumed as canonical semantics.

### Conservative text normalization

Alias keys use Unicode NFKC normalization, case folding, whitespace trimming, and whitespace collapsing. The normalizer does **not** automatically remove accents, punctuation, hyphens, gender/age markers, reserve-team markers, or meaningful suffixes.

Localized names and abbreviations must be explicit alias data rather than products of fuzzy text rewriting.

### Context-aware aliases

Competition and participant aliases may be constrained by contextual dimensions such as:

- sport;
- provider;
- region;
- season;
- parent competition;
- competition identity;
- participant kind.

Missing required context does not authorize a guess.

### Canonical market semantics

Market normalization treats settlement semantics and parameters as identity-bearing data. Canonical meaning includes, where applicable:

- market kind;
- period;
- exact `Decimal` line;
- period/set/quarter index.

`MATCH_WINNER_3_WAY` in regulation and `QUALIFICATION_WINNER` are distinct canonical market kinds. Total `2.5` and total `3.5`, or handicap `-1.0` and `-1.5`, remain distinct.

### Odds normalization

Internal odds remain decimal. Decimal, fractional, American, and implied-probability source formats are converted with `Decimal` arithmetic under a private fixed 60-digit context. Conversion does not depend on a caller's ambient Decimal precision.

Implied-probability source values are defined as probabilities strictly in `(0, 1)`; percentage-looking values are rejected instead of guessed. Decimal arithmetic signals, including overflow, are converted to normalization failures rather than leaking out of the source-data boundary.

### Event matching boundary

Phase 7 does **not** decide whether two provider events represent the same real-world event. Cross-provider event identity remains the responsibility of Phase 8. The existing strict quote bridge therefore continues to require explicit canonical event/market/selection identity hooks while consuming Phase-7 odds normalization.

## Rationale

False-positive canonicalization is more dangerous than a false negative because downstream arbitrage detection assumes canonical identities and settlement semantics are already trustworthy. Explicit unresolved states make uncertainty visible and auditable instead of burying it in heuristic scores.

Separating semantic normalization from event matching also keeps two different concerns independently testable: terminology can be normalized without asserting real-world event identity, while Phase 8 can use normalized signals as evidence in a staged matching process.

## Consequences

### Positive

- unknown or ambiguous terminology cannot silently become comparable market data;
- alias behavior is reproducible and reviewable;
- localized names and abbreviations can be expanded without changing matching algorithms;
- market period and line semantics are explicit;
- odds conversion is deterministic across process Decimal settings;
- Phase 8 receives normalized signals without inheriting fuzzy identity guesses.

### Negative / trade-offs

- new aliases and provider terminology require maintained catalog data;
- fail-closed behavior can initially increase false negatives;
- aliases that are safe in one context may remain unresolved when callers omit that context;
- broad market support requires explicit canonical semantics rather than generic string mapping.

## Alternatives considered

### Global fuzzy-string matching

Rejected because names are not unique and small textual differences may encode material entity distinctions.

### Aggressive text canonicalization

Rejected because stripping punctuation, accents, suffixes, gender/age markers, or team qualifiers can collapse distinct participants.

### Provider-specific normalization inside the arbitrage engine

Rejected because the arbitrage core must remain provider-independent and consume only canonical semantics.

### Combine semantic normalization and event matching

Rejected because terminology equivalence is evidence for event identity, not proof of it. Phase 8 requires additional temporal, participant-order, competition, and ambiguity checks.

## Revisit triggers

Revisit this decision if:

- measured normalization coverage requires a probabilistic resolver;
- a curated alias store moves from static configuration to persistence;
- new market families require richer parameter objects than `line` and `period_index`;
- an approved confidence model can preserve the same fail-closed invariant with explicit thresholds and explanations.