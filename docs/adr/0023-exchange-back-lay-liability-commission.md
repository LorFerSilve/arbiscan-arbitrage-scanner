# ADR-0023 — Exchange back/lay identity, liability, liquidity, and commission

- Status: Accepted
- Date: 2026-09-18
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

Exchange prices are not ordinary bookmaker prices.

A BACK order has the familiar fixed-odds payout shape. A LAY order takes the opposite
side: the user wins the lay stake if the selection does not win and loses liability
equal to `stake * (odds - 1)` if the laid selection wins.

Exchange execution also has semantics that ordinary `OddsQuote` does not represent:

- BACK versus LAY side;
- available matched liquidity at the quoted price;
- lay liability rather than ordinary stake exposure;
- exchange price-origin versus transport-source provenance;
- account/market-specific commission;
- commission charged on positive net market winnings rather than independently on
  each profitable leg;
- settlement-rule equivalence.

Flattening an exchange lay price into a bookmaker decimal quote would allow the
ordinary reciprocal-odds engine to calculate the wrong payout matrix.

## Decision

Phase 17.12 introduces a separate provider-independent exchange model instead of
adding ambiguous optional exchange fields to `OddsQuote`.

`ExchangePriceObservation` carries:

- exchange `Provider`, which must use `ProviderKind.EXCHANGE`;
- transport provider ID;
- canonical event, market, and selection IDs;
- decimal price;
- explicit `ExchangeSide.BACK` or `ExchangeSide.LAY`;
- available stake/liquidity;
- commission rate;
- opaque commission scope identifying the exchange account/market fee bucket;
- explicit settlement-rule verification state;
- quote status.

Incomplete source observations may be retained, but
`assess_exchange_price_support()` keeps them ineligible when side, liquidity,
commission, commission scope, active status, or settlement verification is missing.

`ExchangeStake` represents an amount that is assumed matched at the quoted price.
It cannot exceed visible available liquidity.

For a lay stake `L` at decimal odds `o`:

```text
liability = L * (o - 1)
```

The portfolio evaluator calculates one P&L scenario for every canonical terminal
selection.

For an exchange BACK leg of stake `B` at odds `o`:

```text
selection wins:  +B * (o - 1)
selection loses: -B
```

For an exchange LAY leg of stake `L`:

```text
laid selection wins:  -L * (o - 1)
laid selection loses: +L
```

Exchange legs are grouped by exchange provider and commission scope. Commission is
applied only to positive net gross winnings of that exchange market/scope:

```text
commission = max(net_exchange_market_profit, 0) * commission_rate
```

This prevents overcharging commission independently on one winning leg while another
leg in the same exchange market loses.

A portfolio is exchange arbitrage only when every canonical terminal scenario has
strictly positive net profit after commission.

## Provider boundary

Current The Odds API and OddsPapi adapters expose Betfair-labelled observations as
ordinary bookmaker-origin prices. They do not currently expose exchange BACK/LAY
side, liquidity, commission context, or matched-order semantics.

Those observations therefore remain `ProviderKind.BOOKMAKER` and cannot enter the
Phase 17.12 exchange path merely because the bookmaker slug contains `betfair`.

No live exchange adapter is enabled by Phase 17.12.

## Consequences

### Positive

- lay odds cannot enter reciprocal bookmaker math accidentally;
- liability is explicit;
- liquidity is an execution constraint rather than decorative metadata;
- commission is modeled at the correct market/account aggregation boundary;
- exchange price origin remains separate from the transport used to observe it;
- bookmaker/exchange and lay/lay hedges can be evaluated by a deterministic scenario
  matrix.

### Negative / trade-offs

- the exchange path is separate from the existing `Opportunity`/`StakePlan`
  materialization;
- no automatic exchange stake optimizer is added in Phase 17.12;
- account-specific fee tiers must be supplied explicitly;
- partial/unmatched orders remain outside guaranteed execution claims.

## Revisit triggers

Revisit when a real authorized exchange transport exposes explicit BACK/LAY ladders,
available size, stable selection identity, and fee context, or when Phase 18 replay
requires historical exchange order-book reconstruction.
