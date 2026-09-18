# Exchange-backed outcome semantics

Phase 17.12 introduces exchange-aware payout mathematics without changing ordinary
bookmaker `OddsQuote` semantics.

## Why exchange prices are separate

A decimal number alone is insufficient exchange identity.

The same selection and decimal price can mean:

- BACK: profit if the selection wins;
- LAY: liability if the selection wins and profit if it loses.

The side is therefore structural market data.

## Exchange price observation

`ExchangePriceObservation` records:

- explicit exchange price origin;
- independent transport source;
- canonical event/market/selection identity;
- BACK or LAY side;
- price;
- currently available matched stake;
- commission rate;
- commission scope;
- active/suspended status;
- verified settlement-rule compatibility.

Missing execution terms remain representable for auditing but fail the support gate.

## Lay liability

For lay stake `L` at decimal odds `o`:

```text
liability = L * (o - 1)
```

The lay stake is the amount won if the laid outcome does not win. Liability is the
amount lost if it does win.

## Liquidity

`available_stake` is a hard upper bound for the Phase 17.12 deterministic matched
stake. An `ExchangeStake` larger than the visible amount is rejected.

This does not claim future execution. Exchange liquidity can disappear before an
order is submitted and larger orders can be partially unmatched.

## Commission

Commission is not deducted per winning exchange leg.

Exchange legs sharing one exchange-provider/commission-scope are first netted for a
terminal market outcome. Commission is then charged only when that group has positive
net winnings.

This is necessary for portfolios such as two opposite lays, where one lay wins while
the other loses in every scenario.

## Back/lay example

With:

- bookmaker BACK selection A: EUR 100 at 3.20;
- exchange LAY selection A: EUR 110 at 2.80;
- exchange commission: 2% of positive net exchange-market winnings;

the terminal P&L is:

```text
A wins:
  bookmaker +220
  exchange    -198 liability
  net          +22

A loses:
  bookmaker -100
  exchange   +110 gross
  commission  -2.20
  net          +7.80
```

The guaranteed modeled profit is EUR 7.80, subject to the assumed matched liquidity
and verified settlement rules.

## Lay/lay example

Two opposite EUR 100 lays at 1.90 in the same binary exchange market produce, before
commission:

```text
winning lay side: +100
losing lay side:   -90
market net:        +10
```

At 2% commission on net market winnings, each terminal scenario nets EUR 9.80.

## Runtime boundary

Phase 17.12 provides deterministic settlement evaluation, not live exchange
integration or bet placement.

Current aggregator Betfair-labelled prices remain bookmaker-style source observations
because the feeds do not expose an exchange side/liquidity/commission contract.

See ADR-0023.
