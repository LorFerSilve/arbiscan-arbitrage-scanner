from __future__ import annotations

from arbiscan.api import (
    ApiSecurityPolicy,
    ArbiScanApi,
    EventSummaryResponse,
    OddsResponse,
    OpportunityDetailResponse,
    OpportunitySummaryResponse,
    PageRequest,
    ProviderStatusResponse,
    SportResponse,
    openapi_document,
)


class FakeSource:
    def readiness_checks(self) -> dict[str, bool]:
        return {"ingestion": True, "persistence": True}

    def provider_statuses(self) -> tuple[ProviderStatusResponse, ...]:
        return (ProviderStatusResponse("provider-a", True),)

    def sports(self) -> tuple[SportResponse, ...]:
        return (SportResponse("football"), SportResponse("tennis"))

    def events(self) -> tuple[EventSummaryResponse, ...]:
        return (
            EventSummaryResponse(
                "event-1",
                "football",
                "League",
                ("A", "B"),
                "2026-01-01T12:00:00+00:00",
                "scheduled",
            ),
            EventSummaryResponse(
                "event-2",
                "tennis",
                "Open",
                ("C", "D"),
                "2026-01-01T13:00:00+00:00",
                "scheduled",
            ),
        )

    def odds(self) -> tuple[OddsResponse, ...]:
        return (
            OddsResponse(
                "quote-1",
                "event-1",
                "market-1",
                "selection-1",
                "provider-a",
                "2.10",
                "active",
                "2026-01-01T11:59:00+00:00",
            ),
        )

    def opportunities(self) -> tuple[OpportunitySummaryResponse, ...]:
        return (
            OpportunitySummaryResponse(
                "opp-1",
                "event-1",
                "market-1",
                "0.95",
                "0.05",
                "2026-01-01T11:59:30+00:00",
            ),
        )

    def opportunity(self, opportunity_id: str) -> OpportunityDetailResponse | None:
        if opportunity_id != "opp-1":
            return None
        return OpportunityDetailResponse(self.opportunities()[0], ("quote-1",), True)

    def metrics(self) -> dict[str, int | float]:
        return {"active_quotes": 1, "opportunities_detected": 1}


def test_api_filters_and_paginates_without_exposing_storage() -> None:
    api = ArbiScanApi(FakeSource(), version="0.1")
    page = api.events(PageRequest(limit=1), sport="football")

    assert page.total == 1
    assert page.items[0].event_id == "event-1"
    assert not page.has_more
    assert api.opportunity("opp-1") is not None
    assert api.opportunity("missing") is None


def test_non_local_deployment_requires_authentication_and_rate_limiting() -> None:
    source = FakeSource()
    try:
        ArbiScanApi(source, version="0.1", security=ApiSecurityPolicy(bind_host="0.0.0.0"))
    except ValueError as exc:
        assert "authentication" in str(exc)
    else:
        raise AssertionError("non-local unauthenticated deployment must fail closed")

    try:
        ArbiScanApi(
            source,
            version="0.1",
            security=ApiSecurityPolicy(bind_host="0.0.0.0", authentication_enabled=True),
        )
    except ValueError as exc:
        assert "rate limiting" in str(exc)
    else:
        raise AssertionError("non-local deployment without rate limiting must fail closed")

    ArbiScanApi(
        source,
        version="0.1",
        security=ApiSecurityPolicy(
            bind_host="0.0.0.0", authentication_enabled=True, rate_limiting_enabled=True
        ),
    )


def test_openapi_contract_contains_required_phase_13_routes() -> None:
    document = openapi_document(version="0.1")
    paths = document["paths"]

    assert document["openapi"] == "3.1.0"
    assert "/health" in paths
    assert "/providers/status" in paths
    assert "/events" in paths
    assert "/odds" in paths
    assert "/opportunities" in paths
    assert "/opportunities/{opportunity_id}" in paths
    assert "/configuration/status" in paths
    assert "/metrics" in paths
