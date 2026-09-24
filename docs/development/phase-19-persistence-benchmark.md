# Phase 19 SQLite persistence baseline

Run from the repository root after `uv sync --locked`:

```text
uv run python scripts/benchmark_persistence.py
```

The benchmark creates separate fresh temporary SQLite databases for individual
`SqliteAuditStore.persist_quote()` writes and one atomic `persist_quotes()` batch per
run. It applies schema migrations before timing, then writes the same fixed
canonical quote corpus in each mode. Both modes read the complete corpus and a
fixed time-window/provider subset. Each new quote creates one audit event; the
individual mode commits per quote, while the batch commits once. Full and filtered
reads include canonical deserialization. The benchmark checks exact quote
ordering/content and audit-event payloads on every run; a mismatch fails the
command. It reports stable corpus and filtered-result SHA-256 digests for cross-run
comparison.

Defaults are 20 events, seven selections per event, three price providers, 420
quotes, one warm-up run, and three measured runs. The filtered read selects provider
zero and events 5 through 15 inclusive (77 quotes). `--events`,
`--selections-per-event`, `--providers`, `--warmup-runs`, and `--measured-runs`
adjust the load. Each pair alternates write-mode order to reduce filesystem-cache
bias. Timing uses a monotonic clock and reports median, nearest-rank p95, and
maximum milliseconds per stage. Throughput divides the total measured quote count
by the total time for that stage, so it includes connection setup, SQL work,
transactions, serialization, and deserialization as applicable. The reported read
timings use the individual-write database; the batch database's reads are checked
for correctness but omitted from read timing summaries. Corpus construction,
migration, and correctness checks are outside the timed stages.

## First local measurement

Windows 10, CPython 3.13.14, default workload, one warm-up plus three measured
runs on a local temporary filesystem:

| Stage | Median | p95 | Throughput |
| --- | ---: | ---: | ---: |
| Write 420 quotes and audit events | 2,189.358 ms | 2,547.564 ms | 182.5 quotes/s |
| Read all 420 quotes | 153.211 ms | 241.478 ms | 2,350.0 quotes/s |
| Read 77 filtered quotes | 28.897 ms | 36.098 ms | — |

The full corpus digest was
`df9f4c4962784a392658d9b9bcff7e795f1c566c71d245079f49b372e5104d09`.
This is a local diagnostic baseline, not a production throughput target. The result
depends on the filesystem and SQLite settings. It covers individual quote writes
and quote-history reads; opportunity evidence, retention, provider I/O, matching,
and end-to-end detection are outside this measurement.

## Batch comparison

On the same Windows 10 host with CPython 3.13.14, a paired default-workload run
with one warm-up and three measured runs produced:

| Write mode | Median for 420 quotes | p95 | Aggregate throughput |
| --- | ---: | ---: | ---: |
| One quote per transaction | 2,132.287 ms | 2,229.422 ms | 194.8 quotes/s |
| One atomic batch transaction | 36.361 ms | 37.097 ms | 11,570.9 quotes/s |

The batch achieved **59.4×** the individual-write throughput in this local sample.
The quote corpus digest remained
`df9f4c4962784a392658d9b9bcff7e795f1c566c71d245079f49b372e5104d09`;
both modes produced identical quote histories and audit payloads. The gain is
consistent with avoiding one connection and commit per quote. This comparison is a
diagnostic measurement on a local temporary filesystem, not a production target.

The store now closes each SQLite connection explicitly after its transaction.
SQLite's connection context manager commits or rolls back but does not close the
handle; open handles prevented temporary benchmark databases from being removed on
Windows.
