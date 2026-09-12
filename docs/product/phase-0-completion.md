# Phase 0 Completion Record

**Phase:** Product definition, scope, and invariants  
**Status:** Complete  
**Date:** 2026-09-13

This record maps the Phase 0 roadmap requirements to the repository artifacts that satisfy them.

## Deliverables

| Roadmap deliverable | Artifact | Status |
|---|---|---|
| Product requirements | `docs/product/requirements.md` | Complete |
| Product non-goals | `docs/product/non-goals.md` | Complete |
| Shared glossary | `docs/product/glossary.md` | Complete |
| Initial risk register | `docs/product/risk-register.md` | Complete |
| Provider integration checklist | `docs/product/provider-integration-checklist.md` | Complete |
| ADR structure/process | `docs/adr/README.md` | Complete |
| Initial product-boundary ADR | `docs/adr/0001-scanner-only-mvp-boundary.md` | Accepted |

## Roadmap task validation

### 0.1 Functional scope — Complete

The end-to-end scanner workflow is defined in `requirements.md`, including ingestion, canonical event matching, market normalization, best-price selection, implied-probability calculation, stake planning, validation, and downstream exposure.

### 0.2 Initial market scope — Complete

The MVP is explicitly constrained to:

1. football — pre-match 1X2 match winner;
2. tennis — pre-match two-way match winner.

Live/in-play markets and broader market types remain non-goals until later explicit phases.

### 0.3 Core invariants — Complete

The requirements define invariants for:

- odds validity;
- complete mutually exclusive and collectively exhaustive outcomes;
- event identity;
- quote provenance;
- freshness;
- market/selection status;
- deterministic reproducibility;
- fail-closed ambiguity handling.

### 0.4 Legal/provider constraints — Complete for the architecture phase

`provider-integration-checklist.md` defines the review gate required before a real provider is enabled, covering authorized access, licensing/terms, geographic constraints, caching/storage/redistribution restrictions, rate limits, authentication, timestamp semantics, settlement semantics, testing, and production readiness.

Phase 0 intentionally does not claim that any specific provider has already passed this review.

## Exit criteria

### Requirements and non-goals are written and internally consistent

**Satisfied.** The product requirements define what the scanner must do; the non-goals explicitly exclude automated wagering, live markets, broad market coverage, unauthorized data acquisition, and other scope that would conflict with the MVP.

### MVP sports/markets are explicitly chosen

**Satisfied.** Football pre-match 1X2 and tennis pre-match two-way match winner are the explicit MVP markets.

### Core invariants are documented

**Satisfied.** Correctness, semantic equivalence, completeness, freshness, provenance, status, reproducibility, and fail-closed behavior are normative requirements.

### No ambiguity remains about scanner vs automated betting platform

**Satisfied.** ADR-0001 is Accepted and defines ArbiScan v1 as scanner-only. Automated bet placement requires a separate future ADR and design process.

## Phase 0 decision summary

The following decisions are now binding inputs to subsequent roadmap phases unless superseded by an accepted ADR:

- ArbiScan v1 is a scanner/decision-support system, not an automated betting system.
- Football 1X2 is the first implementation target.
- Tennis match winner is the second MVP market shape.
- MVP detection is pre-match only.
- Provider-specific semantics stay behind adapters.
- Event and market ambiguity fails closed.
- Freshness is part of correctness.
- Arbitrage mathematics must be deterministic and reproducible.
- Theoretical arbitrage must not be presented as guaranteed real-world execution.
- Real provider integrations require an explicit provider review before production use.

## Next phase

The next roadmap dependency is **Phase 1 — Repository bootstrap and engineering standards**.

No Phase 1 implementation decision should weaken the Phase 0 invariants without an explicit ADR.
