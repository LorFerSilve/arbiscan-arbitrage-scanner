# ArbiScan Glossary

This glossary defines the terminology used throughout ArbiScan. Terms here are normative unless a later ADR explicitly supersedes them.

## Arbitrage
A set of positions across all mutually exclusive and collectively exhaustive outcomes of the same canonical market such that, under the modeled assumptions and constraints, the total implied probability is below `1` and the resulting stake allocation yields a non-negative return for every outcome.

A theoretical arbitrage signal is not the same as guaranteed realized profit.

## Arbitrage margin
For implied-probability sum `S`, the idealized margin is:

`1 / S - 1`

This expresses the theoretical profit relative to total stake before execution frictions, limits, rounding, fees, price movement, or other constraints.

## Canonical event
ArbiScan's provider-independent representation of one real sporting event. Multiple provider event records may map to one canonical event.

## Canonical market
A provider-independent market definition with explicit outcome set and settlement semantics. Quotes may be compared only when mapped to the same canonical market.

## Canonical selection
A provider-independent representation of one outcome within a canonical market, such as `HOME`, `DRAW`, `AWAY`, or one of two named tennis participants.

## Collectively exhaustive
A set of outcomes is collectively exhaustive when one of those outcomes must occur under the market's settlement rules. Arbitrage detection requires the complete required outcome set.

## Decimal odds
Odds represented as total payout per unit stake, inclusive of returned stake. Valid positive-return decimal odds used by ArbiScan are greater than `1.0`.

## Detection latency
The elapsed time between relevant odds becoming available at a source and ArbiScan evaluating or surfacing the corresponding opportunity.

## Downstream consumer
Any component that consumes validated ArbiScan output, such as an API, dashboard, alerting service, persistence layer, or later external integration.

## Event matching
The process of determining whether provider-specific event records refer to the same canonical sporting event.

## Fail closed
A correctness policy under which ambiguous, unsupported, incomplete, malformed, stale, or otherwise uncertain data is rejected rather than interpreted optimistically.

## Freshness
The degree to which an odds quote is recent enough, relative to configured temporal rules, to remain eligible for arbitrage evaluation.

## Freshness threshold
A configurable maximum acceptable quote age or temporal skew. Thresholds may eventually differ by provider, sport, market, and pre-match/live context.

## Guaranteed return
Within the mathematical model, the minimum calculated payout/profit across all outcomes after applying modeled stake allocation and constraints. The term must not be interpreted as a guarantee of real-world execution.

## Implied probability
For positive decimal odds `o`, the raw implied probability is:

`1 / o`

For arbitrage detection, the relevant quantity is the sum of implied probabilities of the best eligible prices for the complete canonical outcome set.

## Ingestion
The process of retrieving or receiving provider data, validating transport/payload characteristics, timestamping it, and passing it into the normalization pipeline.

## Ingestion timestamp
The timestamp assigned by ArbiScan when data is received or accepted into the ingestion pipeline.

## Market completeness
A property indicating that all required outcomes for a canonical market are present and eligible for evaluation.

## Market normalization
The process of translating provider-specific market names, identifiers, selections, parameters, and settlement semantics into canonical ArbiScan market representations.

## Market semantics
The exact meaning and settlement rules of a market, including scope such as regulation-only versus including overtime/extra time, participant mapping, handicap/total values, and void/push behavior where relevant.

## Mutually exclusive
Outcomes are mutually exclusive when no two of them can simultaneously be winning outcomes under the market's settlement rules.

## Opportunity
A validated ArbiScan domain object describing a detected arbitrage candidate, including event, market, selected provider quotes, implied-probability sum, stake plan, expected returns, freshness information, and provenance.

## Odds quote
A time-bound provider observation containing at minimum provider identity, event/market/selection references, price, status, and timestamps required by the configured validation policy.

## Provider
An authorized source of sports-odds data. A provider may represent a bookmaker, betting exchange, odds-data aggregator, or another licensed/authorized feed.

## Provider adapter
A boundary component responsible for provider-specific transport, authentication, payload parsing, status interpretation, and translation toward provider-neutral ingestion structures.

## Provider event reference
The provider-specific identifier or stable reference for an event.

## Provider market reference
The provider-specific identifier or stable reference for a market within an event.

## Provider/source timestamp
A timestamp supplied by the provider that describes when the quote or payload was generated, observed, or updated according to that provider's documented semantics.

## Provenance
Metadata sufficient to trace a normalized quote or opportunity back to its source provider data and processing context.

## Raw input
The original provider payload, message, or stable retrievable representation from which normalized data was derived. Retention is subject to provider terms and storage constraints.

## Scanner
A system that detects, evaluates, and reports arbitrage opportunities without automatically placing wagers. ArbiScan's initial product scope is scanner-only.

## Selection status
The current provider-derived state of a selection, such as active, suspended, closed, settled, or unavailable, after explicit mapping into ArbiScan semantics.

## Settlement semantics
The rules that determine when and how a market/selection wins, loses, pushes, or is voided. Equivalent labels are not sufficient for comparison if settlement semantics differ.

## Stake allocation
The process of dividing a total stake across all required outcomes of an arbitrage opportunity so that returns are balanced according to the configured constraints.

## Stake plan
A deterministic output describing per-selection stakes, expected payout per outcome, minimum modeled profit/return, rounding effects, and relevant constraints.

## Stale quote
A quote that violates the active freshness policy and is therefore ineligible for arbitrage detection.

## Theoretical arbitrage
An arbitrage satisfying the pure price equation `sum(1 / odds_i) < 1` before real-world execution constraints are applied.

## True/actionable arbitrage
A later-stage term for an opportunity that remains profitable after all modeled constraints relevant to the deployment are applied, such as rounding, minimum/maximum stakes, fees, commission, and quote freshness. ArbiScan must avoid calling a merely theoretical opportunity actionable unless those constraints have been evaluated.

## 1X2
A three-outcome football match-winner market with canonical outcomes:

- `1` / home win;
- `X` / draw;
- `2` / away win.

The precise settlement scope (for example regulation time) is part of the canonical market definition and must match across providers.
