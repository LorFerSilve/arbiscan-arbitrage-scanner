# Product Documentation

This directory contains the normative Phase 0 product-definition artifacts for ArbiScan.

## Documents

- [`requirements.md`](requirements.md) — product scope, functional workflow, core invariants, MVP markets, security/reliability requirements, and acceptance criteria.
- [`non-goals.md`](non-goals.md) — explicit exclusions that prevent scope drift.
- [`glossary.md`](glossary.md) — canonical terminology used throughout the project.
- [`risk-register.md`](risk-register.md) — initial correctness, security, provider, operational, and product risks.
- [`provider-integration-checklist.md`](provider-integration-checklist.md) — mandatory review gate before enabling a real odds provider.
- [`phase-0-completion.md`](phase-0-completion.md) — evidence that the Phase 0 roadmap exit criteria are satisfied.

Architecture decisions are maintained separately under [`../adr/`](../adr/).

## Normative precedence

If product documentation conflicts:

1. an accepted, non-superseded ADR governs the architecture decision it explicitly covers;
2. current product requirements govern functional and correctness requirements;
3. non-goals constrain implicit expansion of scope;
4. later implementation must not silently weaken these documents.

Material changes to Phase 0 decisions should be made through a pull request and, when architectural, a new ADR.
