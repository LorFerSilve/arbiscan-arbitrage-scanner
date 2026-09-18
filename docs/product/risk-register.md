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
| R-037 | The same bookmaker price origin is observed through multiple transports and counted twice or overwritten ambiguously | Medium | Critical | ADR-0012 source-observation provenance, price-origin consolidation, conflict fail-closed policy | Closed |
| R-038 | Multiple bookmakers from one aggregator are mistaken for multiple independent data sources | Medium | High | Explicit transport-source definition and Phase 16 independent-source exit criterion | Closed |
| R-039 | Two transport sources report conflicting same-time prices/status for one bookmaker and selection | Medium | High | Preserve both observations; exclude conflicting slot unless an explicit trust policy resolves it | Closed |
| R-040 | A technically integrated second transport is activated in an environment before its provider-specific legal/data-rights review is complete | Low-Medium | Critical | Explicit transport-source enablement policy, primary-only rollback path, provider production blockers, and release/deployment gates | Mitigating |
| R-041 | Advanced markets with different lines, indexed periods, or selection handicaps are mapped to one canonical identity | Medium | Critical | ADR-0013 structured source parameters plus exact fail-closed parameter matching before quote construction | Mitigating |
| R-042 | Football totals with PUSH or split-settlement semantics enter the ordinary two-outcome guaranteed-return calculation | Medium | Critical | ADR-0014 canonical support gate: enable only regulation positive x.5 totals until push/half-win/half-loss payouts are modeled | Closed |
| R-043 | Asian handicap direction is inverted across providers, or PUSH/split-settlement variants enter ordinary two-outcome guaranteed-return math | Medium | Critical | ADR-0015 participant-1 line anchor, exact mirrored selection handicaps, explicit settlement profiles, and half-goal-only generic-engine gate | Closed |
| R-044 | Full-time BTTS is conflated with first-half/other YES-NO propositions or malformed incomplete outcomes | Medium | Critical | ADR-0016 exact provider market identity, regulation-only support gate, and canonical YES/NO completeness | Closed |
| R-045 | Draw No Bet / Asian Handicap 0 reciprocal edge is surfaced as strictly positive guaranteed profit because the shared draw-refund state is omitted | Medium | Critical | ADR-0017 generic-path block, explicit settlement-aware normalization, and refundable two-way evaluation with worst-case return | Closed |

## Critical risk themes

### 1. Semantic correctness

The dominant correctness risk is not the arbitrage formula itself; it is comparing prices that do not represent the same event, market, or settlement rules. Event matching and market normalization therefore precede broad provider coverage.

Phase 17 extends this rule to structured market parameters. Numeric lines, period
indexes, and signed selection handicaps are semantic identity, not presentation
metadata. Parameter mismatches must be rejected before any quote can reach the market
book.

Phase 17.2 also treats settlement shape as semantic correctness. Football totals are currently enabled only on positive regulation-time half-goal lines, where Over/Under is a true two-outcome win/lose partition. Integer and quarter-line totals fail closed before quote construction rather than being evaluated with incomplete PUSH or split-settlement assumptions.

Phase 17.3 applies the same principle to Asian handicap orientation and settlement geometry. The canonical market line is the signed handicap of ordered participant 1, participant 2 must carry its exact negation, and only half-goal lines may reach ordinary arbitrage/staking. Integer and quarter variants are explicitly settleable in the domain model but remain ineligible for generic guaranteed-return claims.

Phase 17.4 treats BTTS period identity as equally strict. A YES/NO shape is not sufficient: only provider-specific full-match BTTS identity may resolve to canonical regulation-time BTTS, and the canonical graph must contain exactly one YES and one NO selection.

Phase 17.5 separates a positive decisive-state Draw No Bet price edge from strict guaranteed profit. Football regulation handicap zero can enter only the explicit settlement-aware path; its shared draw PUSH returns stake, fixing worst-case profit at zero even when both decisive outcomes are profitable.

### 2. Temporal correctness

Odds are ephemeral. A price may be mathematically attractive but operationally useless if it is old, suspended, or paired with quotes observed at materially different times. Freshness validation is therefore mandatory.

### 3. Execution gap

ArbiScan can prove only what follows from the data and modeled constraints available to it. The gap between detection and actual wager acceptance remains an explicit product risk. The system must distinguish theoretical and actionable profitability.

### 4. Provider/compliance constraints

Every real provider integration can impose different rules for access, storage, caching, redistribution, commercial usage, and geography. These constraints belong in provider onboarding and cannot be generalized away.

### 5. Multi-source provenance and overlap

Phase 16 adds a second dimension to provider correctness: ArbiScan must distinguish the transport/data vendor from the bookmaker or exchange that originates a price. Multiple feeds may report the same bookmaker. Those observations must remain independently auditable but must never be counted as separate executable price origins. Equal-time conflicts must fail closed rather than resolving through incidental arrival order.

Phase 16.8 adds an explicit transport-source enablement gate before polling. This makes a second source opt-in at the application boundary and gives operators a deterministic rollback to the primary-only source set. That technical gate does not replace provider-specific legal, licensing, retention, display, or geographic approval.

### 6. Supply-chain and secret risk

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
