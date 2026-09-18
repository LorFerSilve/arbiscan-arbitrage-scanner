# ArbiScan Development Roadmap

ArbiScan is a multi-bookmaker sports-odds aggregation and arbitrage-detection platform. The project must evolve incrementally from a well-defined domain model and secure development foundation into a reliable, observable, low-latency system that can ingest heterogeneous odds feeds, normalize markets, match equivalent events, detect arbitrage opportunities, and surface actionable results.

This roadmap is intentionally architecture-first. Application code should only be introduced after the relevant requirements, invariants, interfaces, and validation criteria have been defined.

---

## Guiding principles

1. **Correctness over breadth.** A smaller set of sports and markets with mathematically and semantically correct results is preferable to broad but unreliable coverage.
2. **Provider isolation.** Bookmaker/provider-specific logic must remain behind adapters and must not leak into the core domain model.
3. **Canonical internal representation.** Events, participants, markets, selections, odds, timestamps, and provenance must use a provider-independent representation.
4. **Freshness is part of correctness.** An arbitrage opportunity built from stale or unsynchronized prices must be treated as invalid.
5. **Deterministic math.** Arbitrage detection and stake allocation must be pure, testable, reproducible functions.
6. **No secrets in source control.** Credentials are loaded from secure runtime configuration only.
7. **Fail closed where ambiguity exists.** Ambiguous event matching, incomplete markets, malformed odds, or uncertain market semantics must not produce actionable arbitrage signals.
8. **Observability from the start.** Ingestion failures, stale feeds, normalization errors, matching confidence, detection latency, and dropped opportunities must be measurable.
9. **Respect provider terms and jurisdictional constraints.** Integrations must use authorized APIs/data sources and comply with applicable terms, rate limits, licensing requirements, and local law.
10. **No automated bet placement in the initial product scope.** ArbiScan initially detects and reports opportunities; wagering automation is explicitly out of scope until separately designed, reviewed, and justified.

---

# Phase 0 — Product definition, scope, and invariants

## Objective

Define exactly what ArbiScan is, what it is not, and which assumptions every later phase may rely on.

## Deliverables

- `docs/product/requirements.md`
- `docs/product/non-goals.md`
- `docs/product/glossary.md`
- `docs/product/risk-register.md`
- initial Architecture Decision Record structure under `docs/adr/`

## Tasks

### 0.1 Functional scope

Define the first supported workflow:

1. retrieve odds from multiple providers;
2. identify equivalent sporting events;
3. normalize equivalent betting markets;
4. compare best available prices per outcome;
5. calculate implied probability sum;
6. identify true arbitrage when the sum is `< 1`;
7. calculate stake distribution and guaranteed return;
8. reject stale, incomplete, ambiguous, suspended, or invalid data;
9. expose opportunities to downstream consumers.

### 0.2 Initial market scope

Define an explicit MVP subset instead of attempting every sport and market immediately.

Recommended initial order:

- football — 1X2 match winner;
- tennis — two-way match winner;
- selected two-way moneyline markets;
- later: totals, handicaps/spreads, set markets, outrights, motorsport/F1 markets, and multi-outcome markets.

### 0.3 Core invariants

Document invariants such as:

- decimal odds must be greater than `1.0` for valid positive-return selections;
- one arbitrage calculation may only combine mutually exclusive and collectively exhaustive outcomes of the same canonical market;
- selections from different event instances may never be combined;
- each odds quote carries provider identity, source timestamp, ingestion timestamp, and status;
- stale quotes are excluded using configurable freshness thresholds;
- suspended/closed markets are excluded;
- malformed or unknown market semantics fail closed;
- opportunity calculations must be reproducible from stored inputs.

### 0.4 Legal and provider constraints

Create a provider-integration checklist covering:

- official API availability;
- geographic access restrictions;
- API licensing;
- caching/storage restrictions;
- redistribution restrictions;
- rate limits;
- authentication model;
- permitted commercial use;
- whether odds are delayed or real-time.

## Exit criteria

- requirements and non-goals are written and internally consistent;
- MVP sports/markets are explicitly chosen;
- all core invariants are documented;
- no unresolved ambiguity remains about whether ArbiScan is initially a scanner or an automated betting platform.

