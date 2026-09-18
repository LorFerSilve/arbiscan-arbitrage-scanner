# Phase 17.11 completion — Broader outright tournament/championship semantics

**Status:** Technically complete on 2026-09-18 as a semantic/provider-feasibility
gate. No broader outright runtime market is enabled.

## Delivered

- generalized canonical `OUTRIGHT_WINNER` completeness across race, qualifying,
  session and tournament scopes;
- exact one-selection-per-candidate coverage;
- homogeneous participant-kind enforcement;
- fail-closed treatment of synthetic Field/Other and non-participant outcomes;
- provider-independent `OutrightEvaluationProfile` and deterministic blocker
  diagnostics;
- proof that the existing arbitrary-N reciprocal-odds engine is mathematically
  reusable only for complete, static, mutually-exclusive/exhaustive outrights with
  equivalent withdrawal/void rules and no tie/dead-heat split settlement;
- generic runtime support remains closed until provider evidence constructs that
  profile safely;
- The Odds API `has_outrights` metadata preservation and generic outright rejection
  before binary event parsing;
- OddsPapi unverified tournament-winner catalogue family kept outside supported
  mapping;
- deterministic domain, normalization and provider regressions;
- ADR-0022, market documentation, provider documentation and risk-register update.

## Provider conclusion

The Odds API documents real outright/futures support but its outright schema is not
the same as the ordinary home/away event schema. OddsPapi's public contract exposes
markets dynamically rather than providing one canonical cross-provider outright
identifier that ArbiScan can safely hard-code.

Phase 17.11 therefore does not manufacture cross-transport equivalence from labels.
A later enablement can reuse the generic N-outcome math once complete candidate
identity and settlement equivalence are demonstrated.

## Next dependency

**Phase 17.12 — exchange-backed outcomes, back/lay identity and commission-aware
arbitrage semantics.**

This next phase must keep exchange lay prices distinct from bookmaker back prices,
model liability and commission, prove selection identity, and prevent ordinary
reciprocal bookmaker math from consuming lay odds.
