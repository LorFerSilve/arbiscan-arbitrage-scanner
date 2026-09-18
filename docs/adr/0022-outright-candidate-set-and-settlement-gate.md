# ADR-0022 — Outright candidate-set completeness and settlement-safety gate

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Tournament, championship, season and other futures markets are multi-participant
outrights rather than ordinary two-team fixtures.

The generic arbitrage formula already supports an arbitrary number of outcomes, but
that mathematical property is only useful when the quoted outcomes form one exact,
mutually-exclusive and exhaustive settlement partition. Outright feeds introduce
additional semantic risks:

- one provider can publish only the leading candidates while another publishes the
  whole field;
- candidate lists can change after qualification, withdrawal or replacement;
- a synthetic `Field` / `Other` outcome is not equivalent to a named participant;
- ties and dead heats can split payouts;
- withdrawal and void rules can differ by bookmaker;
- provider event schemas can omit the binary home/away identity assumed by match
  adapters.

The Odds API explicitly marks outright sports with `has_outrights` and documents an
outright schema that can omit normal team/home fields. OddsPapi exposes market
catalogue records dynamically through `/v4/markets`; no broader outright family is
therefore enabled from a guessed label or fixed ID.

## Decision

Canonical `OUTRIGHT_WINNER` completeness is generalized to race, qualifying,
session and tournament scopes.

For every canonical outright-winner market:

- the event must contain at least two candidates;
- every candidate must use the same `ParticipantKind`;
- the market must contain exactly one participant selection for every event candidate;
- the participant selection set must equal the event candidate set exactly;
- outright selections may not carry handicaps.

A `Field` / `Other` bucket cannot be silently represented as another named
participant. A provider candidate set that is partial or dynamically changing cannot
be promoted to the canonical complete market.

Phase 17.11 also defines a provider-independent `OutrightEvaluationProfile`. The
existing generic N-outcome reciprocal-odds/stake engine is semantically sufficient
only when all of these are proven:

- candidate set complete;
- candidate set static for the evaluated snapshot;
- outcomes mutually exclusive;
- outcomes exhaustive;
- no Field/Other bucket;
- ties impossible under the market contract;
- dead-heat split settlement impossible;
- withdrawal settlement rules equivalent across compared price origins;
- void rules equivalent across compared price origins.

The profile proves only mathematical payout-shape eligibility. It does not itself
enable a provider market.

Broader outright runtime support remains disabled until a real transport path proves
stable candidate identity plus the settlement profile above. The Odds API preserves
`has_outrights` and rejects outright competitions before the binary event parser.
OddsPapi ignores unverified tournament-winner catalogue families.

## Consequences

### Positive

- incomplete leaderboards cannot masquerade as complete outright books;
- team, individual, driver and constructor fields cannot be mixed accidentally;
- Field/Other and named-candidate prices cannot be compared as if they had identical
  outcome identity;
- generic N-outcome math is explicitly reusable once its settlement assumptions are
  actually satisfied;
- provider-specific outright schemas remain isolated from the canonical model.

### Negative / trade-offs

- Phase 17.11 enables no new executable outright market;
- candidate withdrawals and field changes require explicit state/equivalence evidence;
- some apparently attractive futures arbitrage will remain unavailable until
  bookmaker rule semantics are captured.

## Revisit triggers

Revisit when both enabled transports expose the same outright with stable participant
identifiers and complete candidate sets, or when settlement-aware dead-heat/withdrawal
payout algebra is implemented.
