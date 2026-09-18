# Phase 17.9 completion — Basketball spreads/totals and overtime-period semantics

**Status:** Technically complete on 2026-09-18.

## Delivered

- canonical `Sport.BASKETBALL`;
- basketball discovery through The Odds API and OddsPapi;
- fail-closed The Odds API full-event bookmaker allowlisting, defaulting to no
  basketball spread/total price origins until settlement scope is independently verified;
- exact full-event total and spread line preservation;
- ordered participant-1 spread anchoring with mirrored participant-2 handicap;
- explicit OddsPapi mappings for `Over Under (incl. overtime)` and
  `Handicap (incl. overtime)`;
- full-event half-point support gates for generic arbitrage/staking;
- integer/quarter-line fail-closed behavior;
- quarter/half source families kept out of the full-event path;
- deterministic provider fixtures for both real transport schemas;
- cross-transport same-bookmaker consolidation and end-to-end opportunity/stake
  regression.

## Safety boundary

This phase does not assert realized betting profitability. It proves canonical
identity and mathematical behavior under the modeled prices. Execution, bookmaker
acceptance, latency, account restrictions, provider licensing, and provider-specific
settlement rules remain separate constraints.

OddsPapi remains development-only until the existing production-rights blockers are
resolved.

## Next dependency

**Phase 17.10 — motorsport/F1 winner, podium, and head-to-head semantics.**

That phase must define participant/constructor identity, race/session scope, outcome
completeness, dead-heat/retirement/DNS/DNF settlement behavior, and provider
equivalence before runtime enablement.
