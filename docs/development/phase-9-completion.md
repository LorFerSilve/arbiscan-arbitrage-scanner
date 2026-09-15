# Phase 9 completion — Market alignment and best-price book construction

- Status: Complete, pending the normal protected-branch merge gate
- Date: 2026-09-15
- Roadmap phase: Phase 9 — Market alignment and best-price book construction
- Pull request: #12

## Objective

Phase 9 constructs one canonical, auditable comparison book for each eligible event/market before arbitrage mathematics runs.

The phase replaces the temporary best-quote selection that existed in the Phase-5 vertical slice with a dedicated provider-independent `marketbook` boundary. Quotes can influence arbitrage only after canonical identity, provider policy, status, historical availability, freshness and completeness checks have succeeded.

## Deliverables

### 9.1 Canonical market-book models — complete

`src/arbiscan/marketbook/models.py` introduces:

- `CanonicalMarketBook`;
- `BestPriceOutcome`;
- `MarketBookFreshness`;
- `MarketBookBatch`;
- `MarketBookDiagnostic` and stable diagnostic codes;
- `ProviderBookPolicy`.

A `CanonicalMarketBook` contains:

- the canonical `Event`;
- the canonical `Market`;
- the exact expected canonical `SelectionId` set;
- one selected best `OddsQuote` per expected selection;
- freshness metadata;
- construction diagnostics.

The model validates that selected outcomes exactly cover the expected market selections and that every selected quote belongs to the same canonical event and market.

### 9.2 Canonical grouping and semantic isolation — complete

`build_market_books()` groups eligible quotes by exact canonical `MarketId` and `SelectionId`.

The builder does not infer compatibility from provider labels or market kind alone. Different canonical market IDs are separate comparison books, which prevents incompatible variants from being combined.

The adversarial suite explicitly proves that:

- `TOTAL_POINTS` 2.5 cannot obtain its missing outcome from `TOTAL_POINTS` 3.5;
- a selection belonging to another canonical market is rejected rather than used to complete the book.

This makes canonical market identity, including modeled line/period semantics, the Phase-9 comparison boundary.

### 9.3 Defensive quote identity validation — complete

Before a quote may enter price competition, the builder verifies:

- quote IDs are not duplicated in the batch;
- canonical event exists;
- canonical market exists;
- canonical selection exists;
- canonical market belongs to the quote event;
- canonical selection belongs to the quote market.

Violations fail closed and produce traceable diagnostics.

This deliberately revalidates normalized quote references so future replay, persistence or service callers cannot bypass Phase-9 assumptions.

### 9.4 Provider inclusion/exclusion policy — complete

`ProviderBookPolicy` supports:

- optional explicit provider inclusion;
- explicit provider exclusion;
- deterministic validation and ordering;
- rejection of contradictory policies where a provider is both included and excluded.

Provider policy is applied before best-price selection. A filtered provider therefore cannot win an outcome, even if it exposes a higher displayed price.

If filtering removes the only eligible quote for an expected outcome, the canonical market is incomplete and is not emitted.

### 9.5 Status, historical availability and freshness eligibility — complete

Only `QuoteStatus.ACTIVE` quotes may participate.

Historical availability and freshness are checked independently:

- `ingested_at` must be less than or equal to the construction `as_of`; a quote ingested later was not available to ArbiScan at that replay/evaluation time;
- freshness uses `source_timestamp` when available and otherwise `ingested_at`;
- an old source timestamp cannot mask future ingestion;
- effective timestamps after `as_of` are rejected;
- quotes older than the configured freshness window are rejected;
- inactive/suspended/closed/unknown quotes are rejected;
- all eligibility filtering occurs before best-price selection.

`MarketBookFreshness` records:

- construction `as_of`;
- configured freshness window;
- oldest selected quote timestamp;
- newest selected quote timestamp;
- maximum selected quote age through a derived property.

### 9.6 Deterministic best-price selection — complete

For each expected canonical selection, the builder chooses exactly one eligible quote using the binding Phase-9 order:

1. highest decimal price;
2. newest effective timestamp on a price tie;
3. lexically smallest canonical provider ID;
4. lexically smallest quote ID.

Input/provider response order never acts as a tie-breaker.

The original `OddsQuote` is retained in `BestPriceOutcome`, preserving provider attribution plus all existing source/ingestion provenance.

### 9.7 Outcome completeness — complete

The canonical registry defines the expected outcome set for each market.

A market book is emitted only when:

- at least two canonical selections exist; and
- every expected selection has at least one eligible quote after identity, provider, status, historical-availability and freshness filtering.

Missing outcomes produce `INCOMPLETE_MARKET`; the partial market never reaches arbitrage mathematics. Canonical markets defining fewer than two outcomes produce `INSUFFICIENT_OUTCOMES` and are skipped before arithmetic.

### 9.8 Vertical-slice integration — complete

`run_vertical_slice()` now routes normalized quotes through `build_market_books()` before arbitrage evaluation.

The downstream call is structurally:

```text
evaluate_market(book.quotes, book.expected_selection_ids, ...)
```

The previous temporary `_best_quote()` orchestration has been removed from the vertical slice.

`VerticalSliceResult` now exposes:

- `market_books`;
- `market_book_diagnostics`;

while retaining the older `book_issues` compatibility output for existing callers/tests.

Integration coverage proves that:

- `ArbitrageEvaluation.quotes` are exactly the selected Phase-9 book quotes;
- `expected_selection_ids` are exactly the book's canonical expected outcomes;
- generated `Opportunity.quote_ids` trace back to those exact selected quotes;
- incomplete markets are rejected before the arithmetic stage;
- provider exclusions are visible before price selection.

