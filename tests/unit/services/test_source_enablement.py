from arbiscan.domain import ProviderId
from arbiscan.providers.synthetic import build_phase5_synthetic_scenario
from arbiscan.services import TransportSourceEnablementPolicy


def test_primary_only_policy_selects_exactly_one_configured_transport() -> None:
    scenario = build_phase5_synthetic_scenario()
    primary = scenario.adapters[0]

    policy = TransportSourceEnablementPolicy.primary_only(primary.provider.id)
    selected = policy.select(tuple(reversed(scenario.adapters)))

    assert selected == (primary,)
    assert policy.required_provider_ids == frozenset({primary.provider.id})


def test_staged_multi_source_policy_selects_enabled_transports_deterministically() -> None:
    scenario = build_phase5_synthetic_scenario()
    provider_ids = frozenset(adapter.provider.id for adapter in scenario.adapters)
    primary_id = scenario.adapters[0].provider.id
    additional = provider_ids - {primary_id}

    policy = TransportSourceEnablementPolicy.staged_multi_source(
        primary_provider_id=primary_id,
        additional_provider_ids=frozenset(additional),
    )
    selected = policy.select(tuple(reversed(scenario.adapters)))

    assert tuple(adapter.provider.id for adapter in selected) == tuple(
        sorted(provider_ids, key=lambda value: value.value)
    )
    assert policy.required_provider_ids == frozenset({primary_id})


def test_enablement_policy_fails_closed_for_unknown_enabled_transport() -> None:
    scenario = build_phase5_synthetic_scenario()
    unknown = ProviderId("provider:not-configured")
    policy = TransportSourceEnablementPolicy(
        enabled_provider_ids=frozenset({unknown}),
    )

    try:
        policy.select(scenario.adapters)
    except ValueError as exc:
        assert "enabled transport sources are not configured" in str(exc)
    else:
        raise AssertionError("unknown enabled transport must fail closed")


def test_enablement_policy_rejects_disabling_required_transport() -> None:
    required = ProviderId("provider:required")

    try:
        TransportSourceEnablementPolicy(
            enabled_provider_ids=frozenset(),
            required_provider_ids=frozenset({required}),
        )
    except ValueError as exc:
        assert "required transport sources are not enabled" in str(exc)
    else:
        raise AssertionError("required source must remain enabled")


def test_enablement_policy_rejects_duplicate_configured_transport_identity() -> None:
    scenario = build_phase5_synthetic_scenario()
    adapter = scenario.adapters[0]
    policy = TransportSourceEnablementPolicy.primary_only(adapter.provider.id)

    try:
        policy.select((adapter, adapter))
    except ValueError as exc:
        assert "duplicate configured transport provider" in str(exc)
    else:
        raise AssertionError("duplicate configured provider identity must fail closed")
