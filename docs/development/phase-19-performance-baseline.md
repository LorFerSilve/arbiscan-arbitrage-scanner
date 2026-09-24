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

The default cycle timing covers the in-process post-ingestion detection path. Provider
HTTP, payload normalization, cross-provider event matching, feed conflict resolution,
database writes, alerts, and UI rendering are outside this default workload. The synthetic
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

## Exploratory load scaling

With two warm-up and ten measured cycles, three providers, three markets per event,
and updates proportional to the event count, the optimized in-process median was:

| Events | Current quotes | Updates/cycle | Median cycle | p95 cycle |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 2,100 | 300 | 24.545 ms | 24.974 ms |
| 200 | 4,200 | 600 | 48.993 ms | 51.122 ms |
| 400 | 8,400 | 1,200 | 99.041 ms | 121.229 ms |

Median time scaled close to the workload size across these three local samples.
The 400-event p95 shows enough variation that load and tail-latency claims need
longer runs on the intended deployment machine before setting an SLO.

## Multi-source consolidation workload

The default benchmark uses `LiveQuoteStore`, whereas the production multi-source
scanner uses `MultiSourceLiveQuoteStore`. Run the same harness with overlapping
transport feeds to include the latter store's quote versioning and consolidation:

```text
uv run python scripts/benchmark_detection.py --transports-per-provider 2
uv run python scripts/benchmark_detection.py --transports-per-provider 2 --conflicting-slots 21
```

Each synthetic price-provider slot is reported by two independent transports at
the same effective timestamp. Equal prices collapse to one executable quote. The
optional `--conflicting-slots` argument makes that many fixed price slots disagree
at equal timestamps; those slots must produce conflict diagnostics and no
executable quote. The report separates applying observations, reading fresh and
consolidated quotes, market-book construction, and evaluation. It includes
observation and consolidation counts alongside the stable result digest. The
agreeing-overlap workload has the same detection digest as the one-transport
workload. A conflict workload is intentionally semantically different; compare
its digest only against runs with identical input parameters.

This remains a synthetic, in-process post-ingestion measurement. It does not time
provider polling, payload normalization, event matching, persistence, alerts, or
the UI. Its update throughput measures store operations, not external feed capacity.

On the same Windows 10 / CPython 3.13.15 / Ryzen 7 5800X machine, local runs of
the default-sized workloads gave these medians (milliseconds). The before and
after multi-source rows use the same 2,100 price slots and 20 measured cycles:

| Workload | Apply | Fresh / consolidate | Build books | Evaluate | Full cycle | Cycle p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| One transport | 1.859 | 0.856 | 10.544 | 11.624 | 24.971 | 25.944 |
| Two agreeing transports, before | 4.987 | 25.135 | 10.594 | 11.711 | 52.097 | 57.475 |
| Two agreeing transports, after | 4.900 | 13.482 | 10.619 | 11.625 | 40.831 | 46.700 |
| Two transports, 21 conflicts, before | 4.898 | 25.077 | 10.604 | 11.618 | 52.207 | 54.864 |
| Two transports, 21 conflicts, after | 4.876 | 13.620 | 10.585 | 11.419 | 40.812 | 47.211 |

The agreeing run held the same 2,100 price slots and produced the same 6,000 books
and opportunities as the one-transport run, while storing 4,200 observations and
applying 600 observations per cycle. The conflicting run suppressed 21 slots on
each of 20 measured cycles: 420 conflicts in total, 41,580 executable quote
appearances, and 5,940 books and opportunities. The agreeing run's opportunity
digest matched the one-transport run exactly:
`7be7cdd1f19ecc850fba82bd158b5ae107d2d31f63d5e3905e106a59f2ce5e1f`.

`cProfile` put 1.129 seconds across 23 calls to `consolidate_quotes()` in the
initial multi-source workload. Consolidation now groups by existing ID values,
avoids redundant output sorts, and skips detailed checks when one observation is
newest. The live store also avoids constructing observation keys when no source
has been invalidated. Three runs after these changes put the median full cycle
between 40.777 and 41.591 ms, versus 52.097 ms in the original run. The first
after run above reduced its fresh/consolidate stage from 25.135 to 13.482 ms.
These are local diagnostics, not an operational throughput or latency promise.

For a fresh profile:

```text
uv run python -m cProfile -o ../arbiscan-profile.pstats scripts/benchmark_detection.py
uv run python -c "import pstats; pstats.Stats('../arbiscan-profile.pstats').sort_stats('cumtime').print_stats(20)"
```

Pass `--transports-per-provider 2` after the script name when profiling the
overlapping-feed workload.

## Historical replay throughput workload

Run the complete Phase 18 replay over a fixed synthetic quote corpus:

```text
uv run python -m scripts.benchmark_replay
```

The default corpus has 10 events, two markets per event, two price providers,
two agreeing transport feeds, and three update batches. It contains 320
transport observations at four simulated instants. One warm-up and three
measured runs each call `run_backtest()` with the same corpus and registry.
The timer covers the full replay, including multi-source state, freshness and
consolidation, market-book construction, arbitrage evaluation, provider-only
analysis, report construction, and the corpus digest computed by replay.
Corpus generation and cross-run signature checks happen outside the timer.
The report includes a
corpus digest, a signature over selected semantic report fields, fixed counts,
median/p95/maximum replay time, and observation throughput over all measured
runs. A changed report signature between repeats fails the command.

The CLI accepts event, market, provider, batch, update, transport, conflict,
warm-up, and measurement counts. For the larger workload measured below:

```text
uv run python -m scripts.benchmark_replay --events 50 --markets-per-event 3 --providers 3 --update-batches 20 --updates-per-batch 150
```

