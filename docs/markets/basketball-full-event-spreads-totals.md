# Basketball full-event spreads and totals

Phase 17.9 adds a deliberately narrow basketball market subset.

## Canonical identity

Basketball is represented as `Sport.BASKETBALL`.

Enabled advanced market identities are:

- `TOTAL_POINTS / FULL_EVENT / line=x.5`;
- `HANDICAP / FULL_EVENT / line=x.5`.

For spreads, `Market.line` is the signed handicap of ordered participant 1 and the
second participant selection must carry the exact negation. Totals require exactly one
OVER and one UNDER selection.

## Provider mappings

### The Odds API

The featured `spreads` and `totals` keys are distinct from documented quarter and
half keys such as `spreads_q1`, `totals_q1`, `spreads_h1`, and `totals_h1`.
The transport describes those as each bookmaker's featured game markets, but it does
not expose a machine-readable overtime-settlement flag. Consequently
`TheOddsApiConfig.basketball_full_event_bookmakers` defaults to empty and the adapter
drops featured basketball `spreads`/`totals` from unverified price origins. A
bookmaker is opted in only after its own rules prove full-game/overtime equivalence.

The Phase 17.9 deterministic corpus opts in Pinnacle and bet365. Pinnacle's basketball
rules state that Game-period bets include overtime; bet365's basketball rules state
that pre-game bets include overtime unless otherwise stated. Period-specific
point-bearing keys still fail closed rather than being relabelled.

References:

- https://www.pinnacle.com/en/future/betting-rules
- https://help.bet365.com/s/en/sportsrules/basketball

### OddsPapi

Basketball is sportId 11. Phase 17.9 accepts only the exact catalog families:

- `Over Under (incl. overtime)`;
- `Handicap (incl. overtime)`.

Other basketball total/handicap families, including quarter and half variants, are
not promoted to full-event identity.

## Settlement gate

Basketball scores are integer-valued. A half-point total or spread cannot tie the
line, so the ordinary two-outcome reciprocal-odds model is sufficient for that subset.

Integer lines can PUSH. Quarter lines may require split settlement. Both remain
fail-closed until the payout/stake engine models those states explicitly.

## Cross-transport overlap

The Phase 17.9 integration regression supplies equal-time/equal-price Pinnacle
observations through both transports. ADR-0012 consolidates those observations into
one executable bookmaker price while retaining the selected transport provenance.
Independent Bet365 and Betfair quotes remain distinct price origins.

## Deferred

- regulation-only basketball spreads/totals;
- quarter/half markets;
- alternate-line ladders as a separate market-selection policy;
- live/in-play basketball;
- integer and quarter-line settlement-aware staking.
