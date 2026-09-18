# Phase 17.6 completion — tennis set-winner and indexed-set semantics

Date: 2026-09-18

## Scope

Phase 17.6 enables pre-match tennis Set 1 and Set 2 winner markets with structured
canonical set identity.

The phase deliberately narrows provider scope where exact semantics cannot be
demonstrated. OddsPapi supplies validated indexed set-winner mappings; The Odds API
does not receive a guessed set-winner mapping.

## Canonical model

The existing canonical foundation already contains:

- `MarketKind.SET_WINNER`;
- `MarketPeriod.SET`;
- mandatory positive `period_index` for indexed periods.

Phase 17.6 adds registry completeness rules requiring every set-winner market to have
exactly two participant selections covering the event participants, with no selection
handicaps.

The runtime support gate enables only tennis Set 1 and Set 2.

## OddsPapi adapter

The adapter now recognizes the exact documented market identities:

- ID 123, First Set Winner, `p1` -> `period_index=1`;
- ID 125, Second Set Winner, `p2` -> `period_index=2`.

Both require `marketType=winner`, handicap zero, and exact outcome labels `1` and
`2`.

The adapter emits structured `SourceMarket.period_index`.

A malformed catalog record that pairs Second Set Winner with `p1` is ignored and
cannot be promoted to Set 2.

## The Odds API feasibility result

No Phase 17.6 adapter mapping was added for The Odds API.

At the time of the Phase 17.6 implementation, the provider material reviewed did not
establish an exact machine-readable indexed set-winner key, so the phase correctly
remained fail-closed rather than manufacturing equivalence from labels.

**Post-completion note (Phase 17.7 revalidation):** the current official The Odds API
market list now documents tennis `h2h_s1` and `h2h_s2` set moneylines. This does
not change the Phase 17.6 code or evidence; it creates a new, explicit follow-up
dependency. Phase 17.8 will implement and validate those keys against the existing
OddsPapi canonical Set 1 / Set 2 semantics.

## End-to-end regression

The deterministic OddsPapi fixture uses the existing canonical Sinner vs Alcaraz
event and two price providers, Pinnacle and Betfair.

It proves:

1. Set 1 and Set 2 source markets receive different structured period indexes;
2. both normalize to separate canonical market IDs;
3. the same provider outcome labels `1` and `2` do not permit cross-set mixing;
4. eight quotes are normalized across two sets, two bookmakers, and two selections;
5. `build_market_books` creates exactly two books;
6. Set 1 best Alcaraz price is **Betfair 2.10**;
7. Set 1 best Sinner price is **Pinnacle 2.05**;
8. Set 1 is a theoretical two-way arbitrage;
9. an Opportunity and conservative EUR StakePlan can be materialized;
10. Set 2 remains a non-arbitrage book;
11. explicitly mapping a Set 1 source market to canonical Set 2 fails with
    `MARKET_PARAMETER_MISMATCH` before quote construction.

## Settlement limitation

For a normally completed set, the ordinary two-outcome arithmetic is valid.

Retirement, walkover, abandonment, and incomplete-set rules can differ across
bookmakers and are not yet represented in the current quote/execution model.
Provider settlement vocabulary also includes non-win/loss states such as CANCELLED
and UNDECIDED.

Phase 17.6 therefore proves theoretical completed-set arbitrage semantics, not a
bookmaker-rule-independent guarantee of realized profit in exceptional tennis
settlement states.

## Code-bearing quality evidence

The code-bearing head
`d2a7fea3186d3b2617813119c1e259e525bfb011` passed:

- Ruff formatting: pass (`224 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`147 source files`);
- pytest: pass (`309 passed`);
- `pip-audit`: no known vulnerabilities.

The final documentation head must preserve the same quality/security gates.

## Handoff

**Phase 17.6 is technically complete.**

The next dependency is **Phase 17.7 — tennis game-market identity and score-state semantics**.

Before any game-level tennis market is enabled, Phase 17.7 must determine:

- whether a canonical game market needs both set index and game index;
- whether service/receiver identity is part of market identity;
- how provider APIs encode current versus numbered game markets;
- whether pre-match game markets exist with stable machine identity;
- how tiebreak games are distinguished from ordinary games;
- retirement/abandonment settlement behavior;
- whether both available transports expose enough structured context to avoid
  score-state or label-derived guessing.

If stable game identity cannot be demonstrated, Phase 17.7 must remain fail-closed
rather than infer score state from labels.
