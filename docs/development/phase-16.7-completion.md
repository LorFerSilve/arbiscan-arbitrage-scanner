# Phase 16.7 completion — observability and operational tuning

Date: 2026-09-18

## Scope

Phase 16.7 validates the second real source under ArbiScan's operational and
observability boundaries. The work extends the existing Phase-14/Phase-16 telemetry
surface without changing provider-neutral arbitrage mathematics, market-book
semantics, or persistence behavior.

All ordinary CI validation remains deterministic, fixture-driven, and credential-free.

## Completed implementation

1. Extended the in-process metrics registry with cumulative source-specific counters
   for:
   - strict-normalization failures;
   - event-identity/matching-boundary failures.
2. Wired the observable realtime scanner so every normalization issue is attributed
   to its transport provider, while event identity failures are separately classified
   from ordinary market/selection normalization failures.
3. Added `SourceOperationalSnapshot` and `MultiSourceOperationalSnapshot` to the
   multi-source scanner application contract.
4. The per-source operational snapshot now exposes:
   - provider health state and availability;
   - cumulative poll/request and error counts;
   - cumulative rate-limit events;
   - latest quota remaining;
   - last attempt, success, and successful-update timestamps;
   - latest update interval;
   - consecutive failures and latest ingestion issue count;
   - current fresh source-observation count;
   - deterministic fresh-observation age distribution;
   - cumulative source normalization and matching failure counts;
   - cumulative ADR-0012 overlap diagnostic participation;
   - cumulative material-conflict participation.
5. The multi-source operational snapshot also exposes the configured poll interval
   and maximum provider concurrency so runtime tuning is observable rather than
   implicit.

## Real-source operational regressions

The Phase 16.7 integration suite exercises The Odds API and OddsPapi through their
real adapter schemas and deterministic HTTP fixture transports.

Validated behavior includes:

1. both sources publish complete per-transport operational snapshots during a healthy
   multi-source cycle;
2. The Odds API exposes fixture-derived quota remaining independently from OddsPapi's
   account-based request-limit model;
3. source freshness distributions retain six pre-consolidation observations per
   transport in the shared football fixture scenario;
4. an intentionally unmatched The Odds API event increments only that source's
   normalization/matching telemetry while transport health remains healthy;
5. an exhausted OddsPapi account quota degrades only OddsPapi, increments its
   rate-limit/error metrics, suppresses its polling output, and leaves The Odds API
   healthy and actionable;
6. system health becomes degraded-but-ready for the isolated quota condition rather
   than globally unhealthy;
7. an ADR-0012 equal-time material conflict is attributed to both real transport
   identities;
8. the real-adapter runtime respects `max_concurrency=1` under an instrumented
   transport probe;
9. a configured seven-second polling cadence is observed exactly, and both provider
   health records expose a seven-second successful update interval on the second
   cycle.

## Quality evidence

The code-bearing Phase 16.7 head
`2112d6ae15de9c9ed7eea6846546d6f059a1bfb8` passed the repository's complete
quality/security surface:

- Ruff formatting: pass (`193 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`132 source files`);
- pytest: pass (`235 passed`);
- `pip-audit`: no known vulnerabilities found;
- CodeQL: pass, no new alerts in code changed by the pull request;
- Analyze (python): pass;
- Analyze (actions): pass.

The final documentation head must preserve those gates.

## Handoff

Phase 16.7 is complete. The next roadmap dependency is **Phase 16.8 — staged
enablement and closure**.

Phase 16.8 should close the multi-provider expansion by:

- defining an explicit staged-enable/disable policy for the second real transport;
- proving at least two independent real transport sources can participate in the
  same scanner runtime under the completed semantic, freshness, overlap, persistence,
  and observability gates;
- preserving failure isolation and bookmaker-origin consolidation;
- confirming no provider-specific changes were required in arbitrage mathematics or
  the canonical core;
- updating provider documentation and the risk register with final operational
  constraints;
- recording final Phase 16 completion evidence and the post-Phase-16 roadmap handoff.

Production enablement should remain fail-closed and reversible. Live-provider
availability must not become a pull-request CI dependency.
