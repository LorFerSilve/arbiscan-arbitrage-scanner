# Phase 17.1 completion — structured advanced-market semantic foundation

Date: 2026-09-18

## Scope

Phase 17.1 establishes the semantic identity boundary required before ArbiScan enables
parameterized or indexed advanced markets.

The canonical model already represented exact total/handicap lines and indexed
periods, but the provider-neutral source boundary did not preserve those values as
structured data. Enabling totals, handicaps, or set markets without fixing that gap
would force later code to infer semantic parameters from provider labels.

Phase 17.1 closes that gap without enabling a new arbitrage market family yet.

## Completed implementation

### Provider-neutral source contract

The source models now preserve:

- `SourceMarket.line: Decimal | None`;
- `SourceMarket.period_index: int | None`;
- `SourceSelectionQuote.handicap: Decimal | None`.

The fields are optional so the validated winner-market path remains backward
compatible.

Correctness constraints:

- numeric market lines and selection handicaps must be exact finite `Decimal`
  values;
- binary floats are rejected;
- non-finite decimal values are rejected;
- a supplied period index must be a positive integer.

### Strict canonical parameter identity

Explicit canonical ID mappings remain necessary but are no longer sufficient for
advanced-market source data.

After market identity resolution, strict normalization now requires:

- source market line equals canonical market line;
- source period index equals canonical period index.

A mismatch, missing source parameter, or unexpected source parameter yields
`MARKET_PARAMETER_MISMATCH` and excludes the entire affected source market before
quote construction.

After selection identity resolution, strict normalization requires:

- source selection handicap equals canonical selection handicap.

A mismatch yields `SELECTION_PARAMETER_MISMATCH` and excludes that source selection.

This prevents a stale or incorrect explicit mapping from binding, for example, a
source total 3.5 market to canonical total 2.5.

### The Odds API parser proof

The existing default request remains `h2h`; no advanced market is enabled by
default.

When additional market keys are explicitly configured:

- `totals` requires every outcome to carry a numeric `point`;
- every outcome in one totals market must report the same point;
- that shared point is preserved as `SourceMarket.line`;
- `spreads` requires every outcome to carry a numeric signed `point`;
- each spread point is preserved as `SourceSelectionQuote.handicap`;
- an unexpected point-bearing market key fails closed;
- inconsistent totals points fail at the adapter boundary as a malformed response.

Spread/Asian-handicap canonical activation remains deliberately blocked because
source handicap preservation alone does not define canonical market-line anchoring,
push/void behavior, or complete settlement semantics.

## Architecture decision

ADR-0013 — *Preserve structured advanced-market parameters before canonical identity*
is accepted.

Its central invariant is that lines, indexed periods, and signed selection handicaps
are semantic identity, not provider presentation text. Provider labels must never be
the authoritative source of those parameters.

## Regression coverage

Phase 17.1 adds tests proving:

1. exact source total 2.5 maps safely to canonical total 2.5;
2. source total 3.5 cannot enter canonical total 2.5 even when an explicit ID hook
   maps the source market to that canonical ID;
3. a missing source line cannot enter a parameterized canonical market;
4. an unexpected source period index is rejected;
5. an unexpected selection handicap is rejected independently;
6. exact source line, period-index, and selection-handicap values survive source-model
   construction;
7. floats, non-finite values, and invalid period indexes fail at the source boundary;
8. The Odds API totals `point` is preserved as a market line when outcomes agree;
9. The Odds API spread points remain signed selection handicaps;
10. inconsistent totals points fail closed in the adapter.

## Risk register

R-041 records the critical risk that markets with different lines, period indexes, or
selection handicaps could otherwise collapse onto one canonical identity.

The risk remains **Mitigating** while Phase 17 market families are added because every
new family must still prove its settlement and completeness semantics in addition to
the Phase 17.1 parameter-identity guard.

## Quality evidence

The code-bearing Phase 17.1 head
`351ca3119de18df73e19f761a0ed67bdfd830323` passed the full repository quality
gate:

- Ruff formatting: pass (`200 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`136 source files`);
- pytest: pass (`253 passed`);
- `pip-audit`: no known vulnerabilities found.

The final documentation head must preserve the repository quality/security gates.

## Handoff

**Phase 17.1 is complete.**

The next dependency is **Phase 17.2 — football pre-match regulation totals**.

Phase 17.2 must define and test, before enablement:

- exact provider-to-canonical totals mappings;
- regulation/full-event settlement scope;
- Over/Under outcome completeness;
- exact line equivalence across providers;
- same-line multi-source market-book construction;
- different-line non-comparison;
- integer-line push/void behavior, or an explicit initial restriction to line classes
  whose settlement semantics the current two-outcome arbitrage model can represent;
- provider fixtures and fail-closed unsupported variants;
- end-to-end arbitrage detection without provider-specific arithmetic changes.

The Phase 17.1 structured-parameter contract is mandatory input to that work.
