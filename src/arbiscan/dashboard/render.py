"""Dependency-free HTML rendering for the local ArbiScan dashboard."""

from __future__ import annotations

from html import escape

from arbiscan.dashboard.models import DashboardOpportunity


def render_dashboard(opportunities: tuple[DashboardOpportunity, ...]) -> str:
    """Render backend projections verbatim; calculations are never recomputed in the UI."""
    cards = "".join(_render_opportunity(item) for item in opportunities)
    if not cards:
        cards = '<p class="empty">No active opportunities.</p>'
    return f'<main class="arbiscan-dashboard"><h1>ArbiScan opportunities</h1>{cards}</main>'


def _render_opportunity(item: DashboardOpportunity) -> str:
    legs = "".join(
        "<li>"
        f"{escape(leg.selection_id)} — {escape(leg.provider_id)} — "
        f"odds {escape(str(leg.decimal_price))} — "
        f"stake {escape(str(leg.stake))} {escape(item.currency)} — "
        f"quoted {escape(leg.quote_observed_at)}"
        "</li>"
        for leg in item.legs
    )
    assumptions = "".join(f"<li>{escape(value)}</li>" for value in item.assumptions)
    provenance = "".join(f"<li>{escape(value)}</li>" for value in item.provenance)
    return (
        f'<article data-opportunity-id="{escape(item.opportunity_id)}">'
        f"<h2>{escape(item.sport)} / {escape(item.competition)}</h2>"
        f"<p>State: {escape(item.state.value)}</p>"
        f"<p>Age: {escape(str(item.age_seconds))}s</p>"
        f"<p>ROI: {escape(str(item.roi))}</p>"
        f"<p>Guaranteed payout: {escape(str(item.guaranteed_payout))} "
        f"{escape(item.currency)}</p>"
        f"<p>Guaranteed profit: {escape(str(item.guaranteed_profit))} "
        f"{escape(item.currency)}</p>"
        f'<ul class="legs">{legs}</ul>'
        f'<ul class="assumptions">{assumptions}</ul>'
        f'<ul class="provenance">{provenance}</ul>'
        "</article>"
    )
