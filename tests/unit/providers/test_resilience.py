"""Timeout, retry, rate-limit, and cancellation tests for provider execution."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import timedelta

from arbiscan.domain import Provider, ProviderId, ProviderKind, Sport
from arbiscan.providers import (
    FakeProvider,
    FakeProviderFixtures,
    ProviderCallPolicy,
    ProviderError,
    ProviderErrorKind,
    ProviderExecutor,
    ProviderOperation,
)

PROVIDER_ID = ProviderId("provider:resilience")


def make_provider(
    *,
    failures: tuple[ProviderError, ...] = (),
    delay: float = 0.0,
) -> FakeProvider:
    provider = Provider(
        id=PROVIDER_ID,
        name="Resilience Fake",
        kind=ProviderKind.SYNTHETIC,
    )
    return FakeProvider(
        provider=provider,
        fixtures=FakeProviderFixtures(sports=(Sport.FOOTBALL,)),
        scripted_failures=({ProviderOperation.SUPPORTED_SPORTS: failures} if failures else None),
        operation_delays=({ProviderOperation.SUPPORTED_SPORTS: delay} if delay > 0 else None),
    )


def run(coro: Awaitable[object]) -> object:
    return asyncio.run(coro)


def test_retryable_failure_is_retried_with_bounded_backoff() -> None:
    failure = ProviderError(
        provider_id=PROVIDER_ID,
        operation=ProviderOperation.SUPPORTED_SPORTS.value,
        kind=ProviderErrorKind.TRANSPORT,
        message="temporary connection reset",
        retryable=True,
    )
    provider = make_provider(failures=(failure,))
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    executor = ProviderExecutor(
        provider,
        policy=ProviderCallPolicy(
            timeout_seconds=1.0,
            max_attempts=2,
            base_backoff_seconds=0.1,
            max_backoff_seconds=1.0,
            jitter_ratio=0.0,
        ),
        sleep=sleep,
        random_sample=lambda: 0.5,
    )
    result = run(
        executor.run(
            ProviderOperation.SUPPORTED_SPORTS,
            provider.supported_sports,
        )
    )
    assert result == (Sport.FOOTBALL,)
    assert delays == [0.1]


def test_retry_after_overrides_shorter_exponential_delay() -> None:
    failure = ProviderError(
        provider_id=PROVIDER_ID,
        operation=ProviderOperation.SUPPORTED_SPORTS.value,
        kind=ProviderErrorKind.RATE_LIMITED,
        message="quota exhausted",
        retryable=True,
        retry_after=timedelta(seconds=0.75),
    )
    provider = make_provider(failures=(failure,))
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    executor = ProviderExecutor(
        provider,
        policy=ProviderCallPolicy(
            timeout_seconds=1.0,
            max_attempts=2,
            base_backoff_seconds=0.1,
            max_backoff_seconds=1.0,
            jitter_ratio=0.0,
        ),
        sleep=sleep,
        random_sample=lambda: 0.0,
    )
    result = run(
        executor.run(
            ProviderOperation.SUPPORTED_SPORTS,
            provider.supported_sports,
        )
    )
    assert result == (Sport.FOOTBALL,)
    assert delays == [0.75]


def test_timeout_is_exposed_as_generic_retryable_provider_error() -> None:
    provider = make_provider(delay=0.05)
    executor = ProviderExecutor(
        provider,
        policy=ProviderCallPolicy(timeout_seconds=0.001, max_attempts=1),
    )

    async def scenario() -> None:
        try:
            await executor.run(
                ProviderOperation.SUPPORTED_SPORTS,
                provider.supported_sports,
            )
        except ProviderError as exc:
            assert exc.kind is ProviderErrorKind.TIMEOUT
            assert exc.retryable
            return
        raise AssertionError("expected ProviderError")

    run(scenario())


def test_non_retryable_failure_does_not_sleep_or_mutate_fixtures() -> None:
    failure = ProviderError(
        provider_id=PROVIDER_ID,
        operation=ProviderOperation.SUPPORTED_SPORTS.value,
        kind=ProviderErrorKind.AUTHENTICATION,
        message="bad credential",
        retryable=False,
    )
    provider = make_provider(failures=(failure,))
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    executor = ProviderExecutor(provider, sleep=sleep)

    async def scenario() -> None:
        try:
            await executor.run(
                ProviderOperation.SUPPORTED_SPORTS,
                provider.supported_sports,
            )
        except ProviderError as exc:
            assert exc.kind is ProviderErrorKind.AUTHENTICATION
        else:
            raise AssertionError("expected ProviderError")
        assert await provider.supported_sports() == (Sport.FOOTBALL,)

    run(scenario())
    assert delays == []


def test_task_cancellation_propagates_without_translation() -> None:
    provider = make_provider(delay=10.0)
    executor = ProviderExecutor(
        provider,
        policy=ProviderCallPolicy(timeout_seconds=30.0, max_attempts=1),
    )

    async def scenario() -> None:
        task = asyncio.create_task(
            executor.run(
                ProviderOperation.SUPPORTED_SPORTS,
                provider.supported_sports,
            )
        )
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return
        raise AssertionError("task cancellation must propagate")

    run(scenario())
