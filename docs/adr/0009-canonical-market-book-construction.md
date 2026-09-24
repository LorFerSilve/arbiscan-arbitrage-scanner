# ADR-0009 — Canonical market-book construction policy

- Status: Accepted
- Date: 2026-09-15
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

After Phase 7 normalizes provider semantics and Phase 8 establishes canonical event identity, ArbiScan still needs one correctness-critical boundary before arbitrage mathematics: quotes from multiple providers must be aligned to exactly the same canonical market and outcome set, invalid/stale quotes must be excluded, and exactly one best eligible quote must be chosen for every expected outcome.

`evaluate_market()` intentionally does not perform price shopping or quote eligibility filtering. Mixing those responsibilities into the mathematical core would make arbitrage results depend on provider/filter/freshness policy and would weaken auditability. Phase 9 therefore introduces a provider-independent canonical market-book layer between normalization/matching and arbitrage evaluation.

A false-positive market alignment can fabricate arbitrage even when event identity is correct. Examples include combining totals at 2.5 with totals at 3.5, combining different settlement periods, or completing a missing outcome with a quote from another canonical market. This boundary must therefore fail closed.

## Decision

ArbiScan constructs `CanonicalMarketBook` values through a deterministic, fail-closed market-book builder before any quote set reaches arbitrage mathematics.

### 1. Exact canonical market identity is the comparison boundary

Quotes are grouped by canonical `MarketId` and `SelectionId` only.

The market-book layer does not infer that two different canonical markets are equivalent merely because they share a `MarketKind`, similar provider labels or related parameters. Canonical market identity already contains the modeled settlement semantics established by the domain and normalization layers.

Consequently:

- `TOTAL_POINTS` 2.5 and `TOTAL_POINTS` 3.5 remain separate books;
- different periods remain separate books;
- different handicap lines remain separate books;
- a selection belonging to another canonical market cannot complete the current book.

Future support for additional market equivalence must first be represented explicitly in the canonical model/normalization contract rather than introduced as a fuzzy Phase-9 shortcut.

### 2. Quote identity and referential integrity are revalidated

Before a quote may compete for best price, the builder verifies:

- quote ID is not duplicated within the input batch;
- referenced canonical event exists;
- referenced canonical market exists;
- referenced canonical selection exists;
- canonical market belongs to the quote event;
- canonical selection belongs to the quote market.

Invalid or ambiguous provenance is excluded with a stable construction diagnostic.

This defensive validation is intentional even though normalized quotes should already satisfy these relationships. Phase 9 is a trust boundary for any future quote source, replay/persistence path or service caller.

### 3. Provider policy is applied before price selection

`ProviderBookPolicy` supports:

- optional explicit inclusion set;
- explicit exclusion set;
- deterministic validation that a provider cannot be both included and excluded.

A filtered provider cannot win an outcome merely because it exposes a higher price. If filtering removes the only quote for an expected outcome, the market becomes incomplete and is rejected.

### 4. Only active and historically available fresh quotes are eligible

Only `QuoteStatus.ACTIVE` quotes can enter a market book.

The effective freshness timestamp is:

1. `source_timestamp`, when the provider supplies one;
2. otherwise `ingested_at`.

At construction time `as_of`:

- `ingested_at` after `as_of` is rejected independently, because that quote was not yet available to the system at the replay/evaluation time;
- an old `source_timestamp` can therefore never mask future ingestion;
- effective timestamps after `as_of` are rejected as future source/effective data;
- quote age greater than the configured freshness window is rejected as stale;
- eligible selected quotes are guaranteed to have been ingested by `as_of` and to lie inside the configured freshness window.

Ingestion-time eligibility and freshness filtering occur before best-price selection and therefore before arbitrage mathematics.

### 4a. The canonical event must still be pre-match

The initial product scope is pre-match detection. At construction time `as_of`, a
market book is emitted only when its canonical event has `EventStatus.SCHEDULED`
and `scheduled_start` is strictly later than `as_of`. A live, postponed, cancelled,
completed or unknown event is ineligible even when its quotes remain active and
fresh. A stale `SCHEDULED` status does not keep a market eligible at or after
kickoff. Ineligible markets emit `EVENT_NOT_PREMATCH` diagnostics and never reach
arbitrage evaluation, including during historical replay.

### 5. Best-price selection is deterministic

For each expected canonical selection, the winning eligible quote is selected by this ordered policy:

1. highest `decimal_price`;
2. if prices tie, newest effective timestamp;
3. if still tied, lexically smallest canonical `ProviderId`;
4. if still tied, lexically smallest `QuoteId`.

Input ordering is never a tie-breaker.

The selected `OddsQuote` itself is retained rather than copying only the price, preserving provider attribution and the complete quote provenance chain.

### 6. Outcome completeness is mandatory

The canonical registry defines the expected selection set for a market.

A market book is emitted only when:

- the canonical market has at least two expected outcomes; and
- every expected canonical selection has at least one eligible quote after identity, provider, status and freshness filtering.

