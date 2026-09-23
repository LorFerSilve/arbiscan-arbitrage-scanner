# ADR-0024 — Deterministic historical replay and backtesting boundary

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

ArbiScan needs to measure detector behavior over historical canonical quote streams
without creating a second implementation of market construction, arbitrage detection,
or actionability logic.

A historical price snapshot is not evidence of realized profit. Real execution also
depends on latency, freshness, stake constraints, order acceptance, market
suspension, provider limits, settlement rules, commission, taxes, and other
account-specific conditions.

Historical analysis must therefore be reproducible while preserving the distinction
between theoretical detector output and modeled actionability.

## Decision

Phase 18 introduces a provider-independent offline replay layer over canonical
`OddsQuote` history.

Replay reuses production primitives:

- `build_market_books()` for canonical best-price construction and freshness;
- `evaluate_market()` for theoretical arbitrage;
- `build_opportunity()` for canonical opportunity identity;
- `revalidate_opportunity()` when an explicit `ActionabilityPolicy` is supplied.

No separate backtest arbitrage formula or market matcher is introduced.

A `HistoricalQuoteCorpus` is strictly chronological and has a deterministic SHA-256
digest over replay timestamps plus canonical serialized quotes. This digest identifies
the fixed evidence corpus used for comparisons.

`BacktestConfig` makes replay assumptions explicit:

- freshness window;
- detection latency;
- source clock-skew tolerance for live-store admission;
- minimum theoretical margin;
- provider inclusion/exclusion policy;
- optional actionability policy;
- optional canonical market scope.

At each simulated detector instant, replay uses only batches whose observation time is
not later than that instant. The production multi-source live store retains one
accepted observation per transport stream. After the configured freshness gate,
overlapping feeds are consolidated by executable bookmaker price slot and equal-time
material conflicts suppress the slot. Only markets supported by the generic arbitrage
settlement policy are passed to the existing market-book and evaluation paths.

Phase 18 reports:

- theoretical detections;
- optional actionable detections under the supplied operational model;
- contiguous opportunity intervals and duration;
- detection-latency sensitivity;
- stale-data false-positive counterfactuals;
- provider coverage and standalone signal metrics;
- precision/recall for externally labeled matching decisions.

Stale-data false positives are quantified by comparing the configured freshness gate
with a counterfactual replay that keeps the same current quote state but relaxes only
the freshness window.

SQLite persistence gains deterministic historical quote loading so retained canonical
evidence can be replayed directly.

## Realized-profit boundary

Backtest output must not be described as realized profitability.

A positive theoretical or actionable historical result means only that the recorded
canonical evidence satisfied the configured model at the simulated time. It does not
prove that wagers could have been submitted, accepted, fully matched, or settled at
those prices.

Any future realized-execution claim requires explicit execution records or a model
that represents all material execution uncertainties and clearly states its limits.

## Consequences

### Positive

- live and historical detection share the same correctness primitives;
- detector changes can be compared against one immutable corpus digest;
- freshness and latency assumptions are measurable rather than anecdotal;
- provider comparisons use the same canonical market semantics;
- theoretical and modeled-actionable results remain explicitly separated.

### Negative / trade-offs

- replay recomputes complete market books at each detector instant and is not yet
  optimized for large corpora;
- current history is quote-snapshot based rather than a complete bookmaker execution
  log;
- provider/account-specific rejection and execution probability are not inferred;
- labeled matching quality requires an external ground-truth dataset.

## Revisit triggers

Revisit when Phase 19 profiling shows replay throughput is inadequate, when historical
order-book/execution records become available, or when a richer event-sourced history
format is required.
