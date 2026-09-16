from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from unittest import TestCase

from arbiscan.dashboard import (
    AlertKind,
    AlertTracker,
    DashboardFilter,
    DashboardLeg,
    DashboardOpportunity,
    filter_opportunities,
    render_dashboard,
)
from arbiscan.lifecycle import LifecycleState


def _leg(**overrides: object) -> DashboardLeg:
    values: dict[str, object] = {
        "selection_id": "home",
        "provider_id": "provider-a",
        "decimal_price": Decimal("2.10"),
        "stake": Decimal("47.62"),
        "quote_observed_at": "2026-09-16T10:00:00Z",
    }
    values.update(overrides)
    return DashboardLeg(**values)  # type: ignore[arg-type]


def _opportunity(**overrides: object) -> DashboardOpportunity:
    values: dict[str, object] = {
        "opportunity_id": "opp-1",
        "event_id": "event-1",
        "sport": "football",
        "competition": "Premier League",
        "market_id": "match-winner",
        "state": LifecycleState.ACTIONABLE,
        "detected_at": "2026-09-16T10:00:01Z",
        "age_seconds": Decimal("1.25"),
        "roi": Decimal("0.0250"),
        "guaranteed_payout": Decimal("102.50"),
        "guaranteed_profit": Decimal("2.50"),
        "currency": "EUR",
        "assumptions": ("stakes rounded to €0.01", "fees and tax already included"),
        "legs": (_leg(), _leg(selection_id="away", provider_id="provider-b")),
        "provenance": ("book:match-winner", "detector:v1"),
    }
    values.update(overrides)
    return DashboardOpportunity(**values)  # type: ignore[arg-type]


def test_projection_rejects_invalid_backend_values() -> None:
    case = TestCase()
    with case.assertRaisesRegex(ValueError, "age_seconds"):
        _opportunity(age_seconds=Decimal("-1"))
    with case.assertRaisesRegex(ValueError, "finite"):
        _opportunity(roi=Decimal("NaN"))
    with case.assertRaisesRegex(ValueError, "three-letter"):
        _opportunity(currency="euros")
    with case.assertRaisesRegex(ValueError, "assumptions"):
        _opportunity(assumptions=())
    with case.assertRaisesRegex(ValueError, "at least one leg"):
        _opportunity(legs=())
    with case.assertRaisesRegex(ValueError, "finite"):
        _leg(decimal_price=Decimal("Infinity"))


def test_filters_cover_sport_competition_provider_roi_profit_and_state() -> None:
    item = _opportunity()
    assert filter_opportunities((item,), DashboardFilter(sport="football")) == (item,)
    assert filter_opportunities((item,), DashboardFilter(competition="La Liga")) == ()
    assert filter_opportunities((item,), DashboardFilter(provider_id="provider-b")) == (item,)
    assert filter_opportunities((item,), DashboardFilter(provider_id="provider-c")) == ()
    assert filter_opportunities((item,), DashboardFilter(minimum_roi=Decimal("0.03"))) == ()
    assert filter_opportunities((item,), DashboardFilter(minimum_profit=Decimal("2.00"))) == (item,)

    stale = _opportunity(state=LifecycleState.STALE)
    assert filter_opportunities((stale,), DashboardFilter()) == ()
    assert filter_opportunities((stale,), DashboardFilter(include_inactive=True)) == (stale,)


def test_renderer_keeps_backend_values_context_and_provenance_visible() -> None:
    html = render_dashboard((_opportunity(),))
    assert "1.25s" in html
    assert "provider-a" in html
    assert "provider-b" in html
    assert "2.10" in html
    assert "47.62 EUR" in html
    assert "102.50 EUR" in html
    assert "2.50 EUR" in html
    assert "stakes rounded to €0.01" in html
    assert "fees and tax already included" in html
    assert "book:match-winner" in html


def test_renderer_escapes_untrusted_display_values() -> None:
    html = render_dashboard(
        (_opportunity(sport='<script>alert("x")</script>', provenance=("<b>raw</b>",)),)
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>raw</b>" not in html
    assert "&lt;b&gt;raw&lt;/b&gt;" in html


def test_alert_deduplication_tracks_created_material_change_and_expiry() -> None:
    tracker = AlertTracker()
    original = _opportunity()

    created = tracker.evaluate(original)
    assert created is not None
    assert created.kind is AlertKind.CREATED
    assert tracker.evaluate(original) is None

    refreshed = replace(original, opportunity_id="opp-2", age_seconds=Decimal("2.00"))
    assert tracker.evaluate(refreshed) is None

    changed = replace(refreshed, guaranteed_profit=Decimal("3.00"))
    material = tracker.evaluate(changed)
    assert material is not None
    assert material.kind is AlertKind.CHANGED
    assert tracker.evaluate(changed) is None

    metadata_changed = replace(changed, provenance=("book:corrected", "detector:v1"))
    metadata_alert = tracker.evaluate(metadata_changed)
    assert metadata_alert is not None
    assert metadata_alert.kind is AlertKind.CHANGED

    expired = replace(metadata_changed, state=LifecycleState.EXPIRED)
    expiry = tracker.evaluate(expired)
    assert expiry is not None
    assert expiry.kind is AlertKind.EXPIRED
    assert tracker.evaluate(expired) is None


def test_invalidation_alert_is_emitted_once_and_hidden_by_default() -> None:
    tracker = AlertTracker()
    active = _opportunity()
    tracker.evaluate(active)
    invalidated = replace(active, state=LifecycleState.INVALIDATED)

    event = tracker.evaluate(invalidated)
    assert event is not None
    assert event.kind is AlertKind.EXPIRED
    assert tracker.evaluate(invalidated) is None
    assert filter_opportunities((invalidated,), DashboardFilter()) == ()
