# Phase 9 completion — Market alignment and best-price book construction

- Status: **Complete**
- Date: 2026-09-15
- Roadmap phase: Phase 9 — Market alignment and best-price book construction
- Pull request: #12
- Squash merge commit: `de58e872c1d9bd7bee74b6e7b0fe061566e45b5a`

## Objective

Phase 9 constructs one canonical, auditable comparison book for each eligible event/market before arbitrage mathematics runs.

The phase replaces the temporary best-quote selection that existed in the Phase-5 vertical slice with a dedicated provider-independent `marketbook` boundary. Quotes can influence arbitrage only after canonical identity, provider policy, status, historical availability, freshness and completeness checks have succeeded.

## Deliverables

### Canonical market-book boundary

`src/arbiscan/marketbook/` provides:

- `CanonicalMarketBook`;
- `BestPriceOutcome`;
- `MarketBookFreshness`;
- `MarketBookBatch`;
- `MarketBookDiagnostic` and stable diagnostic codes;
- `ProviderBookPolicy`;
- `build_market_books()`.

A canonical market book contains the canonical event and market, the exact expected selection set, one selected best `OddsQuote` per expected selection, freshness metadata and construction diagnostics.

### Exact market alignment

Quotes are grouped by exact canonical `MarketId` and `SelectionId`. Different canonical market variants never cross-fill one another.

Adversarial coverage proves, among other cases, that:

- `TOTAL_POINTS` 2.5 cannot obtain a missing outcome from `TOTAL_POINTS` 3.5;
- a selection belonging to another canonical market is rejected;
- incomplete markets never reach arbitrage mathematics.

### Defensive quote validation

Before a quote can compete for best price, Phase 9 validates:

- duplicate quote identity;
- canonical event existence;
- canonical market existence;
- canonical selection existence;
- event/market consistency;
- selection/market consistency.

Violations fail closed and remain traceable through stable diagnostics.

### Provider policy

`ProviderBookPolicy` supports explicit inclusion and exclusion sets. Provider filtering happens before best-price selection. If filtering removes the only eligible quote for an expected outcome, the market becomes incomplete and is rejected.

### Status, historical availability and freshness

Only `QuoteStatus.ACTIVE` quotes are eligible.

Historical availability and freshness are independent constraints:

- `ingested_at <= as_of` is mandatory, so historical replay cannot use data ArbiScan had not yet received;
- `source_timestamp` is used for freshness when available, otherwise `ingested_at`;
- future effective timestamps are rejected;
- quotes older than the configured freshness window are rejected;
- inactive, future-ingested, future-effective and stale quotes are removed before best-price selection.

The dedicated `FUTURE_INGESTION` diagnostic prevents an old source timestamp from masking a future ingestion timestamp.

### Deterministic best-price selection

For every expected canonical selection, the winning eligible quote is selected by:

1. highest decimal price;
2. newest effective timestamp on equal price;
3. lexically smallest canonical provider ID;
4. lexically smallest quote ID.

Input/provider response ordering is never a tie-breaker. The original `OddsQuote` is retained, preserving provider attribution and complete provenance.

### Outcome completeness

A book is emitted only when:

- the canonical market defines at least two outcomes; and
- every expected canonical selection has at least one eligible quote after all Phase-9 filters.

Missing selections produce `INCOMPLETE_MARKET`. Canonical markets with fewer than two outcomes produce `INSUFFICIENT_OUTCOMES` and do not enter arithmetic.

### Vertical-slice integration

`run_vertical_slice()` now builds canonical market books before arbitrage evaluation and calls the mathematical core with exactly:

```text
evaluate_market(book.quotes, book.expected_selection_ids, ...)
```

`VerticalSliceResult` exposes both `market_books` and `market_book_diagnostics` while retaining the older `book_issues` compatibility surface.

`INSUFFICIENT_OUTCOMES` is mapped to legacy `BookIssueCode.EVALUATION_REJECTED`; `INCOMPLETE_MARKET` retains the existing incomplete-market compatibility code.

## Review corrections completed before merge

Automated review identified two valid defects and both were corrected before the Phase-9 merge:

1. a persisted quote with historical `source_timestamp` but `ingested_at > as_of` could otherwise appear available during replay;
2. `INSUFFICIENT_OUTCOMES` was initially absent from the legacy `book_issues` compatibility output.

Regression tests now prove both behaviors remain fixed.

## Final validation evidence

The exact final PR head `0c73134171c6f0008cb4cd009b138dfda74747c8` passed:

```text
uv lock --check      PASS
Ruff format          PASS — 131 files formatted
Ruff lint            PASS
strict mypy          PASS — 0 issues in 90 source files
pytest               PASS — 138 tests
pip-audit            PASS — no known vulnerabilities
CodeQL Python        PASS
CodeQL Actions       PASS
```

All inline review conversations were resolved before the guarded squash merge.

The resulting `main` commit is:

```text
de58e872c1d9bd7bee74b6e7b0fe061566e45b5a
```

Post-merge verification on that exact squash commit also completed successfully:

```text
quality              PASS
Analyze (python)     PASS
Analyze (actions)    PASS
```

This closes the verification gap that remained immediately after the Phase-9 merge.

## Architecture decision

ADR-0009 is the normative record for:

- exact canonical market identity as the alignment boundary;
- defensive quote-reference validation;
- provider filtering before price comparison;
- active/historically-available/fresh quote eligibility;
- deterministic price/freshness/provider/quote tie-breaking;
- mandatory outcome completeness;
- book-level provenance/freshness diagnostics;
- separation between market-book construction and arbitrage mathematics.

## Exit criteria

- **Every candidate arbitrage has a traceable best-price book:** satisfied.
- **Incomplete markets are rejected:** satisfied.
- **Semantically incompatible market variants are separated:** satisfied.
- **Stale-data policy is enforced before arbitrage math:** satisfied.
- **Historical replay cannot see future-ingested data:** satisfied.
- **Provider attribution is preserved:** satisfied.
- **Provider inclusion/exclusion is configurable:** satisfied.
- **Construction is deterministic:** satisfied.
- **Legacy skip diagnostics remain available:** satisfied.
- **Exact merged `main` commit passed post-merge quality and CodeQL workflows:** satisfied.

## Explicitly deferred

Phase 9 intentionally does not implement:

- continuous/incremental ingestion, quote expiry and live refresh scheduling (Phase 10);
- durable persistence/audit storage for book history (Phase 11);
- stake limits, fees, commissions, currencies and execution realism (Phase 12);
- service/API exposure of market books (Phase 13);
- later observability expansion (Phase 14);
- fuzzy equivalence between different canonical market IDs;
- automated wagering.

## Completion

Phase 9 is formally closed. Its implementation, review corrections, protected merge and post-merge verification are all complete. The next dependency is Phase 10 — Real-time ingestion and freshness control.
