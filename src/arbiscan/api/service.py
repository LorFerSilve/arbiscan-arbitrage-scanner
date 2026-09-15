"""Application service boundary exposed to HTTP/CLI/UI transports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from arbiscan.api.contracts import (
    ConfigurationStatusResponse,
    EventSummaryResponse,
    HealthResponse,
    MetricsResponse,
    OddsResponse,
    OpportunityDetailResponse,
    OpportunitySummaryResponse,
    Page,
    PageRequest,
    ProviderStatusResponse,
    ReadinessResponse,
    SportResponse,
)

T = TypeVar("T")


class ApiDataSource(Protocol):
    """Read model required by the API; deliberately hides persistence internals."""

    def readiness_checks(self) -> dict[str, bool]: ...

    def provider_statuses(self) -> Sequence[ProviderStatusResponse]: ...

    def sports(self) -> Sequence[SportResponse]: ...

    def events(self) -> Sequence[EventSummaryResponse]: ...

    def odds(self) -> Sequence[OddsResponse]: ...

    def opportunities(self) -> Sequence[OpportunitySummaryResponse]: ...

    def opportunity(self, opportunity_id: str) -> OpportunityDetailResponse | None: ...

    def metrics(self) -> dict[str, int | float]: ...


@dataclass(frozen=True, slots=True)
class ApiSecurityPolicy:
    """Deployment guardrails for exposing the application boundary."""

    bind_host: str = "127.0.0.1"
    authentication_enabled: bool = False
    rate_limiting_enabled: bool = False

    def validate(self) -> None:
        local_hosts = {"127.0.0.1", "::1", "localhost"}
        if self.bind_host not in local_hosts and not self.authentication_enabled:
            raise ValueError("authentication is required for non-local API deployments")
        if self.bind_host not in local_hosts and not self.rate_limiting_enabled:
            raise ValueError("rate limiting is required for non-local API deployments")


class ArbiScanApi:
    """Stable query interface consumed by future transport adapters."""

    def __init__(
        self,
        source: ApiDataSource,
        *,
        version: str,
        security: ApiSecurityPolicy | None = None,
    ) -> None:
        self._source = source
        self._version = version
        self._security = security or ApiSecurityPolicy()
        self._security.validate()

    def health(self) -> HealthResponse:
        return HealthResponse(status="ok", version=self._version)

    def readiness(self) -> ReadinessResponse:
        checks = dict(self._source.readiness_checks())
        return ReadinessResponse(ready=bool(checks) and all(checks.values()), checks=checks)

    def providers(self, page: PageRequest | None = None) -> Page[ProviderStatusResponse]:
        return _page(self._source.provider_statuses(), page or PageRequest())

    def sports(self, page: PageRequest | None = None) -> Page[SportResponse]:
        return _page(self._source.sports(), page or PageRequest())

    def events(
        self,
        page: PageRequest | None = None,
        *,
        sport: str | None = None,
        status: str | None = None,
    ) -> Page[EventSummaryResponse]:
        values = tuple(
            event
            for event in self._source.events()
            if (sport is None or event.sport == sport) and (status is None or event.status == status)
        )
        return _page(values, page or PageRequest())

    def odds(
        self,
        page: PageRequest | None = None,
        *,
        event_id: str | None = None,
        provider_id: str | None = None,
    ) -> Page[OddsResponse]:
        values = tuple(
            quote
            for quote in self._source.odds()
            if (event_id is None or quote.event_id == event_id)
            and (provider_id is None or quote.provider_id == provider_id)
        )
        return _page(values, page or PageRequest())

    def opportunities(
        self,
        page: PageRequest | None = None,
        *,
        event_id: str | None = None,
    ) -> Page[OpportunitySummaryResponse]:
        values = tuple(
            item
            for item in self._source.opportunities()
            if event_id is None or item.event_id == event_id
        )
        return _page(values, page or PageRequest())

    def opportunity(self, opportunity_id: str) -> OpportunityDetailResponse | None:
        if not opportunity_id.strip():
            raise ValueError("opportunity_id must not be empty")
        return self._source.opportunity(opportunity_id)

    def configuration(self) -> ConfigurationStatusResponse:
        return ConfigurationStatusResponse(
            scanner_only=True,
            authentication_required=self._security.authentication_enabled,
            rate_limiting_enabled=self._security.rate_limiting_enabled,
        )

    def metrics(self) -> MetricsResponse:
        return MetricsResponse(values=dict(self._source.metrics()))


def _page(values: Sequence[T], request: PageRequest) -> Page[T]:
    items = tuple(values)
    start = request.offset
    end = start + request.limit
    return Page(items=items[start:end], offset=start, limit=request.limit, total=len(items))