---

# Phase 1 — Repository bootstrap and engineering standards

## Objective

Create a reproducible and secure Python development environment before domain implementation begins.

## Recommended baseline

- Python 3.13 unless a required dependency forces another supported version;
- `uv` for dependency/environment management;
- `pyproject.toml` as the project configuration source;
- `uv.lock` committed for reproducibility;
- Ruff for linting and formatting;
- Pyright or mypy for static typing;
- pytest for testing;
- pre-commit for local quality gates.

## Deliverables

- `pyproject.toml`
- `uv.lock`
- `.python-version`
- `.editorconfig`
- `.env.example`
- refined `.gitignore`
- `.pre-commit-config.yaml`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `docs/development/setup.md`

## Tasks

### 1.1 Source layout

Adopt a `src/` layout, for example:

```text
src/
└── arbiscan/
    ├── domain/
    ├── providers/
    ├── ingestion/
    ├── normalization/
    ├── matching/
    ├── arbitrage/
    ├── persistence/
    ├── services/
    └── observability/

tests/
├── unit/
├── integration/
├── contract/
└── fixtures/
```

### 1.2 Secrets policy

- `.env` ignored;
- `.env.example` contains names only, never credentials;
- runtime configuration validated on startup;
- no credential fallback values in source;
- document rotation procedure for compromised credentials.

### 1.3 GitHub Actions baseline

Introduce CI for pull requests with initially small, fast gates:

- format check;
- lint;
- type check;
- unit tests;
- dependency/security checks where appropriate.

### 1.4 Supply-chain controls

- pin GitHub Actions to trusted versions and preferably immutable commit SHAs;
- enable Dependabot;
- enable secret scanning/push protection;
- enable CodeQL once substantive Python code exists;
- document third-party dependency acceptance criteria.

## Exit criteria

- a clean checkout can be bootstrapped deterministically;
- local quality commands and CI produce the same result;
- secrets cannot be accidentally committed through the standard workflow;
- `main` accepts changes only through the protected PR workflow.

---

# Phase 2 — Domain model and canonical schemas

## Objective

Define provider-independent entities before writing provider adapters.

## Deliverables

Core types for:

- `Sport`
- `Competition`
- `Participant`
- `Event`
- `Market`
- `Selection`
- `OddsQuote`
- `Provider`
- `ProviderEventReference`
- `ProviderMarketReference`
- `Opportunity`
- `StakePlan`

## Design requirements

### 2.1 Event identity

A canonical event must model at least:

- sport;
- competition;
- participants;
- scheduled start time;
- event status;
- canonical ID;
- provider references.

The model must support non-team events such as tennis and future motorsport/F1 integration.

### 2.2 Market identity

Markets need explicit semantics rather than free-form strings.

Examples:

```text
MATCH_WINNER_2_WAY
MATCH_WINNER_3_WAY
TOTAL_POINTS
HANDICAP
SET_WINNER
OUTRIGHT_WINNER
```

Parameterized markets must retain parameters such as total line or handicap value.

### 2.3 Selection identity

A selection must encode its semantic meaning. Provider strings such as `Home`, `1`, `Team A`, or localized labels must normalize to the same internal selection where appropriate.

### 2.4 Odds quote provenance

Each quote must retain:

- decimal price;
- provider;
- canonical event and market identity;
- source event/market/selection identifiers;
- provider/source timestamp if available;
- ingestion timestamp;
- quote status;
- raw-source reference or trace identifier.

### 2.5 Validation

Invalid states should be difficult to represent. Prefer constrained types/enums/value objects over generic dictionaries and raw strings.

## Testing

- construction validation;
- serialization round trips;
- timestamp/timezone handling;
- decimal precision;
- equality and identity semantics;
- malformed input rejection.

## Exit criteria

- all later subsystems can communicate entirely through canonical types;
- no provider-specific field is required by the arbitrage engine;
- canonical schemas are documented and thoroughly unit-tested.

---

# Phase 3 — Arbitrage mathematics core

## Objective

Build and prove the pure mathematical core independently from APIs, databases, and networking.

## Core formula

For decimal odds `o_1 ... o_n`, define:

```text
S = Σ (1 / o_i)
```

