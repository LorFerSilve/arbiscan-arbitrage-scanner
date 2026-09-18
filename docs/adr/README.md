# Architecture Decision Records

ArbiScan uses Architecture Decision Records (ADRs) to preserve important technical and product decisions together with their context and trade-offs.

## Why ADRs

ArbiScan will evolve across providers, sports, markets, ingestion modes, persistence choices, and deployment environments. Important decisions must therefore remain explainable after the original implementation context has disappeared.

An ADR is appropriate when a decision:

- changes a core architectural boundary;
- establishes a cross-cutting invariant;
- selects a technology with meaningful long-term consequences;
- defines canonical domain semantics;
- changes security, privacy, compliance, or data-retention behavior;
- changes the product boundary, such as introducing automated bet placement;
- accepts a material technical risk or trade-off.

Minor implementation details do not need ADRs.

## File naming

Use sequential four-digit identifiers:

```text
0001-short-kebab-case-title.md
0002-next-decision.md
```

Identifiers are never reused, even if an ADR is later superseded.

## Status values

Each ADR uses one of:

- **Proposed** — under discussion and not yet binding;
- **Accepted** — current architectural decision;
- **Superseded** — replaced by a later ADR;
- **Deprecated** — intentionally no longer recommended but not replaced by one direct successor;
- **Rejected** — considered and explicitly not adopted.

## ADR template

```markdown
# ADR-NNNN — Title

- Status: Proposed
- Date: YYYY-MM-DD
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

What problem or decision requires a durable record?

## Decision

What is being decided?

## Rationale

Why is this decision preferred?

## Consequences

### Positive

- ...

### Negative / trade-offs

- ...

## Alternatives considered

### Alternative A

Why it was not selected.

## Revisit triggers

What evidence or change should cause this decision to be reconsidered?
```

## ADR rules

1. Accepted ADRs are normative for subsequent implementation.
2. If implementation diverges from an accepted ADR, either the implementation must be corrected or a new ADR must explicitly change the decision.
3. ADRs should record trade-offs, not merely state conclusions.
4. Superseding an ADR does not delete historical context.
5. Security/correctness invariants should not be weakened implicitly through code changes.
6. ADRs should link to relevant requirements, risks, issues, and PRs when available.

## Current expansion-critical decisions

- [`0006-aggregator-price-origin-boundary.md`](0006-aggregator-price-origin-boundary.md) — separates transport/data-vendor identity from bookmaker/exchange price-origin identity.
- [`0012-multi-source-price-observation-provenance.md`](0012-multi-source-price-observation-provenance.md) — defines how Phase 16 must preserve transport provenance and resolve overlapping observations without double-counting a bookmaker.
- [`0013-structured-advanced-market-parameters.md`](0013-structured-advanced-market-parameters.md) — requires exact structured lines, period indexes, and selection handicaps before Phase 17 market families can enter canonical arbitrage detection.
- [`0014-football-totals-push-free-settlement-policy.md`](0014-football-totals-push-free-settlement-policy.md) — limits Phase 17.2 football totals to push-free half-goal lines until richer settlement algebra exists.
- [`0015-football-asian-handicap-identity-and-settlement.md`](0015-football-asian-handicap-identity-and-settlement.md) — anchors signed handicap identity to ordered participant 1, models Asian settlement states, and gates complex settlement from the generic engine.
- [`0016-football-btts-provider-equivalence.md`](0016-football-btts-provider-equivalence.md) — defines regulation-time BTTS through exact provider market identity and canonical YES/NO completeness.
- [`0017-draw-no-bet-refund-aware-evaluation.md`](0017-draw-no-bet-refund-aware-evaluation.md) — reuses Asian Handicap 0 for DNB and separates decisive-state edge from the shared draw-refund state.

## Initial ADR topics

The roadmap is expected to produce ADRs for decisions including:

- scanner-only initial product boundary;
- numeric representation for odds, probability, and money;
- canonical event and market identity strategy;
- provider adapter contract;
- freshness model;
- persistence/storage architecture;
- API boundary;
- asynchronous ingestion/concurrency model;
- raw-provider-data retention strategy;
- deployment architecture;
- any future automated wagering functionality.
