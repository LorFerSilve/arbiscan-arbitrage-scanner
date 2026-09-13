"""Shared timeout, retry, backoff, and error-normalization policy for providers."""

from __future__ import annotations

import asyncio
import math
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.errors import (
    ProviderContractError,
    ProviderError,
    ProviderErrorKind,
)
from arbiscan.providers.models import ProviderOperation

T = TypeVar("T")
Sleep = Callable[[float], Awaitable[None]]
RandomSample = Callable[[], float]


@dataclass(frozen=True, slots=True)
class ProviderCallPolicy:
    """Bounded per-attempt timeout and exponential retry policy."""

    timeout_seconds: float = 5.0
    max_attempts: int = 3
    base_backoff_seconds: float = 0.25
    max_backoff_seconds: float = 4.0
    jitter_ratio: float = 0.20

    def __post_init__(self) -> None:
        numeric_values = {
            "timeout_seconds": self.timeout_seconds,
            "base_backoff_seconds": self.base_backoff_seconds,
            "max_backoff_seconds": self.max_backoff_seconds,
            "jitter_ratio": self.jitter_ratio,
        }
        for name, value in numeric_values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProviderContractError(f"{name} must be numeric")
            if not math.isfinite(float(value)):
                raise ProviderContractError(f"{name} must be finite")
        if self.timeout_seconds <= 0:
            raise ProviderContractError("timeout_seconds must be greater than zero")
        if type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ProviderContractError("max_attempts must be an integer >= 1")
        if self.base_backoff_seconds < 0:
            raise ProviderContractError("base_backoff_seconds cannot be negative")
        if self.max_backoff_seconds < self.base_backoff_seconds:
            raise ProviderContractError("max_backoff_seconds cannot be below base_backoff_seconds")
        if not 0 <= self.jitter_ratio <= 1:
            raise ProviderContractError("jitter_ratio must be between zero and one")


class ProviderExecutor:
    """Execute adapter calls under one bounded resilience and error policy."""

    def __init__(
        self,
        adapter: ProviderAdapter,
        *,
        policy: ProviderCallPolicy | None = None,
        sleep: Sleep = asyncio.sleep,
        random_sample: RandomSample = random.random,
    ) -> None:
        if not isinstance(adapter, ProviderAdapter):
            raise ProviderContractError("adapter must implement ProviderAdapter")
        self._adapter = adapter
        self._policy = policy or ProviderCallPolicy()
        self._sleep = sleep
        self._random_sample = random_sample

    async def run(
        self,
        operation: ProviderOperation,
        call: Callable[[], Awaitable[T]],
    ) -> T:
        """Run a fresh call per attempt while propagating task cancellation unchanged."""
        if not isinstance(operation, ProviderOperation):
            raise ProviderContractError("operation must be ProviderOperation")

        last_error: ProviderError | None = None
        for attempt in range(1, self._policy.max_attempts + 1):
            try:
                async with asyncio.timeout(self._policy.timeout_seconds):
                    return await call()
            except TimeoutError:
                error = ProviderError(
                    provider_id=self._adapter.provider.id,
                    operation=operation.value,
                    kind=ProviderErrorKind.TIMEOUT,
                    message=f"provider operation timed out: {operation.value}",
                    retryable=True,
                )
            except ProviderError as exc:
                if exc.provider_id != self._adapter.provider.id:
                    error = ProviderError(
                        provider_id=self._adapter.provider.id,
                        operation=operation.value,
                        kind=ProviderErrorKind.INTERNAL,
                        message="adapter raised ProviderError for a different provider",
                        retryable=False,
                    )
                else:
                    error = exc
            except Exception as exc:
                raise ProviderError(
                    provider_id=self._adapter.provider.id,
                    operation=operation.value,
                    kind=ProviderErrorKind.INTERNAL,
                    message=f"untranslated adapter exception: {type(exc).__name__}",
                    retryable=False,
                ) from exc

            last_error = error
            if not error.retryable or attempt >= self._policy.max_attempts:
                raise error
            await self._sleep(self._retry_delay(attempt, error))

        if last_error is None:
            raise ProviderContractError("provider executor reached an impossible state")
        raise last_error

    def _retry_delay(self, attempt: int, error: ProviderError) -> float:
        exponential = min(
            self._policy.max_backoff_seconds,
            self._policy.base_backoff_seconds * (2 ** (attempt - 1)),
        )
        sample = self._random_sample()
        if not isinstance(sample, (int, float)) or isinstance(sample, bool):
            raise ProviderContractError("random_sample must return a numeric value")
        if not math.isfinite(float(sample)) or not 0 <= sample <= 1:
            raise ProviderContractError("random_sample must return a finite value in [0, 1]")

        jittered = exponential + exponential * self._policy.jitter_ratio * float(sample)
        delay = min(self._policy.max_backoff_seconds, jittered)
        if error.retry_after is not None:
            delay = max(delay, error.retry_after.total_seconds())
        return float(delay)
