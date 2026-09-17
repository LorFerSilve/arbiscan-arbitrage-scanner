# Phase 16.2 — Multi-source provenance hardening

Phase 16.2 implements the ADR-0012 architecture gate required before a second real transport source may participate in actionable scanning.

## Implemented boundary

ArbiScan now models two distinct identities on every canonical odds quote:

- `OddsQuote.provider_id` remains the **price provider** — the bookmaker or exchange that actually offers the executable price;
- `OddsQuote.transport_provider_id` identifies the **transport/source provider** — the independent API or feed through which ArbiScan observed that price.

Direct-source and legacy single-source quote construction remains backwards compatible: when no explicit transport identity is supplied, the transport provider defaults to the price provider.

The arbitrage, market-book, provider-filtering, and stake-planning layers remain price-provider-centric. Transport identity is provenance and reliability metadata; it does not create a second executable bookmaker merely because two feeds observed the same price origin.

## Source-observation identity

Strict normalization now creates deterministic, collision-resistant quote observation IDs from both provider identities plus canonical/source identity, effective source time, and price.

This prevents two transports reporting the same bookmaker/event/market/selection at the same timestamp from colliding in persistence or live state. A same-source same-timestamp price correction also receives a distinct observation ID rather than silently overwriting an incompatible payload under one canonical ID.

## Multi-source live state

`MultiSourceQuoteStore` preserves one live observation state per:

```text
transport source
+ price provider
+ canonical event
+ canonical market
+ canonical selection
```

The scanner therefore no longer relies on last-write behavior between overlapping feeds.

Before market-book construction, source observations are consolidated into executable price-provider slots using the ADR-0012 rules:

1. inactive, stale, future-invalid, explicitly source-invalidated, and malformed observations are excluded first;
2. the newest eligible effective timestamp wins;
3. equal-time observations with identical price/status semantics are equivalent and one is selected deterministically;
4. equal-time observations with materially different price/status semantics fail closed for that bookmaker/selection slot;
5. all underlying source observations remain distinct in live state even when one consolidated quote is selected for the market book.

No hard-coded transport trust ranking was introduced.

## Source-specific invalidation

Explicit source suspension/closure invalidation is now keyed by transport source as well as bookmaker and canonical outcome.

A suspension observed through source A can therefore invalidate source A's observation without incorrectly deleting or suppressing a still-valid observation of the same bookmaker received through source B.

## Serialization compatibility

Canonical JSON serialization advances from schema version 1 to schema version 2.

Schema-v1 `OddsQuote` payloads remain readable through a narrow migration that supplies the only first-class provider identity available in the old schema as the legacy transport identity. Other v1 model payloads retain strict exact-field validation; Phase 16.2 does not generally relax missing-field behavior.

New payloads always serialize explicit transport provenance.

## Persistence migration

SQLite persistence adds migration version 2:

- `canonical_snapshots.transport_provider_id` is added;
- legacy odds-quote rows are backfilled conservatively from their existing `provider_id` because schema v1 did not persist transport identity as a first-class field;
- an index supports transport-provider/time queries;
- new quote persistence records price-provider and transport-provider identity separately.

Persisting semantically identical canonical evidence across serializer schema versions remains idempotent. A v1 persisted object is not treated as an ID collision merely because the current serializer emits the equivalent v2 envelope.

The legacy backfill is intentionally conservative: historical schema-v1 aggregator rows may retain richer source information only inside their pre-existing raw provenance reference. Phase 16.2 does not infer structured identity by parsing opaque provenance strings.

## Observability

Realtime cycle metrics now expose:

- `source_conflict_count`;
- `equivalent_source_observation_count`.

The observable scanner records corresponding metrics and structured-log fields. This makes overlap disagreements diagnosable without treating them as arbitrary provider precedence decisions.

## Price-provider identity requirement for Phase 16.3

The consolidation layer assumes that observations of the same real bookmaker use the same canonical `provider_id` even when they arrive through different transports.

Existing The Odds API bookmaker identifiers are retained for backwards compatibility in this phase. The OddsPapi adapter therefore must not invent an independent OddsPapi-specific bookmaker identity for a known overlapping bookmaker. Phase 16.3 must introduce explicit provider-local-to-canonical bookmaker mapping where overlap exists. Unknown bookmaker equivalence must fail closed rather than being guessed from display-name similarity.

This requirement is deliberately kept out of generic arbitrage mathematics and belongs at the provider/canonicalization boundary.

## Validation evidence

Phase 16.2 regressions cover:

- explicit transport identity distinct from price-provider identity;
- backwards-compatible direct-source quote construction;
- schema-v1 `OddsQuote` deserialization into schema-v2 semantics;
- collision-safe observation IDs across transports and price corrections;
- two transports retaining independent live observations for one bookmaker slot;
- newest-source selection;
- deterministic equivalent-observation consolidation;
- fail-closed equal-time conflict handling;
- source-specific invalidation without suppressing another transport;
- independent revision histories per transport;
- SQLite v1→v2 migration and transport-provider backfill;
- separate persistence indexing of price provider and transport provider.

The normal repository quality gate remains authoritative for formatting, Ruff, strict mypy, pytest, and dependency audit.

## Exit-criteria mapping

- **Transport/source identity is first-class canonical provenance:** implemented on `OddsQuote` and in persistence.
- **Source observations cannot collide merely because they report the same bookmaker price:** normalized IDs include transport identity and source evidence.
- **Overlapping observations remain separate until deterministic consolidation:** implemented by `MultiSourceQuoteStore`.
- **The same bookmaker cannot be counted twice because two APIs reported it:** consolidation emits at most one eligible quote per bookmaker/selection slot.
- **Equal-time material conflicts fail closed:** conflicting slot is excluded and diagnosed.
- **Equivalent observations remain deterministic and auditable:** deterministic selection with all source observations retained.
- **Source invalidation remains isolated:** invalidation keys include transport identity.
- **Persistence/serialization are migration-safe:** schema-v2 JSON and SQLite migration v2 preserve readable legacy evidence.
- **Operational overlap failures are observable:** conflict/equivalence metrics and diagnostics are explicit.
- **No provider-specific logic leaked into arbitrage/staking mathematics:** those layers remain unchanged and price-provider-centric.

## Deliberately deferred

Phase 16.2 does not implement:

- the OddsPapi API adapter;
- automatic bookmaker alias inference;
- live OddsPapi credentials or captured proprietary fixtures;
- source trust-ranking heuristics;
- Phase 17 advanced markets;
- Phase 18 historical expansion;
- local packaging/deployment.

## Next dependency

The next roadmap dependency is **Phase 16.3 — second provider adapter** using the OddsPapi development target selected in Phase 16.1.

Phase 16.3 must build strictly behind `ProviderAdapter`, use explicit bookmaker identity mappings for known overlap, preserve the Phase-16.2 transport provenance model, and remain subject to the data-rights blockers recorded in `docs/providers/oddspapi.md`.