On the same Windows 10 / CPython 3.13.15 / Ryzen 7 5800X machine, one local
series of three measured full replays per workload gave:

| Events | Batches | Observations | Evaluations / detections | Median replay | Observations/s |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 4 | 320 | 80 | 32.121 ms | 9,971.6 |
| 20 | 11 | 2,040 | 660 | 356.864 ms | 5,721.5 |
| 50 | 21 | 8,100 | 3,150 | 2,057.510 ms | 3,953.4 |

The default corpus digest was
`4a1cb2bf9c3847c0dede9fa176c6bddbced96d6fb456700098d67d7f3eb7c70f`;
its report signature was
`f25f34cc3f6f5411fb398d00354c004cd22601dea1474d538e341a84f499be04`.
All repeated reports in each workload had the same signature. The optional
`--conflicting-slots` input keeps equal-time transport conflicts in a fixed
subset; a regression test verifies that a conflicted, incomplete market no
longer yields a detection.

This is an in-memory replay rate, not historical import throughput or a live
provider capacity claim. It excludes SQL history loading, provider HTTP,
normalization, matching, alerts, and UI. The synthetic quotes stay fresh and
produce theoretical arbitrage in every complete market; no execution or
realized profit is modeled. `cProfile` of the 20-event workload attributed
about 0.50 of 1.06 profiled `run_backtest()` seconds to 44 market-book builds.
The observed throughput decline at larger loads warrants a workload-specific
target before any replay architecture change.

## Event-matching scale workload

Run the deterministic Phase-8 matcher against a canonical event catalog without
provider I/O or alias preparation:

```text
uv run python -m scripts.benchmark_matching
uv run python -m scripts.benchmark_matching --events 500 --measured-runs 10
```

The benchmark creates one football competition with unique participant pairs and
one provider event per canonical event. Every provider event has exactly one valid
canonical match. It now measures three distinct paths against the same semantic
decision digest:

1. an exhaustive cold baseline with the legacy full-registry diagnostic scan;
2. an indexed cold lookup using canonical sport/competition/participant indexes;
3. repeated exact-evidence cache hits after the indexed cold decisions are retained.

For the default 250-event workload, the exhaustive cold path performs 62,500
candidate evaluations. The indexed cold path performs 250 candidate evaluations:
one hard-filter survivor per provider event. Repeated unchanged evidence performs
zero candidate evaluations because the bounded exact-evidence cache can return the
previous immutable decision directly.

The canonical registry owns immutable indexes by sport, by sport/competition, and
by sport/competition/unordered participant identity set. These keys correspond only
to existing hard filters; time tolerance, participant ordering, provider-reference
conflicts, stage/venue checks, confidence scoring, and ambiguity rejection still run
through the production matcher for every indexed survivor.

The indexed path uses compact diagnostics by default. If no event survives a hard
filter, it retains the failing stage reason (sport, competition, or participant
identity) without materializing one rejection record for every unrelated registry
event. If an event survives the hard filters, candidate-specific rejection evidence
and the final match/ambiguity explanation remain unchanged. Set
`exhaustive_diagnostics=True` on `EventMatcher` when a debugging/audit workflow
explicitly needs the legacy per-event rejection list. The benchmark checks that the
exhaustive and indexed paths have identical status, matched event, confidence, and
candidate semantics through a shared digest; diagnostic cardinality is deliberately
not part of that parity contract.

Phase 19 also keeps the bounded exact-evidence decision cache from the previous step.
The cache key is the complete immutable `NormalizedEventEvidence`, so changes to
provider identity, external event ID, sport, competition, participants/order policy,
scheduled start, stage, or venue cannot reuse a stale decision. Cache capacity is
explicit and zero disables caching.

No production latency SLO is inferred from this credential-free workload. The
remaining deployment work is to profile the exhaustive baseline, indexed cold path,
and repeated cached path on the intended machine and then validate event matching
against retained real multi-provider data.

## Provider polling and normalization workload

Run the two real provider adapters against their existing schema-faithful local
fixtures and feed the resulting snapshots through production strict normalization:

```text
uv run python -m scripts.benchmark_provider_pipeline
uv run python -m scripts.benchmark_provider_pipeline --measured-runs 20
```

The workload covers The Odds API and OddsPapi football fixtures. Each measured run
constructs a fresh adapter and fixture transport, discovers one competition and event,
fetches its odds snapshot, builds the already-known canonical identity context outside
the normalization timer, and then calls `normalize_source_snapshot()`. Polling and
normalization timings are reported separately with median, nearest-rank p95, and
maximum latency.

The fixture transport performs local file reads instead of network I/O, so polling
numbers measure adapter request orchestration, JSON decoding, schema validation, and
source-record construction rather than internet latency or upstream service capacity.
The Odds API workload performs four adapter requests and yields two source markets,
six selections, and six canonical quotes. The OddsPapi workload performs five adapter
requests and yields three source markets, three selections, and three canonical
quotes. These counts are regression-checked.

Every identical run must retain the same source/normalized semantic digest. The
benchmark therefore establishes a safe profiling boundary for future connection
pooling, parser, request-catalog caching, or normalization changes without treating
fixture timing as a production SLO.

## Remaining Phase 19 work

Profile the new provider-pipeline and event-matching workloads on an intended
deployment machine, then validate both against retained real multi-provider data.
Persistence and historical replay still need representative retained-data measurements
beyond their existing synthetic baselines. Extend the synthetic multi-source
measurement to observed transport overlap and deployment-sized loads. Define
operational latency/throughput targets from actual provider contracts and deployment
capacity, then profile any further changes against fixed workloads and verify equal
results before promoting them.
