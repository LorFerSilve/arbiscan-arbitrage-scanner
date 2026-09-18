# ADR-0013 — Preserve structured advanced-market parameters before canonical identity

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Phase 17 expands ArbiScan beyond winner markets into parameterized and indexed market
families such as totals, Asian handicaps, and set markets.

The canonical domain already distinguishes exact market lines and indexed periods, but
the provider-neutral source boundary previously retained only provider labels,
identifiers, prices, and statuses. A provider can therefore report two markets with
the same textual label but different lines, or two participant prices with different
signed handicaps, without those structured parameters surviving the adapter boundary.

Relying on labels such as `Totals 2.5`, `Spread -1.5`, or `Set 2 Winner` and
re-parsing numbers later would make semantic identity depend on provider text
formatting. That violates the fail-closed normalization policy.

## Decision

Phase 17 advanced-market parameters must be preserved as structured exact values at
the provider-neutral source boundary before a market can be enabled for arbitrage
detection.

The source contract therefore carries:

- `SourceMarket.line: Decimal | None` for a market-scoped numeric line;
- `SourceMarket.period_index: int | None` for provider-supplied indexed periods;
- `SourceSelectionQuote.handicap: Decimal | None` for a signed participant-specific
  handicap.

All decimal parameters are finite `Decimal` values. Binary floats are rejected at
the source-model boundary. Period indexes, when present, are positive integers.

### Canonical identity guard

Explicit canonical ID hooks remain necessary but are no longer sufficient for
parameterized data. After a source market/selection is mapped to canonical identity,
strict normalization must compare the structured source parameters with the canonical
parameters.

A quote is ineligible when:

- source and canonical market lines differ;
- one side has a line while the other does not;
- source and canonical period indexes differ;
- source and canonical selection handicaps differ;
- one side has a selection handicap while the other does not.

These mismatches fail closed before quote construction.

### Provider parsing rule

Adapters may lift a provider field into a market-scoped line only when the payload
semantics make that transformation deterministic.

For The Odds API Phase 17.1 support:

- a configured `totals` market must provide a numeric `point` on every outcome;
- every outcome in that totals market must report the same point;
- only then is that point exposed as `SourceMarket.line`;
- a configured `spreads` market preserves each outcome's signed `point` as
  `SourceSelectionQuote.handicap`;
- spread markets are **not** canonically enabled by this ADR because their
  market-line anchoring and settlement/completeness policy require a dedicated
  Phase 17 market-family specification.

Unexpected point-bearing market keys fail closed rather than being guessed.

## Rationale

Advanced-market arbitrage is safe only when compared quotes share the same exact
semantic parameters. Numeric line identity is not presentation metadata.

Structured parameters:

- prevent total 2.5 from being compared with total 3.5;
- prevent differently handicapped participant selections from sharing one selection
  identity;
- prevent set/period indexes from being lost in provider labels;
- keep provider text parsing inside adapters rather than the canonical/arbitrage core;
- let later market-family phases define settlement and completeness rules without
  changing the source contract again.

## Consequences

### Positive

- advanced-market identity becomes machine-checkable and fail closed;
- current winner-market behavior remains backward compatible through optional fields;
- provider-specific labels remain non-authoritative;
- exact Decimal semantics are preserved end to end;
- future totals, handicap, and indexed-period work has a safe source contract.

### Negative / trade-offs

- adapters must parse and validate provider parameter fields explicitly;
- provider payloads with inconsistent structured points now fail at the adapter
  boundary instead of being partially accepted;
- market-family enablement requires both identity mapping and exact parameter
  agreement;
- handicap activation still needs a dedicated canonical anchoring/settlement policy.

## Alternatives considered

### Parse numeric lines from provider labels during normalization

Rejected. Provider labels are mutable presentation text and can be localized or
formatted inconsistently.

### Trust canonical ID hooks even when source parameters are absent

Rejected for parameterized markets. A stale or incorrect mapping could otherwise bind
a 3.5 source market to a 2.5 canonical market and create false arbitrage.

### Convert source numbers to binary floats

Rejected. Odds and market parameters are correctness-sensitive exact decimal values.

### Enable spreads immediately after retaining signed points

Rejected. Retaining source handicaps is necessary but does not by itself define
canonical market-line anchoring, push/void semantics, or outcome completeness.

## Revisit triggers

Revisit this decision if:

- a provider supplies a stronger structured market-schema object that replaces the
  current source records;
- quarter-line Asian handicaps require a richer split-line representation;
- exchange or derivative markets require multiple numeric parameters per selection;
- period identity needs more structure than a positive integer index.