A theoretical arbitrage exists when:

```text
S < 1
```

The gross theoretical return margin is related to:

```text
1 / S
```

For bankroll `B`, the ideal stake on outcome `i` is:

```text
stake_i = B * (1 / o_i) / S
```

which equalizes theoretical payout across all outcomes.

## Deliverables

- arbitrage detector;
- implied probability calculator;
- margin calculator;
- stake allocator;
- payout calculator;
- configurable minimum-profit threshold;
- precision/rounding policy.

## Required edge cases

- exactly `S == 1`;
- floating-point boundary errors;
- invalid odds;
- duplicate selections;
- incomplete markets;
- three-way football markets;
- arbitrary `n`-outcome markets;
- bookmaker minimum stake;
- maximum stake;
- stake increments;
- currency rounding;
- insufficient bankroll;
- post-rounding loss of arbitrage.

## Numerical policy

Use decimal/fixed-precision arithmetic where monetary correctness requires it. Do not base guaranteed-profit claims on uncontrolled binary floating-point rounding.

## Testing

- deterministic examples;
- property-based tests;
- randomized valid/invalid books;
- invariants ensuring equalized payout within configured tolerance;
- tests proving rounded stakes do not silently turn profitable opportunities negative.

## Exit criteria

- arbitrage calculations are pure and provider-independent;
- mathematical properties are covered by tests;
- monetary precision and rounding policy are documented;
- the engine never labels a non-profitable rounded stake plan as guaranteed profit.

---

# Phase 4 — Provider adapter contract

## Objective

Define a strict integration boundary before implementing any bookmaker or odds-provider integration.

## Deliverables

A provider interface supporting capabilities such as:

- provider metadata;
- supported sports;
- competition discovery;
- event discovery;
- odds retrieval;
- optional streaming updates;
- health/status;
- rate-limit metadata;
- canonical conversion hooks.

## Design constraints

- async-first I/O;
- explicit timeouts;
- bounded retries with backoff/jitter;
- cancellation support;
- rate-limit awareness;
- structured errors;
- raw payload validation;
- provider capability declaration;
- no provider-specific exception types outside the adapter boundary.

## Contract tests

Every provider implementation must pass a shared conformance suite.

## Exit criteria

- a mock provider can implement the complete interface;
- provider failure cannot corrupt domain state;
- adding a new provider does not require changes to the arbitrage engine.

---

# Phase 5 — Synthetic provider and end-to-end vertical slice

## Objective

Prove the architecture without relying on unstable external APIs.

## Deliverables

Create one or more deterministic fake providers that emit controlled fixtures for:

- matching events;
- mismatching events;
- stale odds;
- suspended markets;
- profitable arbitrage;
- no-arbitrage cases;
- malformed data;
- partial provider outages.

Build the first vertical pipeline:

```text
synthetic provider
    -> ingestion
    -> normalization
    -> event/market identity
    -> arbitrage detector
    -> opportunity output
```

## Exit criteria

- the complete logical pipeline works without network access;
- deterministic fixtures exercise success and failure paths;
- architecture can be tested in CI without external services.

---

# Phase 6 — First real odds-data integration

## Objective

Integrate one legitimate odds source to validate the provider contract against real-world data.

## Provider selection criteria

Evaluate candidates by:

- legal/API accessibility from Belgium/EU;
- documented authentication;
- sports/market coverage;
- bookmaker coverage;
- update frequency;
- source timestamps;
- rate limits;
- price/licensing;
- historical data availability;
- WebSocket/streaming support;
- stable event and market IDs.

Prefer an odds aggregation API for the first integration if it provides multiple bookmakers consistently; direct bookmaker adapters can follow where authorized and technically useful.

## Deliverables

- provider implementation;
- raw payload fixtures sanitized of secrets;
- schema validation;
- integration tests with recorded/fixture responses;
- provider documentation;
- rate-limit handling;
- telemetry.

## Exit criteria

- live odds can be transformed into canonical domain objects;
- failures and throttling degrade gracefully;
- CI does not require live provider credentials.

---

# Phase 7 — Normalization engine

## Objective

Convert heterogeneous provider terminology and formats into canonical semantics.

## Areas

### 7.1 Sport normalization

