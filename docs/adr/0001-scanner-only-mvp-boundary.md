# ADR-0001 — Scanner-only MVP boundary

- Status: Accepted
- Date: 2026-09-13
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

ArbiScan originates from a desire to identify cross-provider sports-betting arbitrage opportunities. The product could theoretically range from a passive analytics tool to a fully automated execution system.

These alternatives have materially different correctness, security, legal, operational, and account-management requirements. Automated wagering would introduce bookmaker-account credentials, transaction execution, race conditions between legs, balance management, stronger geographic/compliance concerns, and significantly greater financial impact from defects.

The project also requires a narrow initial domain in order to prove event matching, market normalization, quote freshness, and arbitrage mathematics before broadening coverage.

## Decision

ArbiScan's initial product is a **scanner and decision-support platform only**.

It will:

- ingest authorized odds data from multiple providers;
- normalize equivalent sporting events and betting markets;
- detect mathematically valid arbitrage opportunities;
- calculate deterministic stake plans;
- surface opportunities and their provenance to downstream consumers.

It will **not place wagers automatically** in the initial product scope.

The initial supported market scope is:

1. football — pre-match 1X2 match winner;
2. tennis — pre-match two-way match winner.

Additional sports and market types require explicit canonical modeling before support is enabled.

## Rationale

This boundary isolates the core engineering problem that must be solved correctly regardless of eventual execution features:

- provider abstraction;
- canonical event identity;
- semantic market equivalence;
- temporal freshness;
- deterministic arbitrage mathematics;
- auditable provenance.

A scanner-first architecture reduces unnecessary exposure to user credentials and direct financial transactions while allowing the project to validate the quality of its detection engine.

Narrow MVP market coverage also reduces semantic ambiguity and permits strong tests around complete outcome sets:

- football 1X2 has exactly three canonical outcomes;
- tennis match winner has exactly two canonical participant outcomes.

## Consequences

### Positive

- Core correctness can be developed independently of wagering execution.
- No bookmaker account credentials are required by the MVP.
- No transactional orchestration across multiple providers is required.
- False-positive detection can be measured and improved before financial execution is considered.
- Architecture remains provider-neutral.
- MVP tests can focus on well-defined complete outcome sets.

### Negative / trade-offs

- ArbiScan cannot guarantee that a surfaced opportunity remains available when a user acts on it.
- The product cannot guarantee stake acceptance or realized profit.
- Some commercial value associated with automated execution is intentionally deferred.
- A future execution layer may require additional domain abstractions not needed by the scanner.

## Alternatives considered

### Fully automated betting from the start

Rejected for the MVP. It couples detection correctness with credentials, balances, transaction ordering, account-specific limits, provider rejection, execution latency, and higher legal/security risk before the data model has been validated.

### Support every sport and market immediately

Rejected. Market names that look similar may have different settlement semantics. Broad coverage before canonical modeling would substantially increase false-positive risk.

### Football-only MVP

Not selected as the final boundary because tennis two-way match winner provides a useful second market shape for validating that the architecture is not accidentally hard-coded to three-outcome markets. Football remains the first implementation target.

## Revisit triggers

This ADR should be reconsidered only if one of the following occurs:

- the scanner reaches demonstrated reliability and a separate automated-execution product is proposed;
- there is a clear authorized API path for execution and a dedicated threat/legal/reliability design is completed;
- the MVP market scope proves technically inappropriate based on provider availability or semantic constraints.

Any move to automated wagering requires a new ADR and must not be introduced as an incidental feature.
