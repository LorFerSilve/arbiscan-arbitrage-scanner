"""Phase 17.11 outright settlement-safety and generic-math regressions."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from arbiscan.arbitrage import is_theoretical_arbitrage
from arbiscan.domain import EventId, Market, MarketId, MarketKind, MarketPeriod, Sport
from arbiscan.normalization import (
    OutrightEvaluationProfile,
    assess_generic_outright_math,
    assess_market_support,
)


def _safe_profile() -> OutrightEvaluationProfile:
    return OutrightEvaluationProfile(
        candidate_set_complete=True,
        candidate_set_static=True,
        mutually_exclusive=True,
        exhaustive=True,
        has_field_or_other=False,
        ties_possible=False,
        dead_heat_possible=False,
        withdrawal_rules_equivalent=True,
        void_rules_equivalent=True,
    )


def test_strict_complete_outright_subset_can_reuse_generic_n_outcome_math() -> None:
    decision = assess_generic_outright_math(_safe_profile())

    assert decision.eligible
    assert decision.blockers == ()
    assert is_theoretical_arbitrage(tuple(Decimal("6") for _ in range(5)))


def test_outfight_safety_gate_reports_each_semantic_blocker_fail_closed() -> None:
    safe = _safe_profile()
    cases = (
        (replace(safe, candidate_set_complete=False), "candidate set is incomplete"),
        (replace(safe, candidate_set_static=False), "candidate set is dynamic"),
        (replace(safe, mutually_exclusive=False), "outcomes are not mutually exclusive"),
        (replace(safe, exhaustive=False), "outcomes are not exhaustive"),
        (replace(safe, has_field_or_other=True), "field/other outcome is present"),
        (replace(safe, ties_possible=True), "ties can produce non-exclusive settlement"),
        (replace(safe, dead_heat_possible=True), "dead-heat settlement can split returns"),
        (
            replace(safe, withdrawal_rules_equivalent=False),
            "withdrawal settlement rules are not proven equivalent",
        ),
        (
            replace(safe, void_rules_equivalent=False),
            "void settlement rules are not proven equivalent",
        ),
    )

    for profile, blocker in cases:
        decision = assess_generic_outright_math(profile)
        assert not decision.eligible
        assert blocker in decision.blockers


def test_broader_tournament_outright_remains_runtime_disabled_pending_provider_proof() -> None:
    market = Market(
        id=MarketId("market:phase17-11:tournament-winner"),
        event_id=EventId("event:phase17-11:tournament"),
        kind=MarketKind.OUTRIGHT_WINNER,
        period=MarketPeriod.TOURNAMENT,
    )

    decision = assess_market_support(sport=Sport.FOOTBALL, market=market)

    assert not decision.supported
    assert "Phase 17.11" in decision.detail
    assert "runtime-disabled" in decision.detail
