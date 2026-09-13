"""Small injectable HTTP boundary used by real provider adapters.

The standard-library implementation intentionally keeps transport concerns out of
provider parsers and tests. Tests should inject a deterministic transport rather
than performing network I/O.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from arbiscan.providers.errors import ProviderContractError


class HttpTransportError(RuntimeError):
    """Network/transport failure without request URL or credentials."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Minimal immutable HTTP response consumed by provider adapters."""

    status_code: int
    headers: Mapping[str, str]
    body: bytes

    def __post_init__(self) -> None:
        if type(self.status_code) is not int or not 100 <= self.status_code <= 599:
            raise ProviderContractError("http response status_code must be in [100, 599]")
        if not isinstance(self.body, bytes):
            raise ProviderContractError("http response body must be bytes")
        normalized: dict[str, str] = {}
        for key, value in self.headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ProviderContractError("http response headers must be text mappings")
            normalized[key.strip().casefold()] = value.strip()
        object.__setattr__(self, "headers", MappingProxyType(normalized))


class AsyncHttpTransport(Protocol):
    """Async GET transport contract for provider implementations."""

    async def get(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse: ...


class UrllibAsyncHttpTransport:
    """Dependency-free HTTPS transport using a worker thread for blocking urllib I/O."""

    async def get(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        return await asyncio.to_thread(
            self._get_sync,
            url=url,
            query=dict(query),
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _get_sync(
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        if not isinstance(url, str) or not url.startswith("https://"):
            raise HttpTransportError("provider transport requires an HTTPS URL")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise HttpTransportError("provider transport timeout must be numeric")
        if timeout_seconds <= 0:
            raise HttpTransportError("provider transport timeout must be positive")

        encoded = urlencode(tuple(query.items()))
        request = Request(
            f"{url}?{encoded}" if encoded else url,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": "ArbiScan/0.1"},
        )
        try:
            with urlopen(request, timeout=float(timeout_seconds)) as response:
                return HttpResponse(
                    status_code=int(response.status),
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except HTTPError as exc:
            return HttpResponse(
                status_code=exc.code,
                headers=dict(exc.headers.items()) if exc.headers is not None else {},
                body=exc.read(),
            )
        except (URLError, TimeoutError, OSError) as exc:
            raise HttpTransportError(f"provider transport failed: {type(exc).__name__}") from exc
