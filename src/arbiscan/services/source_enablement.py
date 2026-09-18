"""Provider-neutral transport-source enablement policy for staged rollouts."""

from __future__ import annotations

from dataclasses import dataclass, field

from arbiscan.domain import ProviderId
from arbiscan.providers.contract import ProviderAdapter


@dataclass(frozen=True, slots=True)
class TransportSourceEnablementPolicy:
    """Select transport adapters explicitly before a realtime scanner can poll them.

    The policy is intentionally provider-neutral. A configured adapter is not polled
    unless its transport-provider ID is present in enabled_provider_ids. Optional
    required_provider_ids make rollback/primary-source invariants explicit.
    """

    enabled_provider_ids: frozenset[ProviderId]
    required_provider_ids: frozenset[ProviderId] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        enabled = frozenset(self.enabled_provider_ids)
        required = frozenset(self.required_provider_ids)
        if any(not isinstance(value, ProviderId) for value in enabled | required):
            raise ValueError("source enablement IDs must be ProviderId values")
        missing_required = required - enabled
        if missing_required:
            values = ", ".join(sorted(value.value for value in missing_required))
            raise ValueError(f"required transport sources are not enabled: {values}")
        object.__setattr__(self, "enabled_provider_ids", enabled)
        object.__setattr__(self, "required_provider_ids", required)

    @classmethod
    def primary_only(cls, provider_id: ProviderId) -> TransportSourceEnablementPolicy:
        """Build a fail-closed single-source rollout policy."""
        if not isinstance(provider_id, ProviderId):
            raise ValueError("provider_id must be ProviderId")
        return cls(
            enabled_provider_ids=frozenset({provider_id}),
            required_provider_ids=frozenset({provider_id}),
        )

    @classmethod
    def staged_multi_source(
        cls,
        *,
        primary_provider_id: ProviderId,
        additional_provider_ids: frozenset[ProviderId],
    ) -> TransportSourceEnablementPolicy:
        """Build an explicit multi-source policy while retaining the primary source."""
        if not isinstance(primary_provider_id, ProviderId):
            raise ValueError("primary_provider_id must be ProviderId")
        if any(not isinstance(value, ProviderId) for value in additional_provider_ids):
            raise ValueError("additional_provider_ids must contain ProviderId values")
        return cls(
            enabled_provider_ids=frozenset({primary_provider_id}) | additional_provider_ids,
            required_provider_ids=frozenset({primary_provider_id}),
        )

    def select(
        self,
        adapters: tuple[ProviderAdapter, ...],
    ) -> tuple[ProviderAdapter, ...]:
        """Return enabled adapters deterministically and fail closed on bad config."""
        if any(not isinstance(adapter, ProviderAdapter) for adapter in adapters):
            raise ValueError("adapters must contain ProviderAdapter values")

        by_provider: dict[ProviderId, ProviderAdapter] = {}
        for adapter in adapters:
            provider_id = adapter.provider.id
            if provider_id in by_provider:
                raise ValueError(f"duplicate configured transport provider: {provider_id.value}")
            by_provider[provider_id] = adapter

        unknown_enabled = self.enabled_provider_ids - set(by_provider)
        if unknown_enabled:
            values = ", ".join(sorted(value.value for value in unknown_enabled))
            raise ValueError(f"enabled transport sources are not configured: {values}")

        unknown_required = self.required_provider_ids - set(by_provider)
        if unknown_required:
            values = ", ".join(sorted(value.value for value in unknown_required))
            raise ValueError(f"required transport sources are not configured: {values}")

        return tuple(
            by_provider[provider_id]
            for provider_id in sorted(
                self.enabled_provider_ids,
                key=lambda value: value.value,
            )
        )
