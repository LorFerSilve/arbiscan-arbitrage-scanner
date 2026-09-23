# Phase 19 performance baseline — post-ingestion detection

**Status:** First measured workload and two profiled core optimizations. This is a
partial Phase 19 result, not its full scalability exit gate.

## Measurement contract

Run from the repository root after `uv sync --locked`:

```text
uv run python scripts/benchmark_detection.py
```

The command builds a fixed synthetic football catalog and measures a warmed-up series
of quote-update cycles. Each measured cycle applies canonical quote updates to
`LiveQuoteStore`, reads fresh quotes, builds canonical best-price market books, runs
the exact arbitrage evaluator, and materializes detected opportunities. The JSON
report gives median, nearest-rank p95, and maximum milliseconds by stage, plus
in-process store updates per second and a deterministic result digest.

Defaults cover 100 events, three markets per event (one regulation 1X2 and two
push-free regulation totals), three price providers, 2,100 initial quotes, 300
updates per cycle, three warm-up cycles, and 20 measured cycles. The script accepts
`--events`, `--markets-per-event`, `--providers`, `--updates-per-cycle`,
`--warmup-cycles`, and `--measured-cycles`. The quote state and timings are created
without network calls, credentials, or randomness.

The cycle timing covers the in-process post-ingestion detection path. Provider HTTP,
payload normalization, cross-provider event matching, feed conflict resolution,
database writes, alerts, and UI rendering are outside this workload. The synthetic
prices intentionally create a detection in every complete market, exercising
opportunity materialization on every cycle. The `core_updates_per_second` figure
measures `LiveQuoteStore.apply()` time; it is not a provider ingestion rate.

Use the result digest and market/opportunity counts to confirm the same semantic
workload before comparing timings. Run the repository quality gate after changing
the detector:

```text
uv run python scripts/quality.py --all
```

## First profile and changes

The baseline was measured on Windows 10 with CPython 3.13.15 and an AMD Ryzen 7
5800X. Timings below are single local runs of the default 20 measured cycles;
they are diagnostic measurements, not cross-machine service targets.

| Stage, median milliseconds | Phase 17 core | Indexed registry + shared exact sum |
| --- | ---: | ---: |
| Apply 300 quote updates | 1.845 | 1.849 |
| Read fresh quotes | 0.849 | 0.858 |
| Build 300 market books | 30.111 | 10.554 |
| Evaluate and materialize 300 opportunities | 18.809 | 11.790 |
| Complete in-process cycle | 51.679 | 25.033 |

Both runs produced 6,000 market books, 6,000 opportunities, and result digest
`7be7cdd1f19ecc850fba82bd158b5ae107d2d31f63d5e3905e106a59f2ce5e1f`.
The measured median cycle time fell by about 52% on this workload.

`cProfile` showed 6,900 calls to `CanonicalRegistry.selection_ids_for_market()`
spending about 0.97 seconds in repeated full-selection scans. The registry now
constructs an immutable market-to-selection index once, keeping the same sorted
lookup result. After that change, `evaluate_market()` became the largest measured
core stage. It recomputed the exact rational implied-probability sum four times per
market. The evaluator now computes it once and reuses it for the displayed sum,
return multiplier, margin, and threshold decision. Public Decimal outputs and the
synthetic result digest remained identical; the arbitrage suite also checks parity
with the public math functions across fair, profitable, and unprofitable books.

For a fresh profile:

```text
uv run python -m cProfile -o ../arbiscan-profile.pstats scripts/benchmark_detection.py
uv run python -c "import pstats; pstats.Stats('../arbiscan-profile.pstats').sort_stats('cumtime').print_stats(20)"
```

## Remaining Phase 19 work

Measure provider polling and normalization, event matching, multi-source
consolidation, persistence, and historical replay at representative loads. Define
operational latency/throughput targets from actual provider contracts and deployment
capacity, then profile any further changes against fixed workloads and verify equal
results before promoting them.