The compatibility bridge maps `INCOMPLETE_MARKET` to the existing incomplete-market issue and `INSUFFICIENT_OUTCOMES` to `EVALUATION_REJECTED`, preserving a skip reason for pre-Phase-9 consumers.

## Diagnostic policy

Stable Phase-9 diagnostic codes cover:

- duplicate quote identity;
- unknown event/market/selection references;
- event/market and selection/market mismatches;
- provider filtering;
- inactive quotes;
- future ingestion;
- future source/effective timestamps;
- stale quotes;
- canonical markets with insufficient outcomes;
- incomplete canonical markets.

Diagnostics are deterministically sorted so equivalent inputs produce reproducible diagnostic output.

## Adversarial fixture coverage

The Phase-9 suite includes regressions for the roadmap's correctness-critical cases:

| Risk | Regression evidence |
| --- | --- |
| stale high price wins comparison | stale quote is excluded before price selection |
| suspended high price wins comparison | inactive quote is excluded before price selection |
| future timestamp influences book | future effective quote is rejected |
| replay uses quote not yet available | future `ingested_at` is rejected even when `source_timestamp` is historical |
| provider should not be considered | include/exclude policy is applied before comparison |
| missing expected outcome | market is rejected as incomplete |
| canonical market has fewer than two outcomes | skip remains visible through legacy `EVALUATION_REJECTED` compatibility issue |
| totals/handicap-style variant mixing | 2.5 and 3.5 total markets remain separate |
| wrong selection attached to market | selection/market mismatch fails closed |
| equal prices depend on input ordering | freshness then stable IDs determine the same winner under reordered input |
| selected price loses source attribution | original `OddsQuote` and provider remain attached to each outcome |
| arbitrage uses a different quote pool | integration regression asserts evaluation/opportunity quote IDs equal the Phase-9 book |

## Test and quality evidence

On the fully code-bearing Phase-9 head before the review-correction regressions and documentation-only completion commits, the repository quality runner completed successfully with:

```text
uv lock --check      PASS
Ruff format          PASS — 127 files formatted
Ruff lint            PASS
strict mypy          PASS — 0 issues in 88 source files
pytest               PASS — 136 tests
pip-audit            PASS — no known vulnerabilities
```

The final protected-branch merge gate re-runs the same complete quality/security suite on the exact final PR head, including the two review regressions described below.

## Review corrections

Automated PR review identified two valid regressions before merge:

1. a persisted quote with `source_timestamp <= as_of` but `ingested_at > as_of` could pass Phase-9 freshness checks because the historical source timestamp masked the fact that ArbiScan had not received the quote yet;
2. a canonical market with fewer than two outcomes produced `INSUFFICIENT_OUTCOMES` in the new diagnostic model but was not forwarded to the pre-existing `book_issues` compatibility API.

The corrections:

- `build_market_books()` now checks `ingested_at <= as_of` independently before evaluating the effective source/freshness timestamp and emits `FUTURE_INGESTION` when violated;
- a dedicated regression proves that a future-ingested high price cannot win a historical/replay book even when its source timestamp lies in the past;
- the compatibility bridge now maps `INSUFFICIENT_OUTCOMES` to `BookIssueCode.EVALUATION_REJECTED`;
- a regression proves the legacy consumer still receives that skip reason.

## Architecture decision

ADR-0009 is the normative record for:

- exact canonical market identity as the alignment boundary;
- defensive quote-reference validation;
- provider filtering before price comparison;
- active/historically-available/fresh quote eligibility;
- the deterministic price/freshness/provider/quote tie-break order;
- mandatory outcome completeness;
- book-level provenance/freshness diagnostics;
- the separation between market-book construction and arbitrage mathematics.

## Exit criteria

- **Every candidate arbitrage has a traceable best-price book:** satisfied. Arbitrage evaluation consumes the exact selected `CanonicalMarketBook.quotes`, and opportunity quote IDs derive from that evaluated quote tuple.
- **Incomplete markets are rejected:** satisfied. A book is emitted only when every expected canonical selection has an eligible quote.
- **Semantically incompatible market variants are rejected/separated:** satisfied. Exact canonical `MarketId` is the grouping key; line/period variants represented by different canonical markets cannot cross-fill outcomes.
- **Stale-data policy is enforced before arbitrage math:** satisfied. Future-ingested, future-effective, stale and inactive quotes are removed before best-price selection and no partial book reaches `evaluate_market()`.
- **Historical replay cannot see future data:** satisfied. `ingested_at` is validated independently against `as_of`.
- **Provider attribution is preserved:** satisfied. Each best outcome carries its original selected `OddsQuote` and canonical `ProviderId`.
- **Bookmaker/provider inclusion/exclusion is configurable:** satisfied through `ProviderBookPolicy`.
- **Construction is deterministic:** satisfied through canonical sorting plus explicit tie-break rules independent of input order.
- **Legacy skip diagnostics remain available:** satisfied for both incomplete and insufficient-outcome markets.

## Explicitly deferred

Phase 9 does not implement:

- continuous/incremental ingestion, quote expiry and live refresh scheduling (Phase 10);
- durable persistence/audit storage for book history (Phase 11);
- stake limits, increments, fees, commissions, currencies, execution latency or price-movement realism (Phase 12);
- service/API exposure of market books (Phase 13);
- observability/metrics for book churn and rejected quotes (Phase 14);
- fuzzy or implicit equivalence between different canonical market IDs;
- automated wagering.

## Merge gate

This completion record does not bypass repository protections. The exact final PR head including ADR-0009, review corrections and this completion file must pass repository quality and CodeQL checks, and all review conversations must be resolved, before squash merge to `main`.