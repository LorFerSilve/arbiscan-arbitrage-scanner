# Product Documentation

This directory contains ArbiScan's normative product-definition, correctness, risk, and provider-onboarding documents. The original Phase 0 artifacts remain authoritative, while later phase documents extend the product boundary without weakening those invariants.

## Documents

- [`requirements.md`](requirements.md) — product scope, functional workflow, core invariants, MVP markets, security/reliability requirements, and acceptance criteria.
- [`non-goals.md`](non-goals.md) — explicit exclusions that prevent scope drift.
- [`glossary.md`](glossary.md) — canonical terminology used throughout the project.
- [`risk-register.md`](risk-register.md) — correctness, security, provider, operational, and product risks.
- [`provider-integration-checklist.md`](provider-integration-checklist.md) — mandatory review gate before enabling any real odds source.
- [`dashboard-and-alerts.md`](dashboard-and-alerts.md) — Phase 15 read-only dashboard projection and channel-independent alert boundary.
- [`phase-0-completion.md`](phase-0-completion.md) — evidence that the Phase 0 roadmap exit criteria are satisfied.

Architecture decisions are maintained separately under [`../adr/`](../adr/). Provider-specific documentation and the Phase 16 hand-off live under [`../providers/`](../providers/).

## Normative precedence

If product documentation conflicts:

1. an accepted, non-superseded ADR governs the architecture decision it explicitly covers;
2. current product requirements govern functional and correctness requirements;
3. non-goals constrain implicit expansion of scope;
4. provider onboarding must satisfy the provider integration checklist;
5. later implementation must not silently weaken these documents.

Material changes to product decisions should be made through a pull request and, when architectural, a new ADR.