Map provider sport identifiers into canonical sports.

### 7.2 Competition normalization

Handle aliases, localization, abbreviations, season identifiers, and competition hierarchy.

### 7.3 Participant normalization

Examples of equivalent naming:

```text
Manchester United
Man United
Manchester Utd
MUN
```

Must not be naively collapsed without context.

### 7.4 Market normalization

Correctly distinguish markets that look similar but are not equivalent, for example:

- regulation-time winner vs including overtime;
- match winner vs qualification winner;
- full-time result vs first-half result;
- total `2.5` vs total `3.5`;
- handicap `-1.0` vs `-1.5`.

### 7.5 Odds format normalization

Internally use decimal odds while supporting provider inputs such as decimal, fractional, American, or implied probability if required.

## Exit criteria

- canonicalization is deterministic;
- unknown semantics are explicitly represented/rejected rather than guessed;
- normalization has broad fixture coverage.

---

# Phase 8 — Cross-provider event matching

## Objective

Reliably determine when provider events refer to the same real-world sporting event.

This is one of the highest-risk parts of the project.

## Matching signals

Potential signals include:

- normalized sport;
- competition;
- participant identities;
- participant ordering/home-away semantics;
- scheduled start time tolerance;
- provider event IDs where cross-references exist;
- event round/stage;
- venue when available.

## Architecture

Use staged matching rather than a single fuzzy-string score:

1. hard compatibility filters;
2. normalized participant resolution;
3. temporal compatibility;
4. competition/stage checks;
5. confidence scoring;
6. ambiguity rejection.

## Safety rules

- false negatives are initially preferable to false positives;
- never create arbitrage from low-confidence event matches;
- retain matching explanation/provenance;
- support manual alias data without hardcoding it into algorithms.

## Testing

Include adversarial fixtures:

- same teams on different dates;
- reserve/youth/women teams;
- repeated tennis matchups;
- swapped participant ordering;
- localized names;
- delayed/rescheduled events;
- same-name clubs in different countries.

## Exit criteria

- confidence thresholds are defined and measured;
- ambiguous events fail closed;
- no arbitrage opportunity can cross unmatched event boundaries.

---

# Phase 9 — Market alignment and best-price book construction

## Objective

Build a canonical comparison book for each event/market from all eligible providers.

## Tasks

- group quotes by canonical event and market;
- verify outcome completeness;
- remove stale/suspended quotes;
- select best valid price per outcome;
- preserve provider attribution;
- prevent invalid combinations from the same incompatible market variant;
- support configurable bookmaker/provider inclusion/exclusion.

## Output

A deterministic structure such as:

```text
CanonicalMarketBook
├── event
├── market
├── outcomes
│   ├── outcome A -> best quote/provider
│   ├── outcome B -> best quote/provider
│   └── outcome C -> best quote/provider
├── freshness metadata
└── construction diagnostics
```

## Exit criteria

- every candidate arbitrage has a traceable best-price book;
- incomplete or semantically incompatible markets are rejected;
- stale-data policy is enforced before arbitrage math runs.

---

# Phase 10 — Real-time ingestion and freshness control

## Objective

Make opportunity detection timely enough to be useful while preventing stale-data false positives.

## Components

- polling scheduler and/or stream consumers;
- bounded concurrency;
- provider-specific rate limiting;
- deduplication;
- quote versioning;
- freshness windows;
- stale quote eviction;
- clock-skew handling;
- ingestion health tracking;
- backpressure strategy.

## Important metrics

- provider request latency;
- provider error rate;
- update interval;
- quote age;
- ingestion-to-detection latency;
- stale quote count;
- throttling/rate-limit events.

## Exit criteria

- quote freshness is measurable end to end;
- stale provider data cannot generate actionable signals;
- ingestion remains stable under partial provider failure.

---

# Phase 11 — Persistence and auditability

## Objective

Persist enough state to reproduce, debug, and analyze detected opportunities without coupling live detection to database availability.

## Recommended persistence layers

Evaluate PostgreSQL for durable structured data and optionally Redis for ephemeral/cache/coordination needs.

## Persistable data

