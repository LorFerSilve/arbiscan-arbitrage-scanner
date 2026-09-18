# Motorsport/F1 winner, podium, and head-to-head semantics

Phase 17.10 establishes canonical identity but intentionally enables no executable
motorsport market.

## Participant identity

Formula-style race events may contain many drivers. Drivers use
`ParticipantKind.DRIVER`; constructors remain a separate
`ParticipantKind.CONSTRUCTOR` identity and must not be substituted for a driver.

A race event used for a driver market should contain the canonical driver grid relevant
to that event. Constructor championship markets belong to a separately modeled
participant set rather than reusing driver IDs.

## Scope identity

The following periods are distinct:

- `RACE` — one race;
- `QUALIFYING` — qualifying result;
- `SESSION` — another explicitly named session;
- `TOURNAMENT` — championship/season scope.

A race-winner price is never equivalent to qualifying winner or championship winner
because the participant set and settlement event differ.

## Winner completeness

Race winner uses `MarketKind.OUTRIGHT_WINNER` with `MarketPeriod.RACE`.

The canonical registry requires one participant selection for every event participant.
A bookmaker response that omits one driver, adds an unmodeled "field/other" outcome,
or cannot prove complete grid identity is not a complete canonical winner market.

This is stronger than simply accepting every visible outright price.

## Podium completeness

`MarketKind.PODIUM_FINISH` is a subject-specific proposition.

The market carries one `subject_participant_id` and exactly two selections:

- YES — the subject finishes on the podium under the provider's settlement rule;
- NO — the subject does not.

Multiple driver podium prices are not mutually exclusive with each other and therefore
must never be assembled into one multi-driver reciprocal-probability market.

## Head-to-head completeness

`MarketKind.HEAD_TO_HEAD` contains exactly two distinct participant selections from
the event. It does not imply a handicap and must not infer pair identity from display
order alone.

## Settlement boundary

Phase 17.10 does not model the following provider/bookmaker-specific states:

- driver does not start;
- one or both drivers fail to finish;
- post-race disqualification or reclassification;
- void/refund outcomes;
- dead-heat or split-payout rules;
- shortened/rerouted sessions;
- mutable live/session-relative markets.

Because those states can alter payout, all winner, podium, and H2H motorsport families
remain `UNSUPPORTED` for generic arbitrage/stake evaluation.

## Provider feasibility

### The Odds API

The transport's sport-group mapping can represent `Motor Sports`, but ArbiScan's
current event parser expects binary home/away participants. The provider documents
outright/futures schemas separately and historical outright documentation explicitly
notes missing normal team/home fields.

Phase 17.10 therefore rejects motorsport event promotion before binary event parsing.
No F1 winner/podium/H2H source market is mapped yet.

References:

- https://the-odds-api.com/liveapi/guides/v4/
- https://the-odds-api.com/sports-odds-data/betting-markets.html
- https://the-odds-api.com/releases/outrights.html

### OddsPapi

OddsPapi publicly advertises Motorsports among covered sports and exposes canonical
sport and market catalogues through `GET /v4/sports` and `GET /v4/markets`.

Its public documentation does not publish a fixed F1 sport ID/slug and stable
winner/podium/H2H market IDs as normative constants. Phase 17.10 therefore does not
guess them. A synthetic unverified motorsport record remains unmapped in provider
tests until an exact live catalogue record is captured, reviewed, and legally safe to
retain.

References:

- https://oddspapi.io/en
- https://oddspapi.io/en/docs/get-sports
- https://oddspapi.io/en/docs/get-markets

## Enablement requirements

A future motorsport family may enter runtime support only after:

1. exact provider event and market identity is verified;
2. participant/subject completeness is machine-checkable;
3. both transports are equivalent for the compared market;
4. DNS/DNF/disqualification/dead-heat and void behavior is represented;
5. sanitized deterministic fixtures cover positive and negative settlement cases.
