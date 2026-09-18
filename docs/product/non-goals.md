# ArbiScan Non-Goals

This document prevents scope drift. Items listed here are intentionally excluded from the initial ArbiScan product unless a later roadmap phase and ADR explicitly bring them into scope.

## 1. No automated bet placement

ArbiScan v1 is not a betting bot.

The system will detect and report opportunities, but it will not:

- log into personal bookmaker accounts;
- place bets automatically;
- split stakes across accounts automatically;
- bypass confirmation screens;
- automate deposits or withdrawals;
- attempt to evade provider controls, geographic restrictions, or account limitations.

If wagering automation is ever considered, it requires a separate security, legal, reliability, and execution-risk design.

## 2. No guarantee of realized profit

A mathematically valid arbitrage snapshot does not guarantee that a user can realize the theoretical profit. ArbiScan will not claim guaranteed execution because real-world factors include:

- price movement between observation and action;
- stake limits;
- minimum stake increments;
- market suspension;
- partial availability;
- account-specific pricing or limits;
- provider rejection;
- fees, commission, or currency conversion;
- settlement-rule differences.

The product's responsibility is to correctly identify opportunities under the validated data and constraints available to it.

## 3. No broad market coverage in the MVP

The MVP is intentionally narrow.

Initially supported:

- football pre-match 1X2 match winner;
- tennis pre-match two-way match winner.

Initially excluded:

- live/in-play markets;
- totals/over-under;
- handicaps/spreads;
- double chance;
- draw-no-bet;
- set/game/period markets;
- player props;
- same-game combinations;
- outrights/futures;
- F1/motorsport markets;
- exchange back/lay arbitrage;
- synthetic or derived markets.

These are future extensions, not implicit MVP requirements.

## 4. No unauthorized data acquisition

ArbiScan will not make unauthorized scraping, anti-bot circumvention, credential abuse, CAPTCHA bypass, or terms-of-service evasion part of its architecture.

Provider support requires an authorized data-access path whose usage constraints can be documented.

## 5. No provider-specific core architecture

The core domain and arbitrage engine will not be designed around one bookmaker's payload format, naming conventions, IDs, or market taxonomy.

Provider-specific behavior belongs behind adapters and mappings.

## 6. No fuzzy matching that silently guesses

The system will not maximize match rate at the expense of correctness.

If event identity or market semantics are materially ambiguous, ArbiScan must reject or quarantine the candidate instead of emitting an arbitrage signal.

## 7. No reliance on participant names alone

Participant-name equality is not sufficient event identity. Name normalization may contribute to matching, but the system will not treat identical strings as proof of event equivalence.

## 8. No binary floating-point money model as an implicit default

The project will not silently rely on ordinary floating-point arithmetic for financial decisions where rounding affects outcomes. The exact numeric policy is deferred to a dedicated architecture decision.

## 9. No production-scale distributed architecture before evidence requires it

The MVP will not introduce Kafka, Kubernetes, microservices, distributed consensus, or other infrastructure solely for perceived future scale.

Architecture should remain modular, measurable, and replaceable, but complexity must be justified by observed requirements.

## 10. No machine learning dependency for core correctness

The first correct implementation will not require an ML model to determine arbitrage validity.

Deterministic rules and explicit schemas are preferred for:

- market semantics;
- odds validation;
- arbitrage mathematics;
- freshness filtering.

ML-assisted entity matching may be explored later only if deterministic approaches prove insufficient and confidence/fail-closed behavior can be preserved.

## 11. No user-account platform in the initial backend

The MVP does not require:

- consumer registration;
- identity management;
- bookmaker credential storage;
- payment processing;
- subscriptions/billing;
- social features.

These are separate product concerns and must not distort the initial detection engine.

## 12. No promise of universal bookmaker support

A bookmaker/provider is supported only after its data source, semantics, technical contract, and usage constraints are understood and tested.

The existence of odds on a website does not imply ArbiScan supports that provider.

## 13. No silent semantic coercion

ArbiScan will not convert unsupported markets into 'close enough' canonical markets. Examples that must remain distinct unless explicitly modeled include:

- regulation winner vs winner including extra time;
- match winner vs qualification;
- 1X2 vs draw-no-bet;
- game/set winner vs match winner.

## 14. No hidden correction of bad provider data

Invalid or contradictory provider data may be normalized only through explicit, tested rules. The system will not silently fabricate missing outcomes, timestamps, participants, or statuses.

## 15. No legal/compliance assumptions

The software architecture will not assume that data access, storage, redistribution, commercial use, or gambling-related functionality is universally permitted.

Provider terms and applicable jurisdictional requirements must be reviewed for each real integration and deployment context.


## Phase 17.12 clarification

The initial-product non-goal for exchange back/lay arbitrage remains an execution and
live-integration boundary.

Phase 17.12 adds provider-independent BACK/LAY settlement mathematics, liability,
liquidity and commission semantics so future exchange data cannot be handled
incorrectly. It does **not** add:

- live exchange credentials or account integration;
- exchange order placement;
- automatic hedging;
- unmatched-order management;
- a live exchange provider adapter.

Those remain outside the current scanner execution scope.
