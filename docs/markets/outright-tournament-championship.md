# Tournament and championship outright winner semantics

Phase 17.11 generalizes multi-participant outright identity beyond motorsport while
keeping runtime evaluation fail-closed until provider and settlement equivalence are
proven.

## Canonical identity

An outright winner uses:

- `MarketKind.OUTRIGHT_WINNER`;
- `MarketPeriod.TOURNAMENT` for tournament, season or championship winner scope;
- one canonical event whose participants are the candidate field;
- one `SelectionKind.PARTICIPANT` selection per candidate.

Race, qualifying and session outrights retain their Phase 17.10 period identities.

## Candidate-set completeness

The canonical registry requires the outcome set to equal the event participant set
exactly.

A valid market therefore has:

- at least two candidates;
- one homogeneous participant kind;
- no missing candidate;
- no extra candidate;
- no non-participant outcome;
- no selection handicap.

A provider's visible price list is not automatically a complete candidate set. A
leaderboard containing only favourites, or a changing list after withdrawals, is
insufficient evidence.

## Participant-type boundary

Teams, individuals, drivers, constructors and provider-specific other competitor
types are distinct canonical participant kinds.

A single outright cannot combine different kinds. A constructor championship and a
driver championship must therefore remain separate canonical events/markets even when
a provider presents them near each other.

A literal `Field` or `Other` betting bucket is a synthetic set complement, not an
ordinary competitor. Phase 17.11 does not manufacture a fake participant to make
such a market appear complete.

## Generic N-outcome math

ArbiScan's reciprocal-odds engine already accepts arbitrary N-outcome books.

That engine is semantically sufficient for an outright only when
`assess_generic_outright_math()` receives evidence that the market is:

- complete and static;
- mutually exclusive and exhaustive;
- free of Field/Other buckets;
- free of tie/dead-heat split settlement;
- aligned on withdrawal rules;
- aligned on void rules.

If any condition is false, the market needs richer settlement algebra or remains
unsupported.

This distinction matters because mathematical completeness and provider settlement
equivalence are separate questions.

## Provider feasibility

### The Odds API

The provider exposes `has_outrights` in sport metadata and documents the
`outrights` market. Its outright event schema differs from ordinary fixtures and can
omit normal team/home identity.

Phase 17.11 therefore preserves `has_outrights` and rejects any such competition
before the existing binary event parser. A future adapter path must build explicit
multi-participant source identity and prove the complete field.

### OddsPapi

OddsPapi exposes markets through the runtime `/v4/markets` catalogue. Phase 17.11
does not infer a canonical tournament winner from a generic market label or guessed
market ID.

A deterministic synthetic `Tournament Winner` catalogue fixture remains ignored
until stable source identity, candidate completeness and settlement semantics are
proven.

## Runtime status

Broader tournament/championship outright markets remain runtime-disabled.

This is intentional: Phase 17.11 establishes the semantic contract and the exact
conditions under which the existing generic math can later be reused without
misstating incomplete or split-settlement markets as guaranteed arbitrage.

See ADR-0022.
