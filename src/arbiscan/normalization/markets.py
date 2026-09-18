"""Deterministic normalization of provider market terminology into canonical semantics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from arbiscan.domain import MarketKind, MarketPeriod, ProviderId, Sport
from arbiscan.normalization.resolution import Resolution
from arbiscan.normalization.text import normalize_alias_key

_PARAMETERIZED = {MarketKind.TOTAL_POINTS, MarketKind.HANDICAP}
_INDEXED_PERIODS = {
    MarketPeriod.SET,
    MarketPeriod.GAME,
    MarketPeriod.PERIOD,
    MarketPeriod.QUARTER,
}


@dataclass(frozen=True, slots=True)
class MarketSemantic:
    """Canonical market meaning without event-specific identity."""

    kind: MarketKind
    period: MarketPeriod
    line: Decimal | None = None
    period_index: int | None = None
    set_index: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, MarketKind):
            raise ValueError("market semantic kind must be MarketKind")
        if not isinstance(self.period, MarketPeriod):
            raise ValueError("market semantic period must be MarketPeriod")
        if self.line is not None and (
            not isinstance(self.line, Decimal) or not self.line.is_finite()
        ):
            raise ValueError("market semantic line must be a finite Decimal")
        if self.kind in _PARAMETERIZED and self.line is None:
            raise ValueError(f"{self.kind.value} requires a line")
        if self.kind not in _PARAMETERIZED and self.line is not None:
            raise ValueError(f"{self.kind.value} does not accept a line")
        if self.period_index is not None and type(self.period_index) is not int:
            raise ValueError("market semantic period_index must be int")
        if self.period in _INDEXED_PERIODS:
            if self.period_index is None or self.period_index < 1:
                raise ValueError("indexed periods require period_index >= 1")
        elif self.period_index is not None:
            raise ValueError("period_index is only valid for indexed periods")
        if self.set_index is not None and type(self.set_index) is not int:
            raise ValueError("market semantic set_index must be int")
        if self.period is MarketPeriod.GAME:
            if self.set_index is None or self.set_index < 1:
                raise ValueError("game periods require set_index >= 1")
        elif self.set_index is not None:
            raise ValueError("set_index is only valid for game periods")
        if self.kind is MarketKind.SET_WINNER and self.period is not MarketPeriod.SET:
            raise ValueError("set winner must use set period")
        if self.kind is MarketKind.GAME_WINNER and self.period is not MarketPeriod.GAME:
            raise ValueError("game winner must use game period")


@dataclass(frozen=True, slots=True)
class MarketAlias:
    """One explicit source market alias and its canonical template."""

    alias: str
    sport: Sport
    kind: MarketKind
    period: MarketPeriod
    provider_id: ProviderId | None = None
    requires_line: bool = False
    requires_period_index: bool = False
    requires_set_index: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "alias", normalize_alias_key(self.alias, field_name="market alias")
        )
        if not isinstance(self.sport, Sport):
            raise ValueError("market alias sport must be Sport")
        if not isinstance(self.kind, MarketKind):
            raise ValueError("market alias kind must be MarketKind")
        if not isinstance(self.period, MarketPeriod):
            raise ValueError("market alias period must be MarketPeriod")
        if self.provider_id is not None and not isinstance(self.provider_id, ProviderId):
            raise ValueError("market alias provider_id must be ProviderId")
        if (
            type(self.requires_line) is not bool
            or type(self.requires_period_index) is not bool
            or type(self.requires_set_index) is not bool
        ):
            raise ValueError("market alias requirement flags must be bool")
        if self.requires_line != (self.kind in _PARAMETERIZED):
            raise ValueError("parameterized market aliases must require line exactly")
        if self.requires_period_index != (self.period in _INDEXED_PERIODS):
            raise ValueError("indexed market periods must require period_index exactly")
        if self.requires_set_index != (self.period is MarketPeriod.GAME):
            raise ValueError("game market periods must require set_index exactly")


@dataclass(frozen=True, slots=True)
class MarketNormalizer:
    entries: tuple[MarketAlias, ...]

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        if any(not isinstance(entry, MarketAlias) for entry in entries):
            raise ValueError("market normalizer entries must be MarketAlias values")
        object.__setattr__(self, "entries", entries)

    def resolve(
        self,
        alias: str,
        *,
        sport: Sport,
        provider_id: ProviderId | None = None,
        line: str | Decimal | None = None,
        period_index: int | None = None,
        set_index: int | None = None,
    ) -> Resolution[MarketSemantic]:
        key = normalize_alias_key(alias, field_name="market alias")
        if not isinstance(sport, Sport):
            raise ValueError("sport must be Sport")
        if provider_id is not None and not isinstance(provider_id, ProviderId):
            raise ValueError("provider_id must be ProviderId")

        exact = tuple(
            entry for entry in self.entries if entry.alias == key and entry.sport is sport
        )
        if provider_id is not None:
            provider_specific = tuple(entry for entry in exact if entry.provider_id == provider_id)
            matches = provider_specific or tuple(
                entry for entry in exact if entry.provider_id is None
            )
        else:
            matches = tuple(entry for entry in exact if entry.provider_id is None)

        if not matches:
            if (
                exact
                and provider_id is None
                and any(entry.provider_id is not None for entry in exact)
            ):
                return Resolution.unknown(detail="market alias requires provider context")
            return Resolution.unknown(detail="unknown market alias")

        normalized_line: Decimal | None
        try:
            normalized_line = _normalize_line(line)
        except ValueError as exc:
            return Resolution.unknown(detail=str(exc))

        semantics: set[MarketSemantic] = set()
        missing_context = False
        for entry in matches:
            if entry.requires_line and normalized_line is None:
                missing_context = True
                continue
            if not entry.requires_line and normalized_line is not None:
                continue
            if entry.requires_period_index and period_index is None:
                missing_context = True
                continue
            if not entry.requires_period_index and period_index is not None:
                continue
            if entry.requires_set_index and set_index is None:
                missing_context = True
                continue
            if not entry.requires_set_index and set_index is not None:
                continue
            try:
                semantics.add(
                    MarketSemantic(
                        kind=entry.kind,
                        period=entry.period,
                        line=normalized_line,
                        period_index=period_index,
                        set_index=set_index,
                    )
                )
            except ValueError:
                continue

        ordered = tuple(
            sorted(
                semantics,
                key=lambda value: (
                    value.kind.value,
                    value.period.value,
                    "" if value.line is None else str(value.line),
                    value.period_index or 0,
                    value.set_index or 0,
                ),
            )
        )
        if len(ordered) == 1:
            return Resolution.resolved(ordered[0], detail="explicit market semantic alias")
        if len(ordered) > 1:
            return Resolution.ambiguous(ordered, detail="market alias maps to multiple semantics")
        if missing_context:
            return Resolution.unknown(detail="market alias requires additional structured context")
        return Resolution.unknown(
            detail="market alias conflicts with supplied line or period context"
        )


def _normalize_line(value: str | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValueError("market line must be numeric") from exc
    else:
        raise ValueError("market line must be Decimal or numeric text")
    if not parsed.is_finite():
        raise ValueError("market line must be finite")
    return parsed
