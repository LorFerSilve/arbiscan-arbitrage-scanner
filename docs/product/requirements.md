# ArbiScan Product Requirements

## 1. Purpose

ArbiScan is a provider-independent sports-odds aggregation and arbitrage-detection platform. Its initial purpose is to ingest authorized odds feeds from multiple providers, normalize semantically equivalent events and markets, detect mathematically valid arbitrage opportunities, calculate deterministic stake allocations, and expose those opportunities to downstream consumers.

The initial product is a **scanner and decision-support system**, not an automated wagering system.

## 2. Product goals

ArbiScan MUST:

1. retrieve odds from multiple independent providers through authorized integrations;
2. preserve provider provenance for every ingested quote;
3. map provider-specific events into canonical events;
4. map provider-specific markets and selections into canonical market semantics;
5. compare only outcomes that belong to the same canonical event and market;
6. detect arbitrage only when the implied-probability sum is strictly below `1` after validation;
7. calculate deterministic stake distributions and guaranteed gross return for a configurable total stake;
8. reject stale, suspended, malformed, incomplete, ambiguous, or semantically incompatible data;
9. expose sufficient metadata to explain why an opportunity was produced;
10. remain extensible to additional sports, markets, and providers without introducing provider-specific logic into the core domain model.

## 3. MVP scope

### 3.1 Sports

The MVP SHALL support these sports in order:

1. **Football**
2. **Tennis**

Additional sports, including motorsport/F1, basketball, combat sports, and others, are explicitly deferred until the canonical model and matching pipeline are proven.

### 3.2 Markets

The MVP SHALL support:

- football: **pre-match 1X2 match winner**;
- tennis: **pre-match two-way match winner**.

The MVP SHALL NOT treat the following as equivalent to the above markets:

- draw-no-bet;
- double chance;
- qualification/winner-to-advance markets;
- regulation-time markets when the provider market settles on overtime/extra time or vice versa;
- set/game/period winner markets;
- handicaps/spreads;
- totals;
- outrights/futures.

Those markets require explicit later modeling.

### 3.3 Temporal scope

The MVP SHALL start with **pre-match** odds. Live/in-play detection is deferred because it imposes substantially stricter latency, synchronization, suspension-state, and race-condition requirements.

## 4. Functional workflow

A valid end-to-end ArbiScan workflow is:

1. provider adapter retrieves provider data;
2. ingestion layer validates transport and payload integrity;
3. provider event is mapped to a canonical event;
4. provider market is normalized to a canonical market;
5. selections are normalized to canonical outcomes;
6. quotes are assigned source and ingestion timestamps;
7. freshness, status, completeness, and semantic-equivalence checks run;
8. the best eligible price for each required outcome is selected;
9. implied probabilities are calculated;
10. an opportunity is emitted only when all invariants pass and the total implied probability is `< 1`;
11. a deterministic stake plan and expected gross/net return are calculated;
12. the opportunity retains enough provenance to reproduce the calculation later.

## 5. Core invariants

The following invariants are mandatory and apply across the system.

### 5.1 Odds invariants

- Decimal odds used for positive-return selections MUST be finite numbers greater than `1.0`.
- Zero, negative, `NaN`, infinity, null, malformed, or otherwise invalid odds MUST be rejected.
- Internal calculations MUST avoid binary-floating-point behavior where it can affect money/probability decisions; the numeric strategy is to be formalized in a later ADR.

### 5.2 Market invariants

An arbitrage calculation MAY combine quotes only when outcomes are:

- from the same canonical sporting event;
- from the same canonical market definition;
- mutually exclusive;
- collectively exhaustive for that market;
- governed by equivalent settlement semantics.

A market with missing required outcomes MUST NOT generate an opportunity.

### 5.3 Event invariants

- Quotes from different event instances MUST never be combined.
- Event identity MUST not rely on participant names alone.
- Competition, participants, scheduled start time, sport-specific structure, and provider references MUST be available to matching logic as appropriate.
- Ambiguous event matches MUST fail closed.

### 5.4 Quote provenance invariants

Every eligible odds quote MUST retain at least:

- provider identity;
- provider event reference;
- provider market reference where available;
- canonical event identity;
- canonical market identity;
- normalized selection identity;
- decimal price;
- provider/source timestamp when supplied;
- ingestion timestamp;
- market/selection status;
- raw-source traceability or a stable reference to the raw input when feasible.

### 5.5 Freshness invariants

