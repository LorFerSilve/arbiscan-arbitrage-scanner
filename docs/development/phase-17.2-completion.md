# Phase 17.2 completion — football pre-match regulation totals

Date: 2026-09-18

## Scope

Phase 17.2 enables ArbiScan's first advanced market family: football pre-match
regulation totals on push-free half-goal lines.

It builds on the structured line identity introduced in Phase 17.1 and deliberately
does not broaden the generic arbitrage engine to push or split-settlement markets.

## Completed implementation

### Explicit market-support gate

A new canonical market-support policy permits:

- the validated winner-market baseline;
- football `TOTAL_POINTS` with `REGULATION` period and a positive `x.5` line.

It rejects unsupported market families and total variants before quote creation with
`UNSUPPORTED_MARKET_VARIANT`.

Integer and quarter lines therefore cannot enter market-book construction even when
an explicit canonical ID hook maps them.

### Canonical outcome completeness

Every canonical `TOTAL_POINTS` market must contain exactly:

- one `OVER` selection;
- one `UNDER` selection.

Invalid canonical registry graphs fail at construction.

### The Odds API

For explicitly configured `totals` markets, the adapter now requires:

- a numeric point on each outcome;
- one shared point across the market;
- exactly one Over and one Under outcome.

The shared point remains exact structured source data. The default adapter request is
still `h2h`.

### OddsPapi

The adapter now recognizes schema-faithful football full-time totals only when the
catalog identifies:

- `Over Under Full Time`;
- `period=fulltime`;
- `marketType=totals`;
- a positive numeric line;
- exactly Over and Under outcomes.

The catalog handicap is preserved as the source market line.

Suspending a parameterized OddsPapi market now also preserves its line,
`period_index`, and any selection handicap rather than dropping Phase-17 semantic
metadata.

OddsPapi's production/legal blockers remain unchanged.

## End-to-end real-schema regression

The Phase 17.2 integration test uses both real adapter schemas with deterministic local
fixtures for the same canonical football event and total 2.5 market.

It proves:

1. both transports normalize to the same exact canonical total;
2. both produce canonical OVER/UNDER selections;
3. overlapping Pinnacle observations remain separate source evidence and consolidate
   to one price origin under ADR-0012;
4. Bet365 supplies the best Over price at 2.10 through The Odds API;
5. Betfair supplies the best Under price at 2.05 through OddsPapi;
6. the complete two-selection market book is built;
7. the generic arbitrage evaluator detects the theoretical arbitrage;
8. a canonical Opportunity is materialized without provider-specific arithmetic.

Additional regressions prove:

- total 2.5 and total 3.5 never complete one another;
- an integer total 3.0 remains structurally parseable but is rejected by the canonical
  support gate;
- malformed totals without one Over and one Under fail at the adapter boundary.

## Settlement boundary

ADR-0014 records the Phase 17.2 safety decision:

- positive half-goal `x.5` football regulation totals are supported;
- integer totals are excluded because PUSH settlement is not represented;
- quarter lines are excluded because HALF-WIN/HALF-LOSS split settlement is not
  represented;
- broader periods, live totals, team totals, player totals and other sports remain
  disabled.

## Quality evidence

The code-bearing Phase 17.2 head
`19b4d7ef6d18d0396366cab28b119a074d01f0dd` passed the full repository quality
gate:

- Ruff formatting: pass (`204 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`139 source files`);
- pytest: pass (`265 passed`);
- `pip-audit`: no known vulnerabilities found;
- CodeQL: no new alerts in code changed by the pull request;
- Analyze (python): pass;
- Analyze (actions): pass.

The final documentation head must preserve these gates.

## Handoff

**Phase 17.2 is complete.**

The next dependency is **Phase 17.3 — football Asian handicap settlement semantics**.

Before any handicap line is enabled, Phase 17.3 must define:

- canonical line anchoring and sign convention;
- participant-side handicap identity;
- push behavior on integer lines;
- quarter-line split settlement;
- outcome completeness and payout semantics;
- provider-specific source mappings without core coupling;
- exact same-line/opposite-side equivalence across providers;
- fail-closed unsupported variants;
- whether the existing `ArbitrageEvaluation` and `StakePlan` are sufficient or
  require a richer settlement-aware payout model.

No Asian handicap should enter the generic arbitrage engine merely because Phase 17.1
already preserves signed source handicaps.
