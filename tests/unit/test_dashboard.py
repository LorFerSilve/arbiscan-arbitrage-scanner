from dataclasses import replace
from decimal import Decimal

import pytest

from arbiscan.dashboard import (
    AlertKind,
    AlertTracker,
    DashboardFilter,
    DashboardLeg,
    DashboardOpportunity,
    filter_opportunities,
)
from arbiscan.lifecycle import LifecycleState


def _opportunity(**changes: object) -> DashboardOpportunity:
    base = DashboardOpportunity(
        opportunity_id="opp-1",
        event_id="event-1",
        sport="football",
        competition="Premier League",
        market_id="winner",
        state=LifecycleState.ACTIONABLE,
        detected_at="2026-09-16T10:00:00Z",
        age_seconds=Decimal("2.5"),
        roi=Decimal("0.025"),
        guaranteed_payout=Decimal("102.50"),
        guaranteed_profit=Decimal("2.50"),
        legs=(
            DashboardLeg(
                "home",
                "provider-a",
                Decimal("2.10"),
                Decimal("50"),
                "2026-09-16T10:00:01Z",
            ),
            DashboardLeg(
                "away",
                "provider-b",
                Decimal("2.05"),
                Decimal("50"),
                "2026-09-16T10:00:01Z",
            ),
        ),
        provenance=("book:event-1:winner",),
    )
    return replace(base, **changes)


def test_dashboard_projection_rejects_invalid_age_and_missing_legs() -> None:
    with pytest.raises(ValueError, match="age_seconds"):
        _opportunity(age_seconds=Decimal("-1"))
    with pytest.raises(ValueError, match="at least one leg"):
        _opportunity(legs=())


def test_filters_cover_sport_competition_provider_roi_profit_and_state() -> None:
    item = _opportunity()
    assert filter_opportunities((item,), DashboardFilter(sport="football")) == (item,)
    assert filter_opportunities((item,), DashboardFilter(competition="La Liga")) == ()
    assert filter_opportunities((item,), DashboardFilter(provider_id="provider-b")) == (item,)
    assert filter_opportunities((item,), DashboardFilter(provider_id="provider-c")) == ()
    assert filter_opportunities((item,), DashboardFilter(minimum_roi=Decimal("0.03"))) == ()
    assert filter_opportunities((item,), DashboardFilter(minimum_profit=Decimal("2.00"))) == (
        item,
    )

    stale = _opportunity(state=LifecycleState.STALE)
    assert filter_opportunities((stale,), DashboardFilter()) == ()
    assert filter_opportunities((stale,), DashboardFilter(include_inactive=True)) == (stale,)


def test_alerts_are_deduplicated_and_age_is_not_material() -> None:
    tracker = AlertTracker()
    item = _opportunity()
    first = tracker.evaluate(item)
    assert first is not None and first.kind is AlertKind.CREATED
    assert tracker.evaluate(replace(item, age_seconds=Decimal("8"))) is None

    changed = tracker.evaluate(replace(item, roi=Decimal("0.03")))
    assert changed is not None and changed.kind is AlertKind.CHANGED
    assert tracker.evaluate(replace(item, roi=Decimal("0.03"))) is None


def test_transition_to_stale_emits_expiration_once() -> None:
    tracker = AlertTracker()
    item = _opportunity()
    tracker.evaluate(item)
    expired = tracker.evaluate(replace(item, state=LifecycleState.STALE))
    assert expired is not None and expired.kind is AlertKind.EXPIRED
    assert (
        tracker.evaluate(replace(item, state=LifecycleState.STALE, age_seconds=Decimal("20")))
        is None
    )