- provider metadata;
- canonical events;
- provider-event mappings;
- canonical markets;
- normalized quotes/history according to retention policy;
- opportunities;
- stake calculations;
- matching decisions/confidence;
- ingestion diagnostics;
- configuration versions where needed for reproducibility.

## Requirements

- migrations;
- indexes for event/time/provider queries;
- idempotent writes where possible;
- retention strategy;
- UTC timestamps;
- audit trail sufficient to explain why an opportunity was emitted.

## Exit criteria

- a previously emitted opportunity can be reconstructed from persisted evidence;
- persistence failure does not silently produce corrupted signals;
- migrations are tested.

---

# Phase 12 — Opportunity lifecycle and execution realism

## Objective

Move beyond theoretical arbitrage and model whether an opportunity is practically actionable.

## Opportunity states

Possible lifecycle:

```text
DETECTED
VALIDATED
ACTIONABLE
STALE
INVALIDATED
EXPIRED
```

## Practical constraints

Model where data is available/configured:

- bookmaker minimum stake;
- maximum stake;
- stake increments;
- account-specific limits as user-provided configuration;
- currency;
- commission/exchange fees;
- taxes where applicable;
- bankroll allocation;
- maximum exposure;
- minimum guaranteed profit;
- minimum ROI;
- odds drift tolerance.

## Revalidation

Before surfacing an opportunity as actionable:

1. verify all quotes are fresh;
2. verify market remains open;
3. recompute with current prices;
4. apply stake rounding/limits;
5. verify guaranteed return remains positive.

## Exit criteria

- theoretical and actionable arbitrage are distinct concepts in the model;
- opportunity output includes both profit and operational assumptions;
- post-rounding and configured constraints cannot be ignored.

---

# Phase 13 — Service/API layer

## Objective

Expose ArbiScan functionality through a stable application interface without coupling clients to internal modules.

## Recommended technology

FastAPI is a strong candidate for the Python service layer, subject to confirmation during architecture review.

## Candidate endpoints

- health/readiness;
- providers/status;
- sports;
- events;
- current odds;
- arbitrage opportunities;
- opportunity detail/provenance;
- configuration/status endpoints;
- metrics via an appropriate observability endpoint.

## Requirements

- typed request/response schemas;
- pagination;
- filtering;
- stable error model;
- authentication before exposing non-local deployments;
- rate limiting if externally reachable;
- OpenAPI documentation;
- no secrets in API responses/logs.

## Exit criteria

- clients require no direct access to persistence internals;
- API contracts are tested;
- security boundaries are documented.

---

# Phase 14 — Observability and operational resilience

## Objective

Make incorrect, stale, or degraded behavior visible before users trust the output.

## Logging

Structured logs with correlation identifiers for:

- provider requests;
- ingestion batches;
- event matching;
- market normalization;
- opportunity creation/invalidation.

## Metrics

At minimum:

- provider availability;
- request/error rate;
- rate-limit utilization;
- canonicalization failures;
- unmatched/ambiguous event counts;
- active quote count;
- stale quote count;
- opportunities detected;
- opportunities invalidated;
- end-to-end detection latency.

## Reliability patterns

- timeouts;
- retries with jitter;
- circuit breakers where justified;
- bulkheads/provider isolation;
- graceful shutdown;
- health/readiness checks;
- bounded queues;
- startup configuration validation.

## Exit criteria

- provider degradation is immediately diagnosable;
- important failure modes have metrics/alerts;
- system health can be distinguished from provider health.

---

# Phase 15 — User-facing dashboard and alerts

## Objective

Provide a useful interface only after the core engine has proven correctness and reliability.

## Dashboard capabilities

- active opportunities;
- sport/competition filters;
- bookmaker/provider filters;
- minimum ROI/profit filters;
- freshness/age display;
- exact odds and providers per leg;
- recommended stake distribution;
- guaranteed payout/profit under stated assumptions;
- opportunity provenance;
- expiration/invalidation state.

## Alerts

Potential channels:

- browser/web notifications;
- email;
- Discord/Telegram/other integrations where appropriate.

Alerts should be deduplicated and should identify when an opportunity has materially changed or expired.

## Exit criteria

- UI never hides quote age or provider attribution;
- displayed calculations exactly match backend calculations;
- stale opportunities disappear or are clearly invalidated.

---

