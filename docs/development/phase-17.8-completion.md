# Phase 17.8 completion — tennis set-winner cross-transport completion

Date: 2026-09-18

## Scope

Phase 17.8 completes the existing canonical tennis Set 1 / Set 2 winner family across
both real transport schemas.

The Odds API now joins the OddsPapi implementation without changing canonical market
identity or provider-independent arbitrage mathematics.

## Official provider evidence

The current official The Odds API betting-market list documents:

- `h2h_s1` — moneyline, first set — valid for tennis;
- `h2h_s2` — moneyline, second set — valid for tennis.

These are additional markets accessed through the event-odds endpoint already used by
the adapter.

OddsPapi's current tennis material documents:

- market 123 — First Set Winner;
- market 125 — Second Set Winner.

Phase 17.8 therefore has a demonstrated same-market mapping on both transports.

## The Odds API adapter

When explicitly configured with `h2h_s1` or `h2h_s2`, the adapter now requires:

- a tennis event;
- exactly two outcomes;
- outcome labels exactly equal to the event participants;
- no `point` values.

It emits:

- `h2h_s1` -> `SourceMarket.period_index=1`;
- `h2h_s2` -> `SourceMarket.period_index=2`;
- no market line;
- no selection handicap.

The provider default remains:

```text
markets=h2h
```

Set markets therefore remain opt-in and do not increase default quota consumption.

Malformed participant labels and unexpected point semantics fail at the adapter
boundary.

## Cross-transport canonical equivalence

The deterministic integration regression uses the same canonical Sinner vs Alcaraz
event and both real adapter schemas.

It proves:

1. The Odds API Set 1 and Set 2 markets preserve structured indexes 1 and 2;
2. OddsPapi Set 1 and Set 2 preserve the same structured indexes;
3. both transports normalize to the same two canonical market IDs;
4. Set 1 and Set 2 never cross-compare;
5. both transports preserve independent transport provenance.

## ADR-0012 overlap behavior

The Phase 17.8 fixtures deliberately expose Pinnacle through both transports.

Across two sets and two participant selections there are four equal-time,
equal-price Pinnacle overlaps.

Before consolidation:

- The Odds API contributes 8 quotes;
- OddsPapi contributes 8 quotes;
- total observations: 16.

ADR-0012 consolidation produces:

- 4 equivalent-overlap diagnostics;
- no material conflicts;
- 12 executable quotes;
- exactly one Pinnacle price origin per canonical market/selection.

Thus one bookmaker observed through two feeds cannot be double-counted.

## Best-price book and theoretical arbitrage

After consolidation, Set 1 and Set 2 form separate complete market books.

Set 1 best prices are:

- Carlos Alcaraz — Betfair 2.10 via OddsPapi;
- Jannik Sinner — Pinnacle 2.05 via the deterministically selected overlapping
  transport observation.

The ordinary two-outcome evaluator detects a theoretical completed-set arbitrage and
the conservative EUR stake allocator produces positive guaranteed profit under the
existing normal-settlement assumptions.

Set 2 best prices include:

- Carlos Alcaraz — Bet365 1.92 via The Odds API;
- Jannik Sinner — Pinnacle 1.94.

Set 2 is not an arbitrage.

This demonstrates that distinct transports can contribute different best prices while
shared bookmaker observations still consolidate correctly.

## Strict set isolation

A regression explicitly remaps The Odds API Set 1 source markets to canonical Set 2.

Strict normalization rejects those source markets with
`MARKET_PARAMETER_MISMATCH` before quote creation.

The structured period index, not the market label, owns set identity.

## Settlement limitation

Phase 17.8 does not change the Phase 17.6 tennis settlement caveat.

For a normally completed set, the two participant outcomes form a conventional
win/lose pair and the generic reciprocal-odds/stake path is appropriate.

Retirement, walkover, abandonment, or incomplete-set settlement may still differ by
bookmaker. The resulting opportunity remains theoretical under the documented
completed-set assumptions until bookmaker-specific tennis settlement rules enter the
execution-realism model.

## Code-bearing quality evidence

The code-bearing head
`a58b74e6ebafe79691911a39fa8e7662d805b96c` passed:

- Ruff formatting: pass (`232 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`149 source files`);
- pytest: pass (`321 passed`);
- `pip-audit`: no known vulnerabilities.

The final documentation head must preserve the same quality/security gates.

## Handoff

**Phase 17.8 is technically complete.**

The next dependency is **Phase 17.9 — basketball spreads/totals and
overtime-period semantics**.

Before basketball market enablement, Phase 17.9 must establish:

- canonical basketball sport support;
- regulation-only versus overtime-inclusive settlement identity;
- exact participant spread orientation and line anchoring;
- total-points line identity;
- PUSH/split-settlement treatment for integer or fractional lines where applicable;
- provider mappings across both real transports where equivalent semantics exist;
- exact participant or Over/Under completeness;
- cross-transport overlap consolidation;
- which subset can safely use the existing generic arbitrage/stake engine;
- fail-closed handling of quarters, halves, alternate lines, and live markets until
  separately specified.