- Freshness is a correctness property, not merely a performance metric.
- Every quote MUST be evaluated against a configurable freshness policy.
- Quotes outside the accepted age/skew window MUST be excluded.
- An opportunity MUST NOT combine data whose temporal relationship cannot be validated sufficiently for the configured policy.
- Provider clocks and local ingestion clocks MUST be treated as potentially different until clock-skew handling is defined.

### 5.6 Status invariants

Suspended, closed, settled, cancelled, unavailable, or otherwise non-bettable markets/selections MUST NOT produce actionable opportunities.

Unknown status semantics MUST fail closed until explicitly mapped.

### 5.7 Reproducibility invariants

Given the same validated normalized input, configuration, and numeric policy, arbitrage detection and stake allocation MUST produce the same output.

The system MUST preserve the inputs necessary to explain and reproduce an emitted opportunity.

## 6. Arbitrage definition

For a canonical market with mutually exclusive and collectively exhaustive outcomes and best decimal odds `o_i`, define:

`S = sum(1 / o_i)`

A theoretical arbitrage exists only when:

`S < 1`

For total stake `T`, the idealized stake for outcome `i` is:

`stake_i = T * (1 / o_i) / S`

The corresponding idealized gross payout is:

`payout = T / S`

and idealized gross profit is:

`profit = T * (1 / S - 1)`

These formulas are necessary but not sufficient for an actionable opportunity. Later phases MUST additionally account for stake increments, minimum/maximum stakes, provider limits, rounding, fees/commission where applicable, currency, price movement, and execution risk.

## 7. Provider integration requirements

Before a real provider can be integrated, its adapter MUST have a completed integration review covering:

- official/authorized API or data-access mechanism;
- authentication model;
- documented geographic restrictions;
- licensing or subscription requirements;
- rate limits and retry expectations;
- permitted caching/storage duration;
- redistribution/display restrictions;
- permitted commercial use;
- real-time versus delayed nature of the feed;
- relevant market-status semantics;
- timestamp semantics;
- settlement-rule documentation;
- provider-specific terms that affect implementation.

No provider shall be integrated on the assumption that publicly visible website data may automatically be scraped, stored, or redistributed.

## 8. Security and privacy requirements

- Credentials MUST NOT be committed to source control.
- Secrets MUST be supplied through runtime configuration or an appropriate secrets mechanism.
- Logs MUST NOT expose API keys, authorization headers, session tokens, or other credentials.
- Provider payloads MUST be treated as untrusted external input.
- Parsing and normalization MUST validate types, ranges, required fields, and enumerated values.
- Network integrations MUST use secure transport supported by the provider.
- Dependencies and CI workflows MUST be subject to supply-chain controls defined in Phase 1.

The MVP does not require user accounts or personal betting-account credentials.

## 9. Reliability requirements

ArbiScan MUST distinguish at minimum between:

- provider unavailable;
- provider response invalid;
- rate limited;
- authentication failed;
- event unmatched;
- event match ambiguous;
- market unsupported;
- market incomplete;
- quote stale;
- market suspended/closed;
- opportunity rejected due to validation;
- valid opportunity emitted.

Failures from one provider SHOULD be isolated so that other providers can continue operating.

## 10. Observability requirements

The architecture MUST make it possible to measure later:

- provider request success/error rates;
- request and ingestion latency;
- last successful provider update;
- stale-quote counts;
- normalization failures;
- unsupported-market counts;
- event-match success/ambiguous/failure rates;
- arbitrage evaluation counts;
- opportunities emitted/rejected;
- end-to-end detection latency.

## 11. Explainability requirements

Every surfaced opportunity MUST eventually be able to answer:

- which canonical event and market generated it;
- which provider supplied each selected price;
- when each price was sourced/ingested;
- which odds were used;
- what implied-probability sum was calculated;
- what stake plan was calculated;
- which validation/freshness policy version was applied.

## 12. Extensibility requirements

Adding a provider SHOULD require implementing a provider adapter and mappings, not modifying core arbitrage mathematics.

Adding a new market type SHOULD require an explicit canonical market definition and settlement semantics before detection support is enabled.

Adding a sport SHOULD not weaken event-identity guarantees for already supported sports.

## 13. Acceptance criteria for Phase 0

Phase 0 is complete when:

- the product is unambiguously defined as scanner-only for the initial scope;
- football 1X2 and tennis match-winner are the explicit MVP markets;
- pre-match is the explicit initial temporal scope;
- core correctness/freshness/provenance invariants are documented;
- provider-integration constraints are documented;
- non-goals, glossary, risk register, and ADR process exist and do not contradict this document.