# Phase 16 — Multi-provider expansion

## Objective

Increase coverage without compromising adapter isolation or correctness.

## Status

Technically complete as of 2026-09-18. The Odds API and OddsPapi have passed the
Phase 16 engineering gates for deterministic multi-source participation, including a
tested staged-enable/rollback boundary. This status does not grant production usage
rights: provider-specific legal/licensing/retention/display/geographic blockers remain
independent release prerequisites.

## Process for every new provider

1. provider/legal/API review;
2. capability declaration;
3. adapter implementation;
4. fixture capture/sanitization;
5. contract tests;
6. normalization mappings;
7. event-matching validation;
8. rate-limit tuning;
9. production telemetry validation;
10. staged enablement.

## Quality gate

A provider is not considered supported merely because data can be downloaded. It must pass contract, normalization, freshness, matching, and operational checks.

## Exit criteria

- at least two independent transport/data sources participate safely in arbitrage detection;
- provider outages are isolated;
- adding providers does not increase core-domain coupling.

---

# Phase 17 — Advanced market support

## Objective

Expand beyond simple winner markets after the canonical market model has proven itself.

## Status

In progress. **Phases 17.1 through 17.4 are technically complete.** The next
dependency is **Phase 17.5 — football draw-no-bet settlement semantics**.

### 17.1 — Structured advanced-market parameter foundation

Status: **Complete**.

Before totals, handicaps, or indexed-period markets can enter canonical detection:

- preserve market lines as exact structured `Decimal` values at the source boundary;
- preserve indexed-period identity explicitly;
- preserve signed participant handicaps explicitly;
- reject source/canonical parameter mismatches before quote construction;
- prohibit label parsing from becoming canonical parameter identity;
- add provider parser fixtures proving structured parameter preservation.

ADR-0013 owns this invariant.

### 17.2 — Football totals

Status: **Complete**.

Football pre-match regulation totals are enabled for positive push-free half-goal
(`x.5`) lines. Phase 17.2 proves exact line equivalence, canonical Over/Under
completeness, two-real-transport same-line market-book construction, different-line
non-comparison, and end-to-end arbitrage evaluation. Integer and quarter lines fail
closed under ADR-0014 because the current generic payout model does not represent
PUSH or split settlement.

### 17.3 — Football Asian handicap settlement semantics

Status: **Complete**.

Phase 17.3 anchors `Market.line` to ordered canonical participant 1, requires the
second participant selection to carry the exact negated handicap, and models
half-goal, integer, quarter and unsupported line geometry with WIN, HALF_WIN, PUSH,
HALF_LOSS and LOSS settlement states.

The generic `ArbitrageEvaluation` and `StakePlan` are proven sufficient for
regulation-time half-goal handicaps, which are enabled end to end across both real
adapter schemas. Integer and quarter lines remain fail-closed for generic opportunity
generation because their PUSH/split-settlement payout matrices require a future
scenario-aware guaranteed-return/stake engine.

### 17.4 — Football both-teams-to-score semantics and provider feasibility

Status: **Complete**.

Phase 17.4 adds canonical `BOTH_TEAMS_TO_SCORE` with exact YES/NO completeness and
enables football regulation-time BTTS across both existing real transport schemas.

The Odds API mapping uses the exact documented `btts` event market and rejects
malformed outcome or point semantics. OddsPapi requires the structured full-time
`Both Teams To Score` catalog identity and does not promote first-half records.

The end-to-end regression proves multi-source normalization, overlapping Pinnacle
consolidation, best-price YES/NO construction, theoretical arbitrage detection,
Opportunity creation, and conservative stake allocation without provider-specific
core math.

### 17.5 — Football draw-no-bet settlement semantics

The next dependency is regulation-time football draw-no-bet (DNB).

Before enablement it must establish:

- canonical participant-side outcome completeness;
- exact regulation-time provider identity;
- draw-as-refund/PUSH settlement semantics;
- the payout matrix for both participant selections when the match is drawn;
- whether reciprocal-odds arbitrage remains a sound detection prefilter;
- whether the current `StakePlan` can guarantee profit across win/loss/draw-refund
  terminal states or needs the settlement-aware path anticipated by Phase 17.3;
