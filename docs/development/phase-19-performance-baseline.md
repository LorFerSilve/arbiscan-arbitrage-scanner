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

## Reference deployment load matrix

The production multi-source benchmark now supports partial transport overlap instead
of only the two extremes of one transport or full duplication. Use
`--overlap-slots` to duplicate only a deterministic subset of canonical
price-provider slots:

```text
uv run python scripts/benchmark_detection.py --transports-per-provider 2 --overlap-slots 525
```

With partial overlap, the report records the number and fraction of overlapping slots,
the exact initial observation count, and the actual measured update observations.
Equivalent transport overlap must preserve the single-source market-book,
opportunity, and result digest semantics. Material conflicts remain restricted to
slots that actually overlap.

For repeatable capacity exploration, run the Phase 19 reference load matrix:

```text
uv run python -m scripts.benchmark_load_matrix
uv run python -m scripts.benchmark_load_matrix --profile reference
uv run python -m scripts.benchmark_load_matrix --profile safety_margin
```

The checked-in profiles are explicit engineering reference loads, not claimed
production traffic or SLOs:

| Profile | Events | Markets/event | Providers | Quote slots | Updates/cycle | Transport overlap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| reference | 100 | 3 | 3 | 2,100 | 300 | 25% |
| scaled | 250 | 3 | 4 | 7,000 | 750 | 25% |
| safety_margin | 400 | 4 | 4 | 14,400 | 1,200 | 35% |

Each profile first runs an equivalent single-source semantic control and then the
partial-overlap production multi-source path. The matrix fails if market-book count,
opportunity count, or the stable detection digest changes under equivalent transport
overlap. Timings are reported only for the multi-source run, while the matrix digest
covers the fixed workload definitions and semantic result digests rather than
machine-dependent timing values.

The safety-margin profile is deliberately larger than the reference profile, but the
reference profile is not yet an asserted production envelope. Real provider
contracts, retained traffic distributions, deployment hardware, and observed
transport overlap still need to replace these provisional dimensions before Phase 19
can claim its production-scale exit criterion.

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

## Diagnostic-heavy market-book workload

The Phase 19 market-book builder now groups quote-level diagnostics by canonical
market once, instead of scanning all accumulated diagnostic records for every
complete book. This removes the repeated cross-market scan when a feed supplies
many inactive, stale, or otherwise rejected quotes. It does not relax quote
eligibility, alter the globally sorted diagnostics, or change the sorted
per-market `construction_diagnostics` attached to complete books. Incomplete
markets still report their own diagnostics through the global batch.

The original detection benchmark uses clean executable quotes and therefore
cannot measure this specific bottleneck. Use the dedicated rejected-quote
workload instead:

```text
uv run python -m scripts.benchmark_marketbook_diagnostics
uv run python -m scripts.benchmark_marketbook_diagnostics --events 400 --rejected-per-valid 2
```

The default fixture includes 100 events, three markets per event, three
providers, and two additional suspended quote versions per valid quote. It
records median, p95, and maximum `build_market_books()` time after warm-up,
plus market/diagnostic counts and a stable output digest. Each run validates
that global diagnostics agree with every emitted book's per-market diagnostics.
Use `--rejected-per-valid 0` as a clean-feed control.

This is a synthetic CPU-only workload, **not** observed provider rejection
rates or a service-level objective. Measure on the target deployment hardware
against an unchanged corpus before claiming a concrete speedup. The regression
tests protect diagnostic attribution, input-order independence, and market
scope; general quality gates are unchanged.

## Phase 19 diagnostic-index before/after validation

The diagnostic-heavy builder benchmark was run locally on Windows 10
(`Windows-10-10.0.19045-SP0`, CPython 3.13.15) against the two relevant
implementations:

