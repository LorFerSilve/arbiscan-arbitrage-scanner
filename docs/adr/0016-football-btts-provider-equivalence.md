# ADR-0016 — Define football BTTS by provider-specific full-time identity and exact YES/NO completeness

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Both-teams-to-score appears superficially simple because it has only two outcomes.
The primary correctness risk is therefore not payout algebra but semantic
equivalence.

Different provider APIs can expose:

- full-match BTTS;
- first-half BTTS;
- other period variants;
- player or team scoring propositions;
- generic YES/NO markets with unrelated meaning.

The Odds API exposes an exact soccer market key `btts` and separately identifies
period-specific variants such as `btts_h1`. OddsPapi exposes a structured
`Both Teams To Score` catalog record with `period=fulltime`,
`marketType=totals`, `handicap=0`, and outcomes Yes/No.

ArbiScan must not infer equivalence from the words "Both Teams To Score" or from a
generic YES/NO shape alone.

## Decision

### Canonical market

Add `MarketKind.BOTH_TEAMS_TO_SCORE`.

A supported canonical BTTS market is:

- football;
- regulation time;
- non-parameterized;
- exactly one YES and one NO selection.

### The Odds API source identity

Only the exact configured market key `btts` is considered the Phase 17.4 full-match
BTTS mapping.

The adapter requires:

- exactly one Yes and one No;
- no numeric point parameter.

Period-specific variants such as `btts_h1` are not aliases of regulation BTTS.

### OddsPapi source identity

Only catalog records satisfying all of the following are eligible:

- `marketName=Both Teams To Score`;
- football;
- non-player;
- `period=fulltime`;
- `marketType=totals`;
- `handicap=0`;
- exact Yes/No outcomes.

A record with the same name but another period is ignored fail-closed.

### Arbitrage math

BTTS uses the existing ordinary two-way arbitrage and stake-allocation model. No
provider-specific calculation or special settlement algebra is added.

## Rationale

BTTS has a simple payout shape but a high risk of period or proposition conflation.
Using provider-specific machine-readable identity at the adapter/normalization
boundary is safer than collapsing human labels.

Exact YES/NO completeness guarantees that missing or malformed outcomes cannot create
a false two-way book.

Because a valid regulation BTTS market has exactly one winning terminal outcome and
no push/split settlement, the existing generic evaluator and stake allocator already
represent it correctly.

## Consequences

### Positive

- full-time BTTS is explicitly distinct from first-half variants;
- source labels alone cannot establish canonical identity;
- both real transport schemas can contribute to one canonical market;
- no new arithmetic path is required;
- existing multi-source provenance and bookmaker-deduplication rules remain intact.

### Negative / trade-offs

- provider variants not covered by exact machine-readable mappings remain unavailable;
- The Odds API BTTS remains opt-in rather than part of the default request;
- future BTTS period variants require their own canonical period mapping and tests.

## Alternatives considered

### Infer BTTS from YES/NO labels

Rejected. Many unrelated markets use YES/NO outcomes.

### Map every provider market named "Both Teams To Score" to regulation time

Rejected. The same semantic family may exist for first half or other periods.

### Add provider-specific BTTS arithmetic

Rejected. The settlement shape is already represented by the existing two-way
canonical mathematics.

## Revisit triggers

Revisit this decision when:

- additional provider APIs use materially different machine-readable BTTS identity;
- regulation-time settlement differs across a supported provider;
- first-half or other period BTTS becomes a roadmap dependency;
- source schemas expose explicit settlement-scope fields that should be promoted to a
  more general provider-neutral period identity.
