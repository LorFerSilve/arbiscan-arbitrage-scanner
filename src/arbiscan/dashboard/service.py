"""Dashboard filtering and deterministic alert deduplication."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from arbiscan.dashboard.models import (
    AlertKind,
    DashboardFilter,
    DashboardOpportunity,
    OpportunityAlert,
)
from arbiscan.lifecycle import LifecycleState

_INACTIVE_STATES = {LifecycleState.STALE, LifecycleState.INVALIDATED, LifecycleState.EXPIRED}


def filter_opportunities(
    opportunities: Iterable[DashboardOpportunity], criteria: DashboardFilter
) -> tuple[DashboardOpportunity, ...]:
    """Apply dashboard filters without changing backend calculations."""
    result = []
    for item in opportunities:
        if not criteria.include_inactive and item.state in _INACTIVE_STATES:
            continue
        if criteria.sport is not None and item.sport != criteria.sport:
            continue
        if criteria.competition is not None and item.competition != criteria.competition:
            continue
        if criteria.provider_id is not None and all(
            leg.provider_id != criteria.provider_id for leg in item.legs
        ):
            continue
        if criteria.minimum_roi is not None and item.roi < criteria.minimum_roi:
            continue
        if criteria.minimum_profit is not None and item.guaranteed_profit < criteria.minimum_profit:
            continue
        result.append(item)
    return tuple(result)


class AlertTracker:
    """Emit only new, materially changed, or newly expired opportunities."""

    def __init__(self) -> None:
        self._fingerprints: dict[str, str] = {}
        self._states: dict[str, LifecycleState] = {}

    def evaluate(self, opportunity: DashboardOpportunity) -> OpportunityAlert | None:
        fingerprint = _fingerprint(opportunity)
        previous_fingerprint = self._fingerprints.get(opportunity.opportunity_id)
        previous_state = self._states.get(opportunity.opportunity_id)
        self._fingerprints[opportunity.opportunity_id] = fingerprint
        self._states[opportunity.opportunity_id] = opportunity.state

        if previous_fingerprint is None:
            kind = AlertKind.EXPIRED if opportunity.state in _INACTIVE_STATES else AlertKind.CREATED
        elif opportunity.state in _INACTIVE_STATES and previous_state not in _INACTIVE_STATES:
            kind = AlertKind.EXPIRED
        elif fingerprint != previous_fingerprint:
            kind = AlertKind.CHANGED
        else:
            return None
        return OpportunityAlert(
            opportunity_id=opportunity.opportunity_id,
            kind=kind,
            state=opportunity.state,
            fingerprint=fingerprint,
        )


def _fingerprint(opportunity: DashboardOpportunity) -> str:
    """Fingerprint only material opportunity data; age alone must not create alert spam."""
    legs = tuple(
        (leg.selection_id, leg.provider_id, str(leg.decimal_price), str(leg.stake))
        for leg in opportunity.legs
    )
    material = (
        opportunity.event_id,
        opportunity.market_id,
        opportunity.state.value,
        str(opportunity.roi),
        str(opportunity.guaranteed_payout),
        str(opportunity.guaranteed_profit),
        legs,
    )
    return hashlib.sha256(repr(material).encode()).hexdigest()