- Before: main commit `51e2620aed952c145c6d508ae0e6b2b66dbfc920`
  (before PR #62). The same benchmark script was copied into a detached
  worktree containing the previous builder.
- After: main commit `e1314a9d4f6b4f603b853789d151fd17f84fce9d`
  (PR #62, diagnostic indexing).

Both executions used 100 events, three markets per event, three price
providers, 2,100 valid quotes, and 4,200 additional suspended quotes.
There were 300 complete books, 4,200 diagnostics, 10 warm-up runs, and
100 measured runs, with the same semantic result digest:
`cc41495cd6273cf36517f64113373275c3c0783178a548a04ee0dcb2a7bd1bbf`.

| Market-book build time | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| Median | 159.537 ms | 31.303 ms | 80.38% |
| Nearest-rank p95 | 176.968 ms | 40.734 ms | 76.98% |
| Maximum observed | 211.465 ms | 62.112 ms | 70.63% |

Median speedup was **5.10x** on this particular diagnostic-heavy synthetic
workload. The two runs were sequential rather than interleaved, so background
machine load and thermal conditions were not controlled. This is not an
end-to-end application speedup, a real-feed rejection distribution, or a
production latency guarantee. The digest match proves equal coverage of the
benchmark's recorded book/diagnostic identity fields, not equivalence of every
possible source input.

## Aggregate-calibrated multi-source load investigation

The checked-in `benchmark_load_matrix` reference/scaled/safety-margin
profiles are engineering assumptions, not observed traffic. A local aggregate
profile can now replace their sizing without committing raw provider payloads,
account identifiers, API credentials, or quote-level logs.

Create a local `local_data/aggregate-load-profile.json` (this directory is
Git-ignored). The following **illustrative** numbers are the pre-existing
synthetic reference workload, **not observed provider statistics**:

```json
{
  "name": "example_not_observed",
  "events": 100,
  "markets_per_event": 3,
  "providers": 3,
  "updates_per_cycle": 300,
  "transports_per_provider": 2,
  "overlap_bps": 2500,
  "warmup_cycles": 2,
  "measured_cycles": 10
}
```

Calibrate these fields from a documented, permitted measurement window:
- `events`: distinct pre-match events concurrently tracked, not cumulative
  events throughout the day;
- `markets_per_event`: a deliberately documented approximation of the tracked
  market count per event; the fixture assumes one 3-way winner market and
  `markets_per_event - 1` two-outcome totals per event;
- `providers`: distinct **price providers** represented in that window;
- `updates_per_cycle`: typical quote-slot updates over the scanner's
  actual poll/evaluation interval, bounded by the fixture's quote slots;
- `transports_per_provider`: maximum copies from synthetic transports
  **for each overlapping quote slot** (the matrix requires at least two).
  This is **not** the observed number of independent provider feeds. The
  benchmark sends every non-overlapping slot through transport 0 only;
  secondary transports have no unique-only coverage. With
  `overlap_bps: 0`, the secondary transports contribute no observations.
  To model independently covered/disjoint secondary feeds, a different
  corpus or a real-data replay is necessary;
- `overlap_bps`: percentage of price-provider-selection slots covered by
  multiple transports, expressed in basis points, 0 to 10,000; for example,
  2,500 means 25%;
- `warmup_cycles` and `measured_cycles`: measurement settings, not traffic.

Run from the repository root after `uv sync --locked`:

```text
uv run python -m scripts.benchmark_load_matrix --profile-file local_data/aggregate-load-profile.json
uv run python -m scripts.benchmark_load_matrix --profile-file local_data/aggregate-load-profile.json --warmup-cycles 10 --measured-cycles 100
uv run python scripts/quality.py --all
```

The JSON loader accepts **only** those nine aggregate fields and rejects
unknown keys, credential fields, wrong types, and invalid dimensions.
The existing load-matrix code still runs both a single-source control and
a multi-source path for the same profile and fails on changed opportunity
counts, market-book counts, or semantic detection digest. It reports
per-stage median, p95, maximum, and overlap diagnostics.

**Scope limit:** `transports_per_provider` is a duplicate-overlap
multiplier, not an independent-feed-count calibration. Using an observed
number of feeds for this field may **underestimate** the actual load whenever
secondary feeds carry their own non-overlapping markets or quotes.

**Scope limit:** this calibrates the *shape* of a deterministic synthetic
multi-source detector workload. It does not replay actual cross-provider
odds, event-matching errors, cancellation rates, status changes, timestamp
skew, network latency, or uneven market/provider distributions. The
existing `benchmark_provider_pipeline` separately exercises the two
fixture-backed provider adapters; their football fixtures refer to
different events and are not representative matched live traffic.
For an actual representative-data performance result, next obtain
authorized, locally retained and privacy-reviewed multi-provider
snapshots with shared event identities and measure matching,
normalization, quote consolidation, and book construction together.
Keep raw material local; publish only aggregate dimensions and
non-sensitive timing results when permitted.

## Windows 10 reference and scaled load-matrix observations (2026-10-23)

These are **user-measured, synthetic** baseline results on Windows 10
(`Windows-10-10.0.19045-SP0`, CPython 3.13.15), before introducing the
optional distributed-feed model. They were taken with main at
`6e4a25e1fc2d93d042a7c2fe64afc0e6b1da0271` (PR #63).

| Metric | Reference (10 warm-up, 100 measured) | Scaled (2 warm-up, 8 measured) |
| --- | ---: | ---: |
| Events | 100 | 250 |
| Markets per cycle | 300 | 750 |
| Price providers | 3 | 4 |
| Canonical quote slots | 2,100 | 7,000 |
| Overlapping slots | 525 | 1,750 |
| Updates requested per cycle | 300 | 750 |
| Mean transport observations updated per cycle | 373.5 | 906.25 |
| Median full-cycle latency | 32.169 ms | 92.644 ms |
| Nearest-rank p95 full-cycle latency | 43.613 ms | 102.792 ms |
| Maximum full-cycle latency | 49.702 ms | 102.792 ms |
| Median apply | 2.579 ms | 6.421 ms |
| Median fresh/consolidate | 6.479 ms | 22.000 ms |
| Median market-book | 10.762 ms | 31.293 ms |
| Median evaluate | 11.960 ms | 30.118 ms |
| Reported core updates per second | 115,549.0 | 115,295.3 |
| Detected market books across all measured cycles | 30,000 | 6,000 |
| Synthetic opportunities across all measured cycles | 30,000 | 6,000 |
| Equal-overlap diagnostics across all measured cycles | 52,500 | 14,000 |
| Conflicts | 0 | 0 |
| Single-source vs multi-source semantic parity | true | true |

Reference matrix digest:
`c309fdef3ae829de728a6bc076635ce24deff70710c6784916868694a9d78936`.
Scaled matrix digest:
`62c53f60a92bc71e399ffa29fde965d95bdde0a0cee7aa12e05426b559106c52`.
The benchmark's result and matrix digests depend on the **workload and
number of cycles**; digests from different profiles or different cycle
counts should not be expected to match. Parity checks compare the same
workload within each run.

Scaled has 3.33x the canonical quote slots and 2.50x the events; its
median full-cycle latency is 2.88x the reference median. Reported
`core_updates_per_second` is based on the **apply stage only**, not
end-to-end pipeline throughput. At 115,549.0 versus 115,295.3,
the apply-stage rate differs by about 0.22%; this alone cannot establish
linear scaling or a production SLO. The scaled profile has only eight
measured cycles, so its nearest-rank p95 is necessarily its maximum
observation and is **not** a robust tail-latency estimate.
The reported opportunities are deliberately synthetic per-cycle detections,
not real arbitrage opportunities or distinct trading signals.

A comparable higher-sample scaled measurement can be obtained with:

```text
uv run python -m scripts.benchmark_load_matrix --profile scaled --warmup-cycles 10 --measured-cycles 100
```

## Optional independently covered and missing-feed scenarios

The original load matrix retains its default semantics. New **opt-in**
`--coverage-mode distributed` sends every overlapping canonical quote slot
through all configured transport copies, but distributes each
**non-overlapping** slot deterministically across transports rather
than always assigning it to transport zero. This represents unique-only
coverage on secondary feeds without changing the underlying price origin
or canonical quote identity. `--missing-bps` removes a deterministic
tail percentage of canonical quote slots from **every feed**, including
update cycles; it models absent coverage rather than stale or suspended
quotes.

```text
uv run python -m scripts.benchmark_load_matrix --profile reference --coverage-mode distributed
uv run python -m scripts.benchmark_load_matrix --profile reference --coverage-mode distributed --missing-bps 1000 --warmup-cycles 10 --measured-cycles 100
uv run python -m scripts.benchmark_load_matrix --profile-file local_data/aggregate-load-profile.json --coverage-mode distributed --missing-bps 1000
```

The first distributed command preserves all 2,100 canonical slots,
with 525 overlapping slots and 1,575 unique-only slots divided
deterministically between transport 0 and transport 1. The second
command removes 10% of the slots completely. The benchmark compares
single-source and distributed multi-source **under the same missing
mask** and rejects diverging market books, opportunity counts, or
opportunity digests. The report includes the effective coverage mode,
missing-slot count, and per-transport unique-only slot counts.

Conflicting overlap remains a **separate fail-closed test scenario**,
using the existing `--conflicting-slots` option in the detection
benchmark and dedicated unit tests; conflict-injected output is not
required to match a conflict-free single-source baseline. This is a
synthetic feed-coverage experiment, **not** a claim that the actual two
provider APIs expose these same events, prices, transport overlaps, or
missingness distributions. No raw captured provider records have been
added to the repository.

## Windows 10 distributed-feed and missing-coverage measurements (2026-10-23)

After merging the optional distributed coverage scenario (PR #64, main
commit `4ca2c8c6256926505ad422a4667814edbb3cbb2f`), the same
Windows 10 machine running CPython 3.13.15 was used to profile two
additional synthetic reference workloads. Both scenarios used 100 events,
three markets per event, three price providers, two transports, 25%
slot overlap, 300 requested updates per cycle, 10 warm-up cycles, and
100 measured cycles.

Commands:

```text
uv run python -m scripts.benchmark_load_matrix --profile reference --coverage-mode distributed --warmup-cycles 10 --measured-cycles 100
uv run python -m scripts.benchmark_load_matrix --profile reference --coverage-mode distributed --missing-bps 1000 --warmup-cycles 10 --measured-cycles 100
```

| Measurement | Primary-only unique coverage (previous 100-cycle reference) | Distributed unique coverage | Distributed with 10% missing |
| --- | ---: | ---: | ---: |
| Active canonical quote slots | 2,100 | 2,100 | 1,890 |
| Transport observations initially retained | 2,625 | 2,625 | 2,415 |
| Unique-only slots by transport | (1,575, 0) | (787, 788) | (682, 683) |
| Overlapping canonical slots | 525 | 525 | 525 |
| Mean update observations per cycle | 373.5 | 373.5 | 344.1 |
| Median full-cycle time | 32.169 ms | 32.433 ms | 29.173 ms |
| Nearest-rank p95 full-cycle time | 43.613 ms | 39.936 ms | 34.145 ms |
| Maximum full-cycle time | 49.702 ms | 45.130 ms | 41.525 ms |
| Median apply | 2.579 ms | 2.655 ms | 2.540 ms |
| Median fresh/consolidate | 6.479 ms | 6.578 ms | 5.610 ms |
| Median market-book | 10.762 ms | 10.771 ms | 9.654 ms |
| Median arbitrage evaluation | 11.960 ms | 11.805 ms | 10.470 ms |
| Apply-stage observations per second | 115,549.0 | 113,048.7 | 115,506.8 |
| Emitted books across 100 cycles | 30,000 | 30,000 | 27,000 |
| Synthetic opportunities across 100 cycles | 30,000 | 30,000 | 27,000 |
| Equivalent-overlap diagnostics across 100 cycles | 52,500 | 52,500 | 52,500 |
| Conflicts | 0 | 0 | 0 |
| Single-source/multi-source semantic parity | true | true | true |

The no-missing distributed reference retained the **same
result digest** as the earlier 100-cycle primary-coverage reference:
`4d078909bf7239a937b4cef8604791f1f8d788b877686b2204e04a2fa6a77315`.
The matrix digests differ because coverage mode is part of the matrix
identity:

- Distributed, zero missing:
  `920cceda2f1784661cdfd47a9359f177775e23079d7e97d19565ebba9b0e9333`
  (result digest:
  `4d078909bf7239a937b4cef8604791f1f8d788b877686b2204e04a2fa6a77315`).
- Distributed, 1,000 missing basis points:
  `392f6837a48c6e7e2bf50f6de98b5d9eea66d93d1315e63e84447cdc42692db9`
  (result digest:
  `3799073bff5be853f836866315ac361097d11eb2db188be00cf104f5b09b4692`).

The distributed, no-missing median was 0.264 ms (+0.82%) above the
previous primary-coverage median; that is small relative to ordinary
single-machine benchmark variation and is **not** evidence of a
statistically significant regression. Moving from distributed full
coverage to 10%-missing coverage lowered the median by 3.260 ms
(10.05%) and reduced total emitted books by 10%. These are different
amounts of work, so lower latency is not evidence that missing data
improves the production algorithm.

**Critical missing-data interpretation:** `missing_slots` currently
removes the *tail* of the deterministically generated quote-slot
sequence. The generator orders slots by event, then market, provider,
and selection. With seven selections per event and three providers,
each event contributes 21 canonical quote slots. Removing the final
210 of 2,100 quote slots therefore removes **all provider quotes
for the last ten events** (30 complete markets per cycle), not a
randomly distributed 10% of individual selections across all events.
The loss of exactly 3,000 books across 100 measured cycles reflects
this scenario construction. The remaining 90 events still contain
complete coverage, so this run does **not** validate partially missing
selection legs, unbalanced bookmaker market coverage, or how missing
data affects arbitrage completeness and false-positive rejection in
those conditions. `all_semantic_parity` verifies equality between
control and multi-source implementations under the **same** artificial
missing-slot mask; it does not establish that missing markets are
handled correctly for every possible sparsity pattern.

**Next validation after dispersed masks:** exercise a distinct
market-level outage scenario and changing quote availability over
multiple cycles, then validate authorized real multi-provider data.
A static seeded mask is necessary, but not sufficient, to establish
production fail-closed behavior.

## Deterministic dispersed and missing-selection-leg scenarios

In addition to the original `--missing-bps` **tail** mask, Phase 19 can now
choose a missing-data pattern with `--missing-pattern` and a non-negative
`--missing-seed`. The mask is fixed for all warm-up and measured cycles and
applies to the *same canonical price-provider slots* in the single-source
control and multi-source runs; a masked slot is absent from **every**
transport. This isolates the effect of missing coverage from transport
overlap and avoids accidental differences in detection semantics.

- `tail` (default): remove the last N generated slots, preserving the
  behavior and previously recorded reference digests.
- `dispersed`: rank quote slots with a reproducible SHA-256 key derived
  from the slot index and seed; remove the N lowest-ranked slots,
  spreading missing quotes across events, markets, outcomes and providers.
  An unavailable quote from one provider may still be replaced by an
  available quote from another provider, so this often leaves markets
  complete.
- `selection`: rank canonical selection IDs and remove the selected
  outcomes **from all providers and transports**. One missing required
  outcome makes its entire market incomplete and must prevent an
  executable market book and an arbitrage opportunity. The requested
  missing slot count must be divisible by the number of price providers;
  otherwise the benchmark fails rather than silently rounding a partial
  selection group.

For the measured reference profile (three price providers, 2,100 price
slots), `--missing-bps 1000` removes exactly 210 slots, equivalent to
70 complete selection legs in `selection` mode.

```text
uv run python -m scripts.benchmark_load_matrix --profile reference --coverage-mode distributed --missing-bps 1000 --missing-pattern dispersed --missing-seed 42 --warmup-cycles 10 --measured-cycles 100
uv run python -m scripts.benchmark_load_matrix --profile reference --coverage-mode distributed --missing-bps 1000 --missing-pattern selection --missing-seed 42 --warmup-cycles 10 --measured-cycles 100
```

The workload report now includes `missing_pattern`, `missing_seed`,
`missing_mask_digest`, `complete_markets_per_cycle`,
`incomplete_markets_per_cycle`, `fully_missing_selection_legs`,
`partially_covered_selection_legs`, and affected event/provider counts.
The complete-market count is calculated independently from canonical
selection coverage, not derived from the market-book builder output.
For workloads with no injected price conflicts, a runtime check
requires the emitted book count to equal the independently expected
complete-market count. With injected conflicts, it can only decrease,
never exceed that count. A book cannot be built from an absent required
selection leg, even if an independent transport still serves other
outcomes.

These scenarios remain synthetic and use **static** missing masks.
They do not model dynamically recovering quotes, late provider
revisions, real missingness correlations, timestamp skew, or
unavailable network responses. Per-market completeness applies to
canonical **selection legs**, not a requirement that *all* providers
cover all markets. For conflict-injection benchmarks, the configured conflicting slots
are chosen from **unmasked overlapping quote slots**. The benchmark
rejects a configuration that does not retain enough overlapping slots
to inject the requested number of conflicts, rather than silently
reporting fewer conflicts. Conflicting same-time overlap remains a
separate fail-closed quote-consolidation behavior under test.

## Windows 10 dispersed versus complete-selection outage results (2026-10-23)

These local measurements were supplied after PR #66
(`aada9fb2d043046457b837983c5dd07ecfe192be`) on Windows 10
(`Windows-10-10.0.19045-SP0`, CPython 3.13.15). Both used the
synthetic `reference` profile: 100 events, three markets per event,
three price providers, two transports, 25% configured overlap
(525 of 2,100 original slots), 300 requested updates per cycle,
10 warm-up cycles, and 100 measured cycles. Both enabled
`--coverage-mode distributed --missing-bps 1000 --missing-seed 42`.
Only `--missing-pattern` differed.

```text
uv run python -m scripts.benchmark_load_matrix --profile reference --coverage-mode distributed --missing-bps 1000 --missing-pattern dispersed --missing-seed 42 --warmup-cycles 10 --measured-cycles 100
uv run python -m scripts.benchmark_load_matrix --profile reference --coverage-mode distributed --missing-bps 1000 --missing-pattern selection --missing-seed 42 --warmup-cycles 10 --measured-cycles 100
```

| Metric | A: dispersed per-provider quote slots | B: whole selection legs |
| --- | ---: | ---: |
| Original / active canonical quote slots | 2,100 / 1,890 | 2,100 / 1,890 |
| Missing quote slots | 210 (10%) | 210 (10%) |
| Initially retained observations across transports | 2,347 | 2,382 |
| Unique-only slots: transport 0 / 1 | 716 / 717 | 692 / 706 |
| Events with at least one missing slot | 88 | 50 |
| Partially covered selection legs | 185 | 0 |
| Fully absent selection legs | 1 | 70 |
| Complete / incomplete markets per cycle | 299 / 1 | 240 / 60 |
| Market books across 100 cycles | 29,900 | 24,000 |
| Synthetic opportunities across 100 cycles | 29,900 | 24,000 |
| Equivalent-overlap diagnostics across 100 cycles | 45,700 | 49,200 |
| Price conflicts | 0 | 0 |
| Mean update observations / cycle | 333.97 | 338.77 |
| Median apply time | 3.294 ms | 3.268 ms |
| Median fresh/consolidate time | 8.021 ms | 8.246 ms |
| Median book build time | 14.825 ms | 13.618 ms |
| Median evaluation time | 16.481 ms | 13.219 ms |
| Median full-cycle time | 43.884 ms | 40.191 ms |
| Nearest-rank p95 full-cycle time | 52.968 ms | 133.334 ms |
| Maximum full-cycle time | 68.389 ms | 171.464 ms |
| Apply-stage observations / second | 82,455.8 | 57,208.4 |
| Single-source versus multi-source parity | true | true |

Provenance (reproducible semantic hashes):

- A matrix digest:
  `45c7b03b4bfe417b07dba8711bdab40b3a95d9a0b1e57cf0ce96d4a66e38e929`
- A result digest:
  `96532edec66f2d964354e7733b842103699d886cfb641f0323e515592cac11f3`
- A missing-mask digest:
  `3eb1af4ac7aeef5acd4f241ec7fe540d68df230d00d544e399ea18dc55343cd0`
- B matrix digest:
  `2f720d7fe5ccac42b91c546bf0bec25ef237d4f8d6a66ca6c68bd61c90a7fc9c`
- B result digest:
  `fe4e894379088434bfbd722c238c1fb2ea496d1ec03d206ececf426689d724cc`
- B missing-mask digest:
  `a6f13ae1ede80ba1c89291b78dc1fcd58e018f17e27e5db9afa9a60f93cf6038`

**Correctness finding:** identical total missing quote count has a very
different effect depending on the coverage pattern. A removed quotes
from 88 events but left 299 of 300 markets complete: alternate price
providers supplied at least one remaining quote for all but one
selection leg. B removed 70 whole selection legs across every price
provider and disabled 60 distinct markets (several legs can belong to
the same market), leaving 240 of 300 complete. Its total opportunity
count fell accordingly. These are **synthetic opportunity counts
summed across cycles**, not unique real trading opportunities.
`all_semantic_parity: true` confirms equivalent control and
multi-source result semantics for each fixed mask. The benchmark's
independent selection-completeness assertion checks that incomplete
markets cannot emit books when no conflicts are injected.

**Performance observation, not a speedup claim:** B's full-cycle median
was 40.191 ms versus A's 43.884 ms (8.4% lower), consistent with
building and evaluating fewer complete books. However, B's p95 was
133.334 ms versus A's 52.968 ms (2.52x as large) and its maximum
reached 171.464 ms. Its apply-stage observations/second was also
lower even though median apply time was similar. These runs were
measured at different times, with no recorded control of machine
load, garbage collection, temperature, or scheduling. Thus the
tail-latency difference is **not evidence of a production regression
or of a particular algorithmic bottleneck**. Repeat each identical
benchmark several times (preferably alternating A/B order), keep
the semantic and mask digests fixed, and inspect the distribution of
per-cycle timings before optimizing. These observations are still
synthetic CPU-only timings, not end-to-end provider-network latency.

**Next correctness milestone:** model a feed stopping and recovering
during a sequence of cycles, including stale quote expiry, temporary
market incompleteness, reconnection, and deterministic parity/fail-closed
checks. Fixed missing-data masks cannot test recovery behavior.
Once this behavior is validated, prioritize authorized, representative
real multi-provider replay over further micro-optimization.

## Dynamic transport dropout, expiry, and recovery correctness replay

The fixed missing-quote masks above describe one frozen coverage layout.
To exercise **transitions**, run the new deterministic correctness replay
against the real production `MultiSourceLiveQuoteStore`, its underlying
`LiveQuoteStore` versioning/freshness and eviction methods, actual
`build_market_books()`, and `evaluate_market()`:

```text
uv run python -m scripts.benchmark_feed_recovery
uv run python scripts/quality.py --all
```

This is a **scenario assertion**, not a latency benchmark. It uses one
synthetic football event with two markets and two price providers, a
30-second freshness window, two independent transport IDs and a fixed
clock starting at `2026-01-01T12:00:00Z`. The JSON report includes
phase timestamps, fresh and stale observation counts, evicted revisions,
complete market books, theoretical opportunity counts, equivalent
overlaps, material conflicts and a reproducible semantic result digest.
No live API credentials, networking, or private source captures are used.

The three scenarios are:

1. **Essential transport absent:** one required selection leg is sourced
   *only* through transport 1 (across both price providers), while other
   selections are refreshed on transport 0. At +10 s the silent feed's
   values are still within policy and the market remains complete;
   at +31 s they are **stale** and the market must disappear, even
   before evicting the stale versions. Eviction removes the two stale
   transport observations; a delayed packet with a recent ingestion
   time but its original, expired source timestamp **must not**
   resurrect the incomplete market. At +40 s fresh observations from
   transport 1 restore the missing leg, market book and opportunity.
2. **Redundant transport absent:** transport 0 independently refreshes
   the same required selection leg while transport 1 goes silent.
   Transport 1's stale observations expire and are evicted without
   removing the still-valid market. Fresh transport 1 quotes then
   re-establish overlap on recovery.
3. **Equal-time material conflict:** both transports initially agree
   on the required leg; at +1 s both price providers receive same-time
   contradictory observations across the transports. Consolidation
   suppresses both conflicted executable price slots and the market
   must disappear. At +2 s newer unambiguous transport observations
   resolve both slots and re-enable the market.

The replay fails immediately if any phase's **actual** complete-book or
opportunity count violates its expected outcome, an unavailable target
market remains executable, an expected conflict is missed, or an expired
quote becomes eligible. Unit tests check the exact ordered transitions,
expiry/eviction counts, surviving fallback markets and recovery.
Unlike the previous performance matrix, the replay simulates a
*silent* transport by not updating that feed's state, rather than
instantly deleting quote slots.

**Safety and scope:** expiry is based on the configured source-timestamp
freshness policy, not how recently a stale packet reached the scanner.
One healthy redundant transport may preserve a market; there is no
blanket global shutdown after a provider drops out. These synthetic
checks do **not** test live provider outage discovery, actual network
reconnection, event matching, retry/backoff orchestration, per-provider
health dashboards, or real odds volatility. No claim of production
uptime, SLO compliance or measured latency follows from this replay.

## Remaining Phase 19 work

Profile the provider-pipeline, event-matching, and reference load-matrix workloads on
an intended deployment machine, then validate them against retained real
multi-provider data. Persistence and historical replay still need representative
retained-data measurements beyond their existing synthetic baselines. Replace the
reference matrix's provisional scale and overlap assumptions with observed traffic
and transport-overlap distributions. Define operational latency/throughput targets
from actual provider contracts and deployment capacity, then profile any further
changes against fixed workloads and verify equal results before promoting them.
