# ADR-0021 — Motorsport identity and fail-closed settlement gate

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Motorsport/F1 does not fit the ordinary two-team event model.

A race can contain a full driver grid, qualifying/session markets have distinct scope,
podium bets are subject-specific binary propositions, and head-to-head markets compare
only a subset of event participants. Winner and H2H settlement can also depend on
bookmaker-specific DNS, DNF, disqualification, classification, dead-heat, and void
rules.

The two current transports do not expose enough equivalent public machine-readable
F1 market identity to prove safe cross-transport normalization today:

- The Odds API supports outrights generally, but documented outright event schemas may
  omit the normal home/away participant fields used by ArbiScan's current event parser.
- OddsPapi advertises Motorsports coverage and exposes sports/markets through runtime
  catalogue endpoints, but its public documentation does not publish one fixed F1
  sport identifier plus stable winner/podium/H2H market IDs that ArbiScan can bind to
  without observing and verifying the live catalogue.

## Decision

Phase 17.10 defines canonical motorsport semantics without enabling executable F1
markets.

Canonical scope is explicit:

- race: `MarketPeriod.RACE`;
- qualifying: `MarketPeriod.QUALIFYING`;
- other named sessions: `MarketPeriod.SESSION`;
- season/championship: `MarketPeriod.TOURNAMENT`.

Market families are represented as:

- race/qualifying/session winner: `OUTRIGHT_WINNER`;
- subject-specific top-three proposition: `PODIUM_FINISH` with
  `subject_participant_id`;
- pairwise comparison: `HEAD_TO_HEAD`.

Registry completeness is strict:

- a race-winner market must contain one participant selection for every canonical
  event participant;
- podium requires exactly YES and NO for one explicit event participant;
- H2H requires exactly two distinct participant selections from the event.

All three motorsport families remain runtime-disabled. Generic reciprocal-odds and
stake allocation may not consume them until source identity and bookmaker settlement
states are modeled and proven equivalent.

## Consequences

### Positive

- driver-grid winner, podium, and H2H identities cannot collapse into one generic
  winner label;
- race, qualifying, session, and championship scope cannot silently compare;
- incomplete outright grids fail before market-book construction;
- subject-specific podium identity is explicit;
- current providers fail closed rather than fabricating binary motorsport events.

### Negative / trade-offs

- no F1 arbitrage is emitted by Phase 17.10;
- live provider catalogue validation is still required before any concrete F1 market
  mapping can be activated;
- DNS/DNF/disqualification/dead-heat payout algebra is deferred.

## Revisit triggers

Revisit when both enabled transports expose a verified equivalent F1 market family,
when sanitized catalogue fixtures can be retained legally, or when ArbiScan adds
explicit void/dead-heat settlement-aware evaluation.
