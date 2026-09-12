# ArbiScan Risk Register

This register tracks risks that can cause incorrect arbitrage signals, security incidents, provider-policy violations, unreliable operation, or misleading product behavior.

Risk ratings are intentionally qualitative in Phase 0. Probability and impact can be quantified once operational data exists.

## Rating model

- **Probability:** Low / Medium / High
- **Impact:** Low / Medium / High / Critical
- **Status:** Open / Mitigating / Accepted / Closed

A risk with high correctness or security impact must not be dismissed merely because its probability is initially unknown.

## Risk register

| ID | Risk | Probability | Impact | Primary mitigation | Status |
|---|---|---:|---:|---|---|
| R-001 | Stale odds create false arbitrage | High | Critical | Freshness policy, source/ingestion timestamps, fail-closed expiry | Open |
| R-002 | Different events are incorrectly matched | Medium | Critical | Canonical event identity, multi-signal matching, ambiguity rejection | Open |
| R-003 | Markets with different settlement semantics are treated as equivalent | Medium | Critical | Explicit canonical market schemas and settlement semantics | Open |
| R-004 | Missing outcomes create a false incomplete arbitrage calculation | Medium | Critical | Completeness invariant; require full canonical outcome set | Open |
| R-005 | Suspended/closed selections remain eligible | Medium | High | Explicit status mapping and fail-closed unknown statuses | Open |
| R-006 | Odds move between provider observation and user action | High | High | Low-latency pipeline, timestamps, conservative expiry, do not claim execution guarantee | Open |
| R-007 | Provider rate limits reduce freshness or coverage | High | High | Rate-aware adapters, backoff, quotas, provider health metrics | Open |
| R-008 | Provider outage creates partial/inconsistent market state | Medium | High | Provider isolation, health state, completeness checks | Open |
| R-009 | Provider payload/schema changes break normalization | Medium | High | Contract tests, strict validation, schema/version monitoring | Open |
| R-010 | Provider timestamp semantics or clock skew are misunderstood | Medium | High | Document timestamp semantics per provider, track ingestion time, skew policy | Open |
| R-011 | Floating-point/rounding errors create false positive profitability | Medium | High | Explicit numeric policy, deterministic decimal arithmetic, boundary tests | Open |
| R-012 | Stake increments/minimums/maximums erase theoretical profit | High | High | Separate theoretical from actionable arbitrage; constraint-aware stake planning | Open |
| R-013 | Fees/commission/currency conversion erase profitability | Medium | High | Explicit cost model before labeling opportunities actionable | Open |
| R-014 | Provider-specific business rules leak into core domain | Medium | Medium | Adapter boundaries and provider-neutral canonical schemas | Open |
| R-015 | API credential is committed or logged | Low-Medium | Critical | Secret scanning, push protection, runtime secrets, log redaction | Mitigating |
| R-016 | Third-party dependency or GitHub Action is compromised | Low-Medium | High | Dependency review, lockfile, Dependabot, pinned trusted Actions | Open |
| R-017 | Unauthorized data access/storage/redistribution violates provider terms | Medium | Critical | Integration checklist and terms/licensing review before enabling provider | Open |
| R-018 | Geographic or jurisdictional restrictions are ignored | Medium | High | Deployment/provider compliance review; no circumvention | Open |
| R-019 | Raw provider data is retained longer than permitted | Medium | High | Provider-specific retention policy and storage controls | Open |
| R-020 | User interprets theoretical arbitrage as guaranteed realized profit | High | High | Product terminology, explainability, explicit execution-risk distinction | Open |
| R-021 | Duplicate provider events produce duplicate/noisy opportunities | Medium | Medium | Canonical IDs, deduplication, deterministic matching | Open |
| R-022 | Participant naming/transliteration causes false matches | Medium | High | Alias normalization plus independent event signals; no name-only identity | Open |
| R-023 | Competition naming differences cause cross-competition matching | Medium | High | Canonical competition mapping and confidence rules | Open |
| R-024 | Rescheduled events are matched to obsolete event instances | Medium | High | Start-time/version tracking and event lifecycle handling | Open |
| R-025 | Voided/postponed/cancelled event semantics are inconsistent across providers | Medium | High | Explicit lifecycle/status mapping and settlement semantics | Open |
| R-026 | Same provider is accidentally counted as independent prices under aliases | Low-Medium | Medium | Stable canonical provider identity | Open |
| R-027 | Unbounded ingestion or payload size causes resource exhaustion | Low-Medium | High | Timeouts, size limits, bounded queues, backpressure | Open |
| R-028 | Malformed/untrusted provider input causes parser failure or injection into logs/UI | Medium | High | Strict validation, output encoding, structured logging | Open |
| R-029 | Retry logic amplifies provider failure or triggers throttling | Medium | Medium | Bounded exponential backoff, jitter, retry budgets | Open |
| R-030 | Observability contains sensitive credentials/payload fields | Low-Medium | High | Structured redaction and explicit logging policy | Open |
| R-031 | Architecture is over-engineered before workload is known | Medium | Medium | Modular monolith first; measure before distributing | Open |
| R-032 | Architecture is too tightly coupled to scale or add providers | Medium | High | Clear interfaces, provider isolation, contract tests | Open |
| R-033 | Live/in-play support is added before latency/synchronization safety exists | Medium | Critical | Live markets remain explicit non-goal until dedicated phase | Open |
| R-034 | Automated betting scope creeps into MVP without threat/legal review | Medium | Critical | Scanner-only ADR and roadmap gate | Open |
| R-035 | Arbitrage math is correct but based on semantically invalid inputs | Medium | Critical | Validation and normalization gates precede math | Open |
| R-036 | Opportunity cannot be reproduced after detection | Medium | High | Preserve normalized inputs, provenance, configuration/version references | Open |

## Critical risk themes

### 1. Semantic correctness

The dominant correctness risk is not the arbitrage formula itself; it is comparing prices that do not represent the same event, market, or settlement rules. Event matching and market normalization therefore precede broad provider coverage.

### 2. Temporal correctness

Odds are ephemeral. A price may be mathematically attractive but operationally useless if it is old, suspended, or paired with quotes observed at materially different times. Freshness validation is therefore mandatory.

### 3. Execution gap

ArbiScan can prove only what follows from the data and modeled constraints available to it. The gap between detection and actual wager acceptance remains an explicit product risk. The system must distinguish theoretical and actionable profitability.

### 4. Provider/compliance constraints

Every real provider integration can impose different rules for access, storage, caching, redistribution, commercial usage, and geography. These constraints belong in provider onboarding and cannot be generalized away.

### 5. Supply-chain and secret risk

The public nature of the repository increases the impact of accidental credential disclosure. Repository controls, least-privilege CI, dependency hygiene, and secret redaction are required before real credentials are introduced.

## Risk acceptance rule

A risk may be marked **Accepted** only when:

1. the residual risk is understood;
2. the decision is documented;
3. accepting it does not violate a core correctness/security invariant;
4. a responsible architecture or product decision explicitly permits it.

Critical correctness risks that could produce false arbitrage signals should generally be mitigated or fail closed rather than accepted silently.

## Review cadence

The risk register MUST be reviewed when:

- a new provider is integrated;
- a new sport or market type is added;
- live/in-play support is proposed;
- persistence/retention behavior changes;
- automated execution is proposed;
- a security or correctness incident occurs;
- a major architecture boundary changes.