- provider-specific mappings and schema-faithful fixtures;
- cross-source equivalence and fail-closed period/settlement variants;
- end-to-end regressions that distinguish theoretical price shape from truly
  guaranteed post-settlement return.

Later Phase 17 dependencies should address tennis set/game markets and the remaining
roadmap candidates only after their own semantic specifications exist.

## Candidate markets

- football totals;
- Asian handicap;
- both-teams-to-score;
- draw-no-bet;
- tennis set/game markets;
- basketball spreads/totals;
- motorsport/F1 winner/podium/head-to-head markets;
- outright tournament markets;
- exchange-backed outcomes if supported legally and technically.

Each market family requires its own semantic specification and test matrix before enablement.

## Exit criteria

- each market type has explicit outcome-completeness rules;
- line/parameter equivalence is proven before cross-provider comparison;
- unsupported variants cannot silently enter the generic arbitrage engine.

---

# Phase 18 — Historical analysis, replay, and backtesting

## Objective

Measure how the system would have behaved rather than relying on anecdotal opportunities.

## Capabilities

- replay normalized historical quote streams;
- reproduce opportunity lifecycle;
- analyze duration of opportunities;
- estimate sensitivity to detection latency;
- quantify stale-data false positives;
- compare providers;
- measure matching precision/recall on labeled data;
- analyze theoretical vs actionable opportunities.

## Important caveat

Backtests must avoid claiming realized profitability from price snapshots alone. Execution uncertainty, account limits, rejected bets, latency, odds changes, market suspension, fees, and bookmaker rules must be modeled or explicitly excluded from the conclusion.

## Exit criteria

- detection behavior can be reproduced offline;
- system changes can be evaluated against a fixed historical corpus;
- performance claims distinguish theoretical signal quality from actual betting execution.

---

# Phase 19 — Performance and scalability engineering

## Objective

Optimize only after profiling demonstrates real bottlenecks.

## Areas

- async connection pooling;
- batch processing;
- efficient canonical lookup indexes;
- matching cache;
- incremental market-book updates;
- event-driven recomputation instead of global rescans;
- database query optimization;
- queue throughput;
- horizontal provider workers if required.

## Benchmarks

Define representative workloads for:

- number of providers;
- concurrent events;
- markets per event;
- quote updates per second;
- end-to-end detection latency.

## Exit criteria

- performance targets are measured rather than guessed;
- optimizations preserve deterministic results;
- load tests cover expected production scale plus safety margin.

---

# Phase 20 — Security hardening and threat-model review

## Objective

Perform a dedicated security pass before any serious public deployment.

## Threat areas

- leaked provider credentials;
- malicious/compromised provider payloads;
- dependency compromise;
- CI supply-chain attacks;
- SSRF through configurable provider endpoints;
- log injection/data leakage;
- API abuse;
- denial of service;
- unsafe deserialization;
- database credential exposure;
- overly privileged GitHub Actions tokens;
- compromised deployment secrets.

## Controls

- formal threat model;
- least privilege;
- secret rotation;
- dependency and container scanning;
- CodeQL/static analysis;
- protected environments for deployment;
- hardened network egress/ingress policy;
- audit logging;
- backup/restore testing;
- incident response procedure.

## Exit criteria

- critical threat paths have documented mitigations;
- security CI gates are active;
- no known high/critical unresolved findings remain for release.

---

# Phase 21 — Packaging, deployment, and release engineering

## Objective

Create repeatable deployment and release procedures.

## Candidate deployment model

Containerized services using Docker, with exact deployment target chosen later based on operational requirements and cost.

## Deliverables

- production Dockerfile;
- local Docker Compose stack if useful;
- deployment documentation;
- environment-specific configuration;
- migration procedure;
- rollback strategy;
- release/versioning policy;
- changelog/release notes process;
- health/readiness checks;
- backup strategy.

## CI/CD rules

- PRs build/test only;
- deployment credentials only available to protected deployment environments;
- production deployment requires explicit gated workflow;
- artifacts should be immutable and traceable to a Git commit.

## Exit criteria

- deployment is reproducible;
- rollback is documented and tested;
- releases are traceable to source and CI results.

---

# Phase 22 — Production readiness and v1.0 criteria

