# ArbiScan Arbitrage Scanner

ArbiScan is a multi-bookmaker sports-odds aggregation and arbitrage-detection engine. The product boundary is intentionally scanner-only: it identifies and reports semantically valid opportunities but does not place bets automatically.

## Current status

Phases 0 through 18 of [`roadmap.md`](roadmap.md) are technically implemented
and merged to `main`. **Phase 19 — performance and scalability engineering — is
in progress, not complete.**

Phase 19 has reproducible synthetic benchmarks for detection, matching, provider
polling, multi-source consolidation, SQLite persistence and historical replay.
Profiling-driven indexing, matching-cache, batch-persistence and diagnostic
improvements have landed. The most recent completed milestone (PRs #70–#72)
validated an eight-step, fixture-backed two-provider replay for partial coverage,
source expiry, late revisions, clock skew and recovery. These repeated polls are
**simulated mutations of retained single-response fixtures**, not captured real
provider traffic or evidence of production latency.

The implemented core includes:

- provider-neutral canonical event/market/selection/quote models;
- deterministic Decimal-based arbitrage mathematics and stake allocation;
- strict async provider adapters with two real transport schemas;
- semantic normalization and cross-provider event matching;
- multi-source price-origin provenance and same-bookmaker consolidation;
- canonical best-price market books;
- realtime ingestion, freshness/stale control, rate-limit handling, and provider isolation;
- persistence/audit evidence and opportunity reconstruction;
- opportunity lifecycle/actionability revalidation;
- transport-neutral service/API contracts;
- system/provider observability;
- read-only dashboard projection and alert deduplication;
- advanced football totals/handicaps/BTTS/DNB, indexed tennis set winners, and
  full-event basketball half-point spreads/totals;
- canonical motorsport race/qualifying/session identity with race-winner, podium, and
  H2H completeness gates, while runtime F1 evaluation remains intentionally disabled;
- generalized tournament/championship outright candidate completeness plus an explicit
  settlement-safety profile for deciding when generic N-outcome math is sufficient;
- a separate exchange settlement path with explicit BACK/LAY identity, lay liability,
  matched-liquidity limits, commission scope, and net-market commission;
- deterministic historical replay over canonical quote corpora, including opportunity
  duration, latency sensitivity, stale-data counterfactuals, provider comparisons,
  matching precision/recall, and theoretical-versus-actionable analysis.

The project remains development software. OddsPapi is technically integrated but
remains blocked from production activation pending the documented provider-rights
clarifications. Phase 19 exit criteria are not met without permissioned real-world
multi-poll validation and representative deployment-load measurements.

## Current market scope

Enabled advanced semantics remain intentionally narrow:

1. football pre-match regulation winner, push-free half-goal totals/handicaps, BTTS,
   and settlement-aware Draw No Bet;
2. tennis pre-match two-way match winner plus documented Set 1 / Set 2 winner;
3. basketball full-event half-point totals and spreads, with regulation/sub-period,
   integer/quarter-line, alternate, and live variants fail-closed;
4. motorsport/F1 canonical winner/podium/H2H identity is modeled, but all such
   markets remain runtime-disabled until provider and DNS/DNF/disqualification/
   dead-heat settlement equivalence is proven;
5. broader tournament/championship outright identity now requires a complete,
   homogeneous candidate set and explicit settlement-safety evidence; runtime support
   remains closed until a provider path proves that evidence;
6. exchange BACK/LAY payout semantics are modeled separately from bookmaker quotes,
   including lay liability, visible matched liquidity and commission on positive net
   exchange-market winnings. No live exchange transport is enabled yet.

## Next Phase 19 gate

1. Confirm each provider permits the required local capture, retention and offline
   replay. Do not collect or commit payloads where permission is unclear.
2. Obtain **authorized, time-ordered observations from both sources for matching
   events**, covering price changes, outcome loss, source skew, outages and recovery.
   Keep raw captures and credentials outside the repository.
3. Validate matching and normalization, then freshness, consolidation and
   fail-closed book construction against those sequences. Record only permitted,
   non-sensitive aggregate results and reproducible semantic digests.
4. After correctness passes, profile on the intended deployment hardware, establish
   measured latency/throughput targets, and recheck any optimization for parity.

See [the Phase 19 baseline](docs/development/phase-19-performance-baseline.md)
for existing measurements, limitations and commands. No real-capture data is yet
available in the repository.

## Development

The project uses Python 3.13, uv, Ruff, mypy, pytest, pre-commit, and GitHub Actions. See [`docs/development/setup.md`](docs/development/setup.md) for the reproducible setup and quality commands.

The full local/CI quality gate is:

```text
uv run python scripts/quality.py --all
```

CI uses deterministic fixtures and does not require live provider credentials.

## Documentation

- Development status and phase completion records: [`docs/development/`](docs/development/)
- Product requirements: [`docs/product/requirements.md`](docs/product/requirements.md)
- Non-goals: [`docs/product/non-goals.md`](docs/product/non-goals.md)
- Risk register: [`docs/product/risk-register.md`](docs/product/risk-register.md)
- Provider integration checklist: [`docs/product/provider-integration-checklist.md`](docs/product/provider-integration-checklist.md)
- The Odds API integration: [`docs/providers/the-odds-api.md`](docs/providers/the-odds-api.md)
- Phase 16 readiness: [`docs/providers/phase-16-readiness.md`](docs/providers/phase-16-readiness.md)
- Phase 16.1 provider selection: [`docs/providers/phase-16.1-provider-selection.md`](docs/providers/phase-16.1-provider-selection.md)
- OddsPapi onboarding record: [`docs/providers/oddspapi.md`](docs/providers/oddspapi.md)
- Dashboard/alert boundary: [`docs/product/dashboard-and-alerts.md`](docs/product/dashboard-and-alerts.md)
- Historical replay/backtesting: [`docs/analysis/historical-replay-and-backtesting.md`](docs/analysis/historical-replay-and-backtesting.md)
- Architecture decisions: [`docs/adr/`](docs/adr/)
- Development roadmap: [`roadmap.md`](roadmap.md)
