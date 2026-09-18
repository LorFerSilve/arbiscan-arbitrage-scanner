# ADR-0018 — Make tennis set index structural and narrow support to demonstrated provider mappings

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Set-winner prices look like ordinary two-way tennis markets, but market identity
depends on **which set** settles the wager.

If Set 1 and Set 2 are represented only by similar labels or the same two participant
outcomes, quotes from different sets could be combined into a false arbitrage.

The canonical model already supports `MarketPeriod.SET` with a mandatory positive
`period_index`, and Phase 17.1 requires structured advanced-market parameters.
Phase 17.6 must decide how provider set identity reaches that field and what to do
when transports expose different capabilities.

Provider feasibility is asymmetric:

- OddsPapi exposes exact documented First Set Winner and Second Set Winner market
  identities with structured provider periods;
- current The Odds API tennis documentation does not establish an exact indexed
  set-winner key that ArbiScan can map without guessing.

Tennis also has exceptional retirement/walkover/incomplete-set settlement behavior
that can differ by bookmaker.

## Decision

### Canonical identity

Tennis set winner uses:

- `MarketKind.SET_WINNER`;
- `MarketPeriod.SET`;
- mandatory `period_index`;
- exactly two participant selections covering the event participants;
- no line or selection handicap.

Phase 17.6 enables indexes 1 and 2 only.

### Source identity must be structured

Set index is never derived by parsing human-readable market labels.

For OddsPapi, Phase 17.6 requires the demonstrated structured identities:

- market 123 + First Set Winner + `period=p1` -> index 1;
- market 125 + Second Set Winner + `period=p2` -> index 2.

The adapter emits `SourceMarket.period_index`; strict normalization requires exact
equality with the canonical market index.

### Provider-narrowed support

No The Odds API set-winner mapping is added until an exact documented machine-readable
tennis set-winner market identity is available.

Lack of support from one transport is preferable to manufacturing semantic
equivalence.

### Arbitrage math

For a normally completed set, set winner is an exhaustive two-participant win/lose
market and may use the existing generic two-way arbitrage and stake-allocation path.

### Exceptional tennis settlement

Phase 17.6 does not model bookmaker-specific retirement, walkover, abandonment, or
incomplete-set rules.

Consequently, a generated set-winner Opportunity proves the theoretical completed-set
price relationship under current canonical assumptions. It is not independent
evidence that all bookmakers will settle every exceptional match state identically.

## Rationale

Using `period_index` as canonical identity directly prevents cross-set price mixing.

Requiring provider machine identity rather than label parsing follows ADR-0013 and
makes parser drift fail closed.

Provider-narrowed support preserves correctness when API capabilities are asymmetric.

The ordinary arbitrage engine need not be changed for the normal completed-set payout
shape, while execution realism remains free to add bookmaker settlement rules later.

## Consequences

### Positive

- Set 1 and Set 2 can never share one canonical market identity;
- strict parameter mismatch blocks accidental cross-set mappings before quotes exist;
- provider labels are not promoted to canonical parameters;
- no unsupported The Odds API market key is invented;
- existing provider-independent two-way mathematics can be reused for completed sets;
- later set indexes can be added without changing the canonical model.

### Negative / trade-offs

- Phase 17.6 has only one demonstrated transport for set-winner data;
- set 3+ remains unavailable until exact mappings are validated;
- retirement/walkover settlement remains an execution-realism limitation;
- OddsPapi's technical support still cannot bypass its production-rights blocker.

## Alternatives considered

### Parse "First Set" / "Second Set" from labels

Rejected. Human labels are presentation data, not canonical parameter identity.

### Treat all set-winner prices as one market

Rejected. It can create false cross-set arbitrage.

### Guess a The Odds API market key

Rejected. Provider capability must be demonstrated, not inferred.

### Block set winner until two transports support it

Rejected. Phase 17's semantic work can safely enable one provider family while
documenting the narrower source coverage, because arbitrage can still compare
multiple bookmaker price origins within that transport.

### Model every retirement rule now

Rejected. Those rules are bookmaker/execution semantics, not required to establish
indexed canonical market identity. They remain an explicit operational risk.

## Phase 17.7 provider revalidation note

During Phase 17.7, the current official The Odds API market list was found to
document tennis `h2h_s1` and `h2h_s2` set moneylines.

This satisfies one of this ADR's revisit triggers: provider evidence has changed.
The Phase 17.6 implementation and its original fail-closed decision remain valid for
their time and code state, but the transport is no longer considered semantically
infeasible for Set 1 / Set 2 winner.

Phase 17.8 will perform the required adapter, fixture, parameter, and cross-transport
validation before The Odds API is marked supported for this family. Until that work
lands, the runtime remains provider-narrowed exactly as implemented in Phase 17.6.

## Revisit triggers

Revisit this decision when:

- The Odds API or another transport documents exact indexed tennis set-winner keys;
- OddsPapi exposes validated set 3+ mappings;
- bookmaker-specific tennis retirement/void rules enter the execution-realism model;
- live/in-play set markets become a roadmap dependency.