ArbiScan should not be considered `v1.0` merely because it finds an arbitrage example.

## Required v1.0 properties

- at least two validated real data sources/bookmakers;
- reliable canonical event matching;
- strict canonical market semantics;
- 2-way and 3-way arbitrage support;
- configurable freshness thresholds;
- realistic stake rounding/constraints;
- deterministic opportunity calculations;
- opportunity provenance/audit trail;
- provider contract tests;
- comprehensive domain/math unit tests;
- integration tests;
- CI quality/security gates;
- observability and provider-health monitoring;
- documented setup/deployment/security model;
- no secrets in repository/history;
- measured end-to-end latency;
- documented limitations and false-positive controls.

## Release gate

A `v1.0` release requires an explicit production-readiness review against the above criteria rather than being tied to a calendar date.

---

# Cross-cutting testing strategy

Testing is not a final phase; every phase adds tests at the appropriate level.

## Unit tests

For:

- domain validation;
- normalization rules;
- market semantics;
- arbitrage math;
- stake allocation;
- matching primitives.

## Property-based tests

Especially valuable for:

- arbitrage formulas;
- odds conversion;
- stake allocation;
- rounding invariants.

## Contract tests

Every provider adapter must pass the same provider contract suite.

## Integration tests

Cover:

- provider fixture -> canonical objects;
- canonical quotes -> market book;
- market book -> opportunity;
- persistence round trips;
- API contracts.

## End-to-end tests

Use deterministic synthetic providers; live external APIs should not be required for normal CI.

## Regression fixtures

Every serious production parsing/matching bug should create a sanitized fixture and regression test before the fix is considered complete.

---

# Cross-cutting documentation strategy

Recommended documentation structure:

```text
docs/
├── product/
│   ├── requirements.md
│   ├── non-goals.md
│   ├── glossary.md
│   └── risk-register.md
├── architecture/
│   ├── overview.md
│   ├── domain-model.md
│   ├── data-flow.md
│   └── deployment.md
├── providers/
├── markets/
├── development/
├── security/
└── adr/
```

Architecture decisions with meaningful long-term consequences should receive an ADR rather than being buried in commits or chat history.

---

# Development workflow

For each roadmap item:

1. select the smallest coherent task;
2. create a feature/docs branch;
3. document the intended behavior and acceptance criteria;
4. implement the change;
5. add or update tests;
6. run local quality gates;
7. open a pull request;
8. let CI validate it;
9. resolve all review conversations;
10. squash-merge into `main`;
11. delete the merged branch;
12. update roadmap/docs when architecture or scope changes.

Avoid combining unrelated roadmap phases into one pull request.

---

# Recommended immediate execution order

The next implementation work should proceed in this exact order unless new information justifies an ADR changing it:

```text
Phase 0  Product definition, scope, invariants
   ↓
Phase 1  Repository bootstrap and engineering standards
   ↓
Phase 2  Canonical domain model
   ↓
Phase 3  Arbitrage mathematics core
   ↓
Phase 4  Provider adapter contract
   ↓
Phase 5  Synthetic end-to-end vertical slice
   ↓
Phase 6  First real odds source
   ↓
Phase 7  Normalization
   ↓
Phase 8  Cross-provider event matching
   ↓
Phase 9  Best-price market books
   ↓
Phase 10 Real-time ingestion/freshness
   ↓
Phase 11 Persistence/auditability
   ↓
Phase 12 Opportunity lifecycle/execution realism
   ↓
Phase 13 API
   ↓
Phase 14 Observability/resilience
   ↓
Phase 15 Dashboard/alerts
   ↓
Phase 16+ Expansion, historical analysis, scaling, hardening, deployment
```

The critical architectural rule is that **provider integrations do not define the domain model**. The canonical domain and arbitrage mathematics must exist first; external data is adapted into them afterward.

---

# Current project status

- Repository created.
- Repository is public.
- `main` is protected by an active ruleset.
- Pull requests are required for changes to the default branch.
- Force pushes and default-branch deletion are blocked.
- Linear history is required.
- Review conversations must be resolved before merge.
- Squash merge is the intended repository merge strategy.
- No application implementation has started.

**Next milestone: Phase 0 — Product definition, scope, and invariants.**
