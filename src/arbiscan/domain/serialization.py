"""Versioned, deterministic JSON serialization for canonical domain snapshots.

The codec is intentionally restricted to a closed registry of ArbiScan domain
classes. It does not import or instantiate arbitrary types named by input data.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from inspect import signature
from typing import cast

from arbiscan.domain.enums import (
    EventStatus,
    MarketKind,
    MarketPeriod,
    OpportunityStatus,
    ParticipantKind,
    ProviderKind,
    QuoteStatus,
    SelectionKind,
    Sport,
)
from arbiscan.domain.errors import DomainValidationError
from arbiscan.domain.identifiers import (
    CompetitionId,
    EventId,
    MarketId,
    OpportunityId,
    ParticipantId,
    ProviderId,
    QuoteId,
    SelectionId,
    StakePlanId,
)
from arbiscan.domain.models import (
    Competition,
    Event,
    Market,
    OddsQuote,
    Opportunity,
    Participant,
    Provider,
    ProviderEventReference,
    ProviderMarketReference,
    Selection,
    StakeAllocation,
    StakePlan,
)

SCHEMA_VERSION = 1

_MODEL_TYPES: dict[str, Callable[..., object]] = {
    type_.__name__: type_
    for type_ in (
        CompetitionId,
        ParticipantId,
        EventId,
        MarketId,
        SelectionId,
        QuoteId,
        ProviderId,
        OpportunityId,
        StakePlanId,
        Provider,
        Competition,
        Participant,
        ProviderEventReference,
        ProviderMarketReference,
        Event,
        Market,
        Selection,
        OddsQuote,
        Opportunity,
        StakeAllocation,
        StakePlan,
    )
}

_ENUM_TYPES: dict[str, type[StrEnum]] = {
    type_.__name__: type_
    for type_ in (
        Sport,
        ParticipantKind,
        EventStatus,
        MarketKind,
        MarketPeriod,
        SelectionKind,
        QuoteStatus,
        ProviderKind,
        OpportunityStatus,
    )
}


def _encode(value: object) -> object:
    # StrEnum must be handled before str because StrEnum subclasses str.
    if isinstance(value, StrEnum):
        return {"$enum": type(value).__name__, "value": value.value}
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, tuple):
        return {"$tuple": [_encode(item) for item in value]}
    if is_dataclass(value) and not isinstance(value, type):
        payload: dict[str, object] = {"$type": type(value).__name__}
        for dataclass_field in fields(value):
            payload[dataclass_field.name] = _encode(getattr(value, dataclass_field.name))
        return payload
    raise TypeError(f"unsupported canonical serialization type: {type(value).__name__}")


def _string_field(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise DomainValidationError(f"serialized field {key!r} must be a string")
    return value


def _require_exact_keys(
    mapping: dict[str, object],
    expected: set[str],
    *,
    context: str,
) -> None:
    actual = set(mapping)
    if actual == expected:
        return

    details: list[str] = []
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        details.append(f"missing fields: {', '.join(missing)}")
    if unexpected:
        details.append(f"unexpected fields: {', '.join(unexpected)}")
    raise DomainValidationError(f"{context} has invalid fields ({'; '.join(details)})")


def _decode(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if not isinstance(value, dict):
        raise DomainValidationError("serialized canonical value has an unsupported JSON type")

    if not all(isinstance(key, str) for key in value):
        raise DomainValidationError("serialized canonical object keys must be strings")
    mapping = cast(dict[str, object], value)

    if "$decimal" in mapping:
        _require_exact_keys(mapping, {"$decimal"}, context="serialized Decimal")
        try:
            return Decimal(_string_field(mapping, "$decimal"))
        except Exception as exc:
            raise DomainValidationError("invalid serialized Decimal") from exc

    if "$datetime" in mapping:
        _require_exact_keys(mapping, {"$datetime"}, context="serialized datetime")
        raw = _string_field(mapping, "$datetime")
        try:
            return datetime.fromisoformat(raw)
        except ValueError as exc:
            raise DomainValidationError("invalid serialized datetime") from exc

    if "$enum" in mapping:
        _require_exact_keys(mapping, {"$enum", "value"}, context="serialized enum")
        enum_name = _string_field(mapping, "$enum")
        enum_type = _ENUM_TYPES.get(enum_name)
        if enum_type is None:
            raise DomainValidationError(f"unknown serialized enum type: {enum_name}")
        try:
            return enum_type(_string_field(mapping, "value"))
        except ValueError as exc:
            raise DomainValidationError(f"invalid value for serialized enum {enum_name}") from exc

    if "$tuple" in mapping:
        _require_exact_keys(mapping, {"$tuple"}, context="serialized tuple")
        items = mapping["$tuple"]
        if not isinstance(items, list):
            raise DomainValidationError("serialized tuple payload must be a list")
        return tuple(_decode(item) for item in items)

    if "$type" in mapping:
        type_name = _string_field(mapping, "$type")
        factory = _MODEL_TYPES.get(type_name)
        if factory is None:
            raise DomainValidationError(f"unknown serialized domain type: {type_name}")

        expected_fields = set(signature(factory).parameters)
        actual_fields = set(mapping) - {"$type"}
        if actual_fields != expected_fields:
            details: list[str] = []
            missing = sorted(expected_fields - actual_fields)
            unexpected = sorted(actual_fields - expected_fields)
            if missing:
                details.append(f"missing fields: {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected fields: {', '.join(unexpected)}")
            raise DomainValidationError(
                f"serialized payload for {type_name} has invalid fields ({'; '.join(details)})"
            )

        kwargs = {key: _decode(mapping[key]) for key in expected_fields}
        try:
            return factory(**kwargs)
        except (TypeError, ValueError) as exc:
            raise DomainValidationError(f"invalid serialized payload for {type_name}") from exc

    raise DomainValidationError("serialized canonical object has no recognized type tag")


def dumps(value: object) -> str:
    """Serialize one canonical domain object into deterministic JSON."""
    envelope = {"schema_version": SCHEMA_VERSION, "payload": _encode(value)}
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def loads[T](data: str, expected_type: type[T]) -> T:
    """Deserialize canonical JSON and require the expected root type."""
    try:
        parsed = cast(object, json.loads(data))
    except json.JSONDecodeError as exc:
        raise DomainValidationError("invalid canonical JSON") from exc

    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise DomainValidationError("canonical JSON root must be an object")
    envelope = cast(dict[str, object], parsed)
    _require_exact_keys(
        envelope,
        {"schema_version", "payload"},
        context="canonical JSON envelope",
    )

    if envelope["schema_version"] != SCHEMA_VERSION:
        raise DomainValidationError("unsupported canonical schema version")

    result = _decode(envelope["payload"])
    if not isinstance(result, expected_type):
        raise DomainValidationError(
            f"expected {expected_type.__name__}, got {type(result).__name__}"
        )
    return result
