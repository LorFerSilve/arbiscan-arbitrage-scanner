"""Provider-independent outright candidate-set and settlement safety assessment."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutrightEvaluationProfile:
    """Evidence required before generic N-outcome arbitrage math may model an outright."""

    candidate_set_complete: bool
    candidate_set_static: bool
    mutually_exclusive: bool
    exhaustive: bool
    has_field_or_other: bool
    ties_possible: bool
    dead_heat_possible: bool
    withdrawal_rules_equivalent: bool
    void_rules_equivalent: bool

    def __post_init__(self) -> None:
        for field_name in (
            "candidate_set_complete",
            "candidate_set_static",
            "mutually_exclusive",
            "exhaustive",
            "has_field_or_other",
            "ties_possible",
            "dead_heat_possible",
            "withdrawal_rules_equivalent",
            "void_rules_equivalent",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise ValueError(f"outright profile {field_name} must be bool")


@dataclass(frozen=True, slots=True)
class OutrightMathEligibility:
    """Deterministic result of the generic outright-math safety gate."""

    eligible: bool
    blockers: tuple[str, ...]


def assess_generic_outright_math(
    profile: OutrightEvaluationProfile,
) -> OutrightMathEligibility:
    """Return whether ordinary reciprocal-odds/stake math is semantically sufficient.

    This gate answers only the payout-shape question. It does not enable a provider
    market by itself. Runtime activation still requires canonical identity,
    freshness, provider equivalence, and the normal market-support gate.
    """

    if not isinstance(profile, OutrightEvaluationProfile):
        raise ValueError("profile must be OutrightEvaluationProfile")

    blockers: list[str] = []
    if not profile.candidate_set_complete:
        blockers.append("candidate set is incomplete")
    if not profile.candidate_set_static:
        blockers.append("candidate set is dynamic")
    if not profile.mutually_exclusive:
        blockers.append("outcomes are not mutually exclusive")
    if not profile.exhaustive:
        blockers.append("outcomes are not exhaustive")
    if profile.has_field_or_other:
        blockers.append("field/other outcome is present")
    if profile.ties_possible:
        blockers.append("ties can produce non-exclusive settlement")
    if profile.dead_heat_possible:
        blockers.append("dead-heat settlement can split returns")
    if not profile.withdrawal_rules_equivalent:
        blockers.append("withdrawal settlement rules are not proven equivalent")
    if not profile.void_rules_equivalent:
        blockers.append("void settlement rules are not proven equivalent")

    return OutrightMathEligibility(eligible=not blockers, blockers=tuple(blockers))