Incomplete markets emit diagnostics and do not reach `evaluate_market()`.

The book's outcome set must equal the expected canonical selection set exactly.

### 7. Construction diagnostics and freshness metadata are first-class output

`CanonicalMarketBook` contains:

- canonical event;
- canonical market;
- expected canonical selection IDs;
- one `BestPriceOutcome` per expected selection;
- `MarketBookFreshness` with construction time, configured freshness window, oldest selected quote and newest selected quote;
- construction diagnostics associated with that market.

The batch builder also returns all diagnostics, including rejected quotes and incomplete markets. Future ingestion is distinguished from future source/effective timestamps so replay failures remain explainable.

This makes every candidate arbitrage traceable to an explicit best-price comparison book.

### 8. Arbitrage mathematics consumes books, not raw provider quote pools

The vertical slice now constructs market books first and calls:

```text
evaluate_market(book.quotes, book.expected_selection_ids, ...)
```

The mathematical core therefore receives exactly one already-selected active quote per expected canonical outcome.

The legacy vertical-slice `BookIssue` output remains as a compatibility surface, but market-book diagnostics are the richer Phase-9 source of construction evidence. Canonical markets with fewer than two outcomes are mapped to the legacy `EVALUATION_REJECTED` issue so pre-Phase-9 consumers continue to receive a skip reason.

### 9. Execution realism remains out of scope

Phase 9 chooses the best displayed eligible price. It does not yet model:

- stake limits;
- stake increments;
- account-specific restrictions;
- fees/commissions;
- currency conversion;
- partial fills;
- execution latency;
- price movement during placement;
- bookmaker rejection risk.

Those concerns belong to the later opportunity/execution-realism phase and must not be silently folded into market alignment.

## Rationale

The safest system boundary is to make semantic alignment and quote eligibility explicit before arithmetic. `evaluate_market()` should answer a narrow deterministic question about one complete canonical market, not also decide whether provider data is stale, whether one bookmaker is allowed, or whether two market variants are equivalent.

Exact canonical market IDs make incompatible variants impossible to combine accidentally. Applying ingestion availability, freshness, status and provider policy before price shopping prevents an attractive but ineligible quote from influencing the book. Keeping the original selected `OddsQuote` preserves full provenance for later auditing and opportunity lifecycle work.

The deterministic tie-break rule guarantees reproducible results independent of provider response order, ingestion ordering or Python container ordering.

## Consequences

### Positive

- every arbitrage evaluation is backed by a traceable `CanonicalMarketBook`;
- stale, future-ingested, future-timestamped, inactive and provider-filtered quotes cannot influence best price;
- historical replay cannot use quotes that were not yet ingested at `as_of`;
- incomplete markets fail closed before arbitrage math;
- incompatible canonical market variants cannot cross-fill outcomes;
- provider attribution and raw quote provenance are preserved;
- price selection is deterministic and reproducible;
- the arbitrage core remains pure and provider-policy agnostic;
- the same builder can later consume persisted/replayed normalized quotes.

### Negative / trade-offs

- conservative completeness rules intentionally discard partial market data;
- exact canonical market identity means normalization/modeling must explicitly support every market variant that should be compared;
- choosing freshness as the first price tie-break favors newer equivalent prices but does not imply guaranteed executability;
- the builder currently evaluates a snapshot at one `as_of`; continuous incremental books are deferred to Phase 10;
- execution constraints are not represented yet.

## Alternatives considered

### Let the arbitrage engine choose best quotes

Rejected because it mixes provider/freshness policy into numerical logic and makes mathematical tests less isolated.

### Group by market kind and line dynamically

Rejected as the primary identity mechanism. It duplicates canonical domain semantics and risks omitting other settlement-bearing dimensions such as period or future market parameters.

### Choose the first quote on equal price

Rejected because provider/input ordering is not a stable semantic property and would make output non-deterministic across ingestion runs.

### Choose only by highest price and ignore freshness until later

Rejected because a stale high price could manufacture an apparent arbitrage before being noticed downstream. Freshness is an eligibility condition, not a presentation filter.

### Trust source timestamps without checking ingestion time

Rejected for replay. A historical source timestamp does not prove the quote was available to ArbiScan at the historical `as_of`; persisted quotes must independently satisfy `ingested_at <= as_of`.

### Emit partial books and let arbitrage math reject them

Rejected because Phase 9 owns outcome completeness. Downstream components should not need to rediscover whether the comparison book is structurally complete.

## Revisit triggers

Revisit this ADR when:

- Phase 10 introduces continuous/incremental quote books and freshness expiry;
- a new canonical market model requires explicit equivalence across multiple canonical IDs;
- exchanges/commissions require price normalization before comparison;
- Phase 12 introduces stake/execution constraints that alter the meaning of “best executable price”;
- persistence/replay requires versioned market-book policies;
- measured production behavior supports changing the deterministic tie-break or freshness policy.
