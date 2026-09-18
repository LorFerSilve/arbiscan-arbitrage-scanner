# Phase 17.12 completion — Exchange back/lay and commission-aware semantics

**Status:** Technically complete on 2026-09-18 as a settlement/mathematics and
provider-boundary foundation. No live exchange transport is enabled.

## Delivered

- explicit `ExchangeSide.BACK` versus `ExchangeSide.LAY`;
- dedicated `ExchangePriceObservation` separate from ordinary `OddsQuote`;
- strict `ProviderKind.EXCHANGE` price-origin requirement;
- independent transport-provider provenance;
- explicit visible matched liquidity;
- lay liability algebra;
- explicit commission rate and commission-scope/account-market provenance;
- fail-closed support diagnostics for missing side, liquidity, commission, scope,
  active status, or settlement verification;
- `ExchangeStake` liquidity enforcement;
- deterministic terminal-scenario evaluator for bookmaker BACK plus exchange
  BACK/LAY portfolios;
- commission applied to positive net exchange-market winnings per provider/scope;
- back/lay arbitrage regression;
- opposing lay/lay arbitrage regression;
- conflicting commission-rate rejection;
- regression proving aggregator Betfair-labelled prices remain ordinary bookmaker
  origins and do not gain exchange semantics by name;
- ADR-0023 and dedicated exchange-market documentation.

## Provider conclusion

Neither currently enabled transport exposes enough exchange-order semantics to create
`ExchangePriceObservation` safely from live data. Existing Betfair-labelled
aggregator prices lack explicit BACK/LAY side, matched liquidity, commission scope,
and account fee context.

Phase 17.12 therefore adds no live exchange mapping and makes no provider-name
inference.

## Next dependency

Phase 17 expansion is now semantically complete through 17.12.

The next roadmap dependency is **Phase 18 — historical analysis, replay, and
backtesting**.
