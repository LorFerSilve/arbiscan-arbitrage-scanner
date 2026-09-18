# Phase 16.8 completion — staged enablement and Phase 16 closure

Date: 2026-09-18

## Scope

Phase 16.8 closes the Phase 16 multi-provider engineering sequence by introducing an
explicit, provider-neutral transport-source enablement gate and proving deterministic
single-source, dual-source, and rollback behavior with the two real adapter schemas.

This phase does **not** declare OddsPapi production-approved. Provider-specific
licensing, caching, retention, display, fixture-distribution, and geographic/data-use
questions remain external production prerequisites.

## Completed implementation

1. Added `TransportSourceEnablementPolicy` at the application/service boundary.
2. The policy explicitly declares which transport-provider IDs may participate.
3. Disabled adapters are removed before polling, so they cannot:
   - issue provider requests;
   - contribute canonical quotes;
   - alter live source state;
   - influence provider health or freshness telemetry.
4. Added a primary-only factory for a fail-closed single-source rollout.
5. Added staged multi-source composition that keeps the primary transport required
   while opt-in additional transports are enabled.
6. Unknown enabled transports fail closed.
7. Duplicate configured transport identities fail closed.
8. A required transport cannot be omitted from the enabled set.
9. The multi-source scanner exposes both:
   - every configured transport-provider ID;
   - the subset actually enabled and eligible for polling.
10. No changes were required in the canonical domain, arbitrage mathematics, stake
    allocation, or bookmaker price-origin semantics.

## Staged enablement regressions

The Phase 16.8 closure suite validates:

1. **Primary-only stage**
   - both real adapters can be configured;
   - only The Odds API is enabled;
   - OddsPapi is not polled;
   - no OddsPapi quote enters executable state;
   - operational telemetry contains only the enabled transport.

2. **Dual-source stage**
   - The Odds API and OddsPapi are both explicitly enabled;
   - both independent transport failure domains are polled;
   - both contribute to one canonical football market book;
   - overlapping bookmaker observations remain consolidated;
   - best-price construction can select Bet365 via The Odds API and Betfair via
     OddsPapi in the same market.

3. **Rollback stage**
   - after proving dual-source participation, a fresh primary-only scanner can be
     composed deterministically;
   - OddsPapi is absent from polling, fresh quote state, and operational telemetry;
   - no previous dual-source conflict/observation state leaks into the rollback
     runtime.

4. **Configuration fail-closed behavior**
   - naming an unconfigured transport in the enablement policy rejects scanner
     construction rather than silently ignoring the error.

## Phase 16 exit-criteria mapping

The Phase 16 exit criteria from `roadmap.md` and
`docs/providers/phase-16-readiness.md` are satisfied at the engineering layer:

- **two independent real transport sources participate safely** — The Odds API and
  OddsPapi coexist in deterministic real-adapter integration tests;
- **provider failures are isolated** — outage and quota regressions keep the healthy
  source operational;
- **overlapping price origins are safe** — ADR-0012 provenance and deterministic
  consolidation prevent double counting and fail closed on material conflicts;
- **canonical core remains provider-neutral** — the second transport required no
  provider-specific changes to arbitrage mathematics or canonical domain models;
- **semantic gates pass** — sport, competition, participants, event matching, market,
  selection, status, and freshness semantics are validated;
- **persistence retains provenance** — executable price origin and selected transport
  source survive persistence/reconstruction;
- **observability gates pass** — per-source requests/errors/rate limits, timing,
  freshness, normalization/matching failures, conflicts, and health are exposed;
- **staged activation is reversible** — transport participation is explicitly gated
  before polling, with a tested primary-only rollback path;
- **quality/security gates pass** — the code-bearing Phase 16.8 head passed the full
  repository gate;
- **provider/risk documentation is updated** — OddsPapi production blockers and
  Phase 16-specific risks are explicitly recorded.

## Production-readiness boundary

Phase 16 is an engineering architecture milestone, not a production deployment
approval.

OddsPapi remains production-blocked until its unresolved provider/legal questions are
clarified and recorded against the provider integration checklist. The safe default
for a production-like composition therefore remains a primary-only transport policy.

The staged multi-source policy is technically ready for an environment only after its
provider-specific access and usage rights are approved. This separation prevents a
green engineering test suite from implicitly authorizing provider usage.

## Quality evidence

The code-bearing Phase 16.8 head
`d5aad6ecb846a7680704d6f0df9c9c97a1259d74` passed:

- Ruff formatting: pass (`197 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`135 source files`);
- pytest: pass (`244 passed`);
- `pip-audit`: no known vulnerabilities found.

The final documentation head must retain the same quality/security gates, including
CodeQL and both configured Analyze jobs.

## Handoff

**Phase 16 — Multi-provider expansion is technically complete.**

The next roadmap dependency is **Phase 17 — Advanced market support**.

Phase 17 must preserve all Phase 16 invariants. Every added market family requires its
own explicit semantic specification, outcome-completeness rules, line/parameter
equivalence policy, provider mappings, adversarial fixtures, and fail-closed behavior.

Production activation of OddsPapi remains a separate provider-readiness decision and
must not be inferred from the Phase 17 handoff.
