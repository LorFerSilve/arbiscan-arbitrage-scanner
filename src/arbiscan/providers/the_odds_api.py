"""The Odds API V4 adapter used as ArbiScan's first real odds-data integration."""

from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator, Callable, Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from urllib.parse import quote

from arbiscan.domain import Provider, ProviderId, ProviderKind, Sport
from arbiscan.observability.provider import (
    NullProviderTelemetry,
    ProviderTelemetryEvent,
    ProviderTelemetryOutcome,
    ProviderTelemetrySink,
)
from arbiscan.providers.contract import ProviderAdapter
from arbiscan.providers.errors import ProviderContractError, ProviderError, ProviderErrorKind
from arbiscan.providers.http import (
    AsyncHttpTransport,
    HttpResponse,
    HttpTransportError,
    UrllibAsyncHttpTransport,
)
from arbiscan.providers.models import (
    CanonicalIdHooks,
    OddsSnapshot,
    ProviderCapabilities,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthState,
    ProviderOperation,
    RateLimitSnapshot,
    SourceCompetition,
    SourceEvent,
    SourceMarket,
    SourceOddsFormat,
    SourceParticipant,
    SourceSelectionQuote,
)

THE_ODDS_API_PROVIDER_ID = ProviderId("provider:the-odds-api")
THE_ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"

Clock = Callable[[], datetime]


class _SchemaError(ValueError):
    """Internal payload-schema error translated at the adapter boundary."""


@dataclass(frozen=True, slots=True)
class TheOddsApiConfig:
    """Runtime configuration for The Odds API without exposing its secret in repr."""

    api_key: str = field(repr=False, compare=False)
    base_url: str = THE_ODDS_API_BASE_URL
    regions: tuple[str, ...] = ("eu",)
    markets: tuple[str, ...] = ("h2h",)
    request_timeout_seconds: float = 10.0
    include_sids: bool = True
    basketball_full_event_bookmakers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ProviderContractError("The Odds API key must be non-empty text")
        object.__setattr__(self, "api_key", self.api_key.strip())
        if not isinstance(self.base_url, str) or not self.base_url.startswith("https://"):
            raise ProviderContractError("The Odds API base_url must use HTTPS")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

        if any(not isinstance(value, str) for value in self.regions):
            raise ProviderContractError("The Odds API regions must contain text values")
        if any(not isinstance(value, str) for value in self.markets):
            raise ProviderContractError("The Odds API markets must contain text values")
        regions = tuple(value.strip() for value in self.regions)
        markets = tuple(value.strip() for value in self.markets)
        if not regions or any(not value for value in regions) or len(set(regions)) != len(regions):
            raise ProviderContractError("The Odds API regions must be unique non-empty text")
        if not markets or any(not value for value in markets) or len(set(markets)) != len(markets):
            raise ProviderContractError("The Odds API markets must be unique non-empty text")
        object.__setattr__(self, "regions", regions)
        object.__setattr__(self, "markets", markets)

        if any(not isinstance(value, str) for value in self.basketball_full_event_bookmakers):
            raise ProviderContractError(
                "The Odds API basketball_full_event_bookmakers must contain text values"
            )
        basketball_bookmakers = tuple(
            value.strip().casefold() for value in self.basketball_full_event_bookmakers
        )
        if any(not value for value in basketball_bookmakers) or len(
            set(basketball_bookmakers)
        ) != len(basketball_bookmakers):
            raise ProviderContractError(
                "The Odds API basketball_full_event_bookmakers must be unique non-empty text"
            )
        object.__setattr__(
            self,
            "basketball_full_event_bookmakers",
            basketball_bookmakers,
        )

        timeout = self.request_timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ProviderContractError("The Odds API request timeout must be numeric")
        if not math.isfinite(float(timeout)) or timeout <= 0:
            raise ProviderContractError("The Odds API request timeout must be finite and positive")
        object.__setattr__(self, "request_timeout_seconds", float(timeout))
        if type(self.include_sids) is not bool:
            raise ProviderContractError("The Odds API include_sids must be bool")


@dataclass(frozen=True, slots=True)
class _SportRecord:
    key: str
    group: str
    title: str
    active: bool


_GROUP_TO_SPORT: Mapping[str, Sport] = MappingProxyType(
    {
        "Soccer": Sport.FOOTBALL,
        "Basketball": Sport.BASKETBALL,
        "Tennis": Sport.TENNIS,
        "Motor Sports": Sport.MOTORSPORT,
        "Motorsports": Sport.MOTORSPORT,
    }
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ProviderContractError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _mapping(value: object, *, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _SchemaError(f"{path} must be an object")
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise _SchemaError(f"{path} contains a non-text key")
        normalized[key] = item
    return normalized


def _sequence(value: object, *, path: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise _SchemaError(f"{path} must be an array")
    return tuple(value)


def _text(value: object, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _SchemaError(f"{path} must be non-empty text")
    return value.strip()


def _optional_text(value: object | None, *, path: str) -> str | None:
    if value is None:
        return None
    return _text(value, path=path)


def _boolean(value: object, *, path: str) -> bool:
    if type(value) is not bool:
        raise _SchemaError(f"{path} must be boolean")
    return value


def _timestamp(value: object, *, path: str) -> datetime:
    raw = _text(value, path=path)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _SchemaError(f"{path} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _SchemaError(f"{path} must include a timezone")
    return parsed.astimezone(UTC)


def _optional_timestamp(value: object | None, *, path: str) -> datetime | None:
    if value is None:
        return None
    return _timestamp(value, path=path)


def _price_text(value: object, *, path: str) -> str:
    if type(value) is not Decimal:
        raise _SchemaError(f"{path} must be numeric")
    if not value.is_finite():
        raise _SchemaError(f"{path} must be finite")
    return str(value)


def _optional_point(value: object | None, *, path: str) -> Decimal | None:
    if value is None:
        return None
    if type(value) is int:
        return Decimal(value)
    if type(value) is not Decimal:
        raise _SchemaError(f"{path} must be numeric")
    if not value.is_finite():
        raise _SchemaError(f"{path} must be finite")
    return value


def _header_int(headers: Mapping[str, str], name: str) -> int | None:
    raw = headers.get(name.casefold())
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _retry_after(headers: Mapping[str, str]) -> timedelta | None:
    seconds = _header_int(headers, "retry-after")
    return None if seconds is None else timedelta(seconds=seconds)


def _sport_records(payload: object) -> tuple[_SportRecord, ...]:
    records: list[_SportRecord] = []
    for index, raw in enumerate(_sequence(payload, path="sports")):
        item = _mapping(raw, path=f"sports[{index}]")
        records.append(
            _SportRecord(
                key=_text(item.get("key"), path=f"sports[{index}].key"),
                group=_text(item.get("group"), path=f"sports[{index}].group"),
                title=_text(item.get("title"), path=f"sports[{index}].title"),
                active=_boolean(item.get("active"), path=f"sports[{index}].active"),
            )
        )
    return tuple(records)


def _source_event(raw: object, *, competition: _SportRecord) -> SourceEvent:
    item = _mapping(raw, path="event")
    event_id = _text(item.get("id"), path="event.id")
    sport_key = _text(item.get("sport_key"), path="event.sport_key")
    if sport_key != competition.key:
        raise _SchemaError("event.sport_key does not match the requested competition")
    home = _text(item.get("home_team"), path="event.home_team")
    away = _text(item.get("away_team"), path="event.away_team")
    if home == away:
        raise _SchemaError("event home and away participants must differ")
    sport = _GROUP_TO_SPORT.get(competition.group)
    if sport is None:
        raise _SchemaError("event belongs to an unsupported canonical sport group")
    return SourceEvent(
        external_id=event_id,
        sport=sport,
        competition_external_id=competition.key,
        participants=(
            SourceParticipant(external_id=f"name:{home}", name=home, role="home"),
            SourceParticipant(external_id=f"name:{away}", name=away, role="away"),
        ),
        scheduled_start=_timestamp(item.get("commence_time"), path="event.commence_time"),
        source_status="unknown",
    )


def _selection_id(
    *,
    bookmaker_key: str,
    market_key: str,
    outcome: Mapping[str, object],
    index: int,
) -> str:
    sid = _optional_text(outcome.get("sid"), path=f"outcomes[{index}].sid")
    if sid is not None:
        return sid
    name = _text(outcome.get("name"), path=f"outcomes[{index}].name")
    description = _optional_text(
        outcome.get("description"),
        path=f"outcomes[{index}].description",
    )
    suffix = name if description is None else f"{description}:{name}"
    return f"{bookmaker_key}:{market_key}:{suffix}"


def _source_markets(
    payload: Mapping[str, object],
    *,
    event_id: str,
    basketball_full_event_bookmakers: Collection[str] = (),
) -> tuple[SourceMarket, ...]:
    markets: list[SourceMarket] = []
    sport_key = _text(payload.get("sport_key"), path="event.sport_key")
    home_team = _text(payload.get("home_team"), path="event.home_team")
    away_team = _text(payload.get("away_team"), path="event.away_team")
    if home_team == away_team:
        raise _SchemaError("event home and away participants must differ")
    bookmakers = _sequence(payload.get("bookmakers"), path="event.bookmakers")
    for bookmaker_index, raw_bookmaker in enumerate(bookmakers):
        bookmaker = _mapping(raw_bookmaker, path=f"bookmakers[{bookmaker_index}]")
        bookmaker_key = _text(
            bookmaker.get("key"),
            path=f"bookmakers[{bookmaker_index}].key",
        )
        bookmaker_title = _text(
            bookmaker.get("title"),
            path=f"bookmakers[{bookmaker_index}].title",
        )
        price_provider = Provider(
            id=ProviderId(f"bookmaker:the-odds-api:{bookmaker_key}"),
            name=bookmaker_title,
            kind=ProviderKind.BOOKMAKER,
        )
        bookmaker_markets = _sequence(
            bookmaker.get("markets"),
            path=f"bookmakers[{bookmaker_index}].markets",
        )
        for market_index, raw_market in enumerate(bookmaker_markets):
            market = _mapping(
                raw_market,
                path=f"bookmakers[{bookmaker_index}].markets[{market_index}]",
            )
            market_key = _text(
                market.get("key"),
                path=f"bookmakers[{bookmaker_index}].markets[{market_index}].key",
            )
            if (
                sport_key.startswith("basketball_")
                and market_key in {"spreads", "totals"}
                and bookmaker_key.casefold() not in basketball_full_event_bookmakers
            ):
                # The transport exposes the bookmaker's featured game market but does
                # not encode its overtime settlement rule. Only price origins with an
                # independently verified full-event rule may enter this canonical path.
                continue
            market_sid = _optional_text(
                market.get("sid"),
                path=f"bookmakers[{bookmaker_index}].markets[{market_index}].sid",
            )
            last_update = _optional_timestamp(
                market.get("last_update"),
                path=f"bookmakers[{bookmaker_index}].markets[{market_index}].last_update",
            )
            raw_outcomes = _sequence(
                market.get("outcomes"),
                path=f"bookmakers[{bookmaker_index}].markets[{market_index}].outcomes",
            )
            if not raw_outcomes:
                raise _SchemaError("market.outcomes must not be empty")
            selections: list[SourceSelectionQuote] = []
            points: list[Decimal | None] = []
            for outcome_index, raw_outcome in enumerate(raw_outcomes):
                outcome = _mapping(raw_outcome, path=f"outcomes[{outcome_index}]")
                point = _optional_point(
                    outcome.get("point"),
                    path=f"outcomes[{outcome_index}].point",
                )
                points.append(point)
                selections.append(
                    SourceSelectionQuote(
                        external_selection_id=_selection_id(
                            bookmaker_key=bookmaker_key,
                            market_key=market_key,
                            outcome=outcome,
                            index=outcome_index,
                        ),
                        label=_text(
                            outcome.get("name"),
                            path=f"outcomes[{outcome_index}].name",
                        ),
                        price=_price_text(
                            outcome.get("price"),
                            path=f"outcomes[{outcome_index}].price",
                        ),
                        odds_format=SourceOddsFormat.DECIMAL,
                        handicap=(
                            point
                            if market_key == "spreads"
                            else Decimal("0")
                            if market_key == "draw_no_bet"
                            else None
                        ),
                    )
                )

            market_line: Decimal | None = None
            period_index: int | None = None
            if market_key == "totals":
                if any(point is None for point in points):
                    raise _SchemaError("totals market outcomes require point")
                total_points = {point for point in points if point is not None}
                if len(total_points) != 1:
                    raise _SchemaError("totals market outcomes must share one point")
                total_labels = {selection.label.casefold() for selection in selections}
                if len(selections) != 2 or total_labels != {"over", "under"}:
                    raise _SchemaError(
                        "totals market must contain exactly one Over and one Under outcome"
                    )
                market_line = next(iter(total_points))
            elif market_key in {"h2h_s1", "h2h_s2"}:
                if not sport_key.startswith("tennis_"):
                    raise _SchemaError(f"{market_key} is only supported for tennis events")
                if any(point is not None for point in points):
                    raise _SchemaError(f"{market_key} market outcomes must not carry point")
                if len(selections) != 2:
                    raise _SchemaError(f"{market_key} market must contain exactly two outcomes")
                if {selection.label for selection in selections} != {
                    home_team,
                    away_team,
                }:
                    raise _SchemaError(
                        f"{market_key} market outcomes must match the event home and away participants"
                    )
                period_index = 1 if market_key == "h2h_s1" else 2
            elif market_key == "btts":
                if any(point is not None for point in points):
                    raise _SchemaError("btts market outcomes must not carry point")
                btts_labels = [selection.label.casefold() for selection in selections]
                if len(selections) != 2 or sorted(btts_labels) != ["no", "yes"]:
                    raise _SchemaError(
                        "btts market must contain exactly one Yes and one No outcome"
                    )
            elif market_key == "draw_no_bet":
                if any(point is not None for point in points):
                    raise _SchemaError("draw_no_bet market outcomes must not carry point")
                if len(selections) != 2:
                    raise _SchemaError("draw_no_bet market must contain exactly two outcomes")
                if {selection.label for selection in selections} != {home_team, away_team}:
                    raise _SchemaError(
                        "draw_no_bet market outcomes must match the event home and away participants"
                    )
                market_line = Decimal("0")
            elif market_key == "spreads":
                if any(point is None for point in points):
                    raise _SchemaError("spreads market outcomes require point")
                if len(selections) != 2:
                    raise _SchemaError("spreads market must contain exactly two outcomes")
                by_label = {selection.label: selection for selection in selections}
                if set(by_label) != {home_team, away_team}:
                    raise _SchemaError(
                        "spreads market outcomes must match the event home and away participants"
                    )
                home_handicap = by_label[home_team].handicap
                away_handicap = by_label[away_team].handicap
                if home_handicap is None or away_handicap is None:
                    raise _SchemaError("spreads market outcomes require handicap points")
                if home_handicap != -away_handicap:
                    raise _SchemaError(
                        "spreads market home and away handicap points must be exact opposites"
                    )
                market_line = home_handicap
            elif any(point is not None for point in points):
                raise _SchemaError(f"market {market_key!r} carries unsupported point semantics")

            markets.append(
                SourceMarket(
                    external_event_id=event_id,
                    external_market_id=f"{bookmaker_key}:{market_sid or market_key}",
                    label=f"{bookmaker_title} {market_key}",
                    selections=tuple(selections),
                    price_provider=price_provider,
                    source_timestamp=last_update,
                    line=market_line,
                    period_index=period_index,
                )
            )
    return tuple(markets)


class TheOddsApiProvider(ProviderAdapter):
    """Strict adapter for The Odds API V4.

    The adapter still requests decimal ``h2h`` data by default. Phase 17 preserves
    structured ``point`` parameters for explicitly configured totals/spreads.
    Basketball is discovered as a canonical sport; featured ``spreads`` and
    ``totals`` remain distinct from the provider's quarter/half market keys.
    Totals require an exact Over/Under pair; spreads require the event's exact home/away
    pair with opposite points and anchor ``SourceMarket.line`` to the home participant.
    Draw No Bet requires the exact event participant pair, carries no source point, and
    is represented canonically as the existing Asian-handicap-zero settlement shape.
    Tennis set moneylines use only the documented ``h2h_s1`` and ``h2h_s2``
    keys, require the event participant pair without point semantics, and preserve the
    set number as structured ``SourceMarket.period_index``.
    """

    def __init__(
        self,
        *,
        config: TheOddsApiConfig,
        transport: AsyncHttpTransport | None = None,
        telemetry: ProviderTelemetrySink | None = None,
        canonical_id_hooks: CanonicalIdHooks | None = None,
        clock: Clock = _utc_now,
    ) -> None:
        if not isinstance(config, TheOddsApiConfig):
            raise ProviderContractError("config must be TheOddsApiConfig")
        self._config = config
        self._transport = transport or UrllibAsyncHttpTransport()
        self._telemetry = telemetry or NullProviderTelemetry()
        self._canonical_id_hooks = canonical_id_hooks
        self._clock = clock
        self._provider = Provider(
            id=THE_ODDS_API_PROVIDER_ID,
            name="The Odds API",
            kind=ProviderKind.AGGREGATOR,
        )
        capabilities = {
            ProviderCapability.SPORT_DISCOVERY,
            ProviderCapability.COMPETITION_DISCOVERY,
            ProviderCapability.EVENT_DISCOVERY,
            ProviderCapability.ODDS_SNAPSHOTS,
            ProviderCapability.HEALTH,
            ProviderCapability.RATE_LIMIT_METADATA,
        }
        if canonical_id_hooks is not None:
            capabilities.add(ProviderCapability.CANONICAL_ID_HINTS)
        self._capabilities = ProviderCapabilities(frozenset(capabilities))
        self._event_competitions: dict[str, str] = {}
        self._last_rate_limit: RateLimitSnapshot | None = None

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    @property
    def canonical_id_hooks(self) -> CanonicalIdHooks | None:
        return self._canonical_id_hooks

    async def supported_sports(self) -> tuple[Sport, ...]:
        records = await self._load_sports(ProviderOperation.SUPPORTED_SPORTS)
        values = {
            _GROUP_TO_SPORT[record.group] for record in records if record.group in _GROUP_TO_SPORT
        }
        return tuple(sorted(values, key=lambda value: value.value))

    async def discover_competitions(self, sport: Sport) -> tuple[SourceCompetition, ...]:
        operation = ProviderOperation.DISCOVER_COMPETITIONS
        if not isinstance(sport, Sport):
            raise self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                "sport must be a canonical Sport",
            )

        payload, response = await self._request_json(operation, "/sports", {"all": "false"})
        try:
            records = _sport_records(payload)
            competitions = tuple(
                sorted(
                    (
                        SourceCompetition(
                            external_id=record.key,
                            sport=sport,
                            name=record.title,
                            region=record.group,
                        )
                        for record in records
                        if record.active and _GROUP_TO_SPORT.get(record.group) is sport
                    ),
                    key=lambda value: value.external_id,
                )
            )
        except (_SchemaError, ProviderContractError) as exc:
            raise self._validated_payload_error(operation, response, exc) from exc

        self._emit(
            operation,
            outcome=ProviderTelemetryOutcome.SUCCESS,
            response=response,
            item_count=len(competitions),
        )
        return competitions

    async def discover_events(
        self,
        competition_external_id: str,
        *,
        starts_after: datetime | None = None,
        starts_before: datetime | None = None,
    ) -> tuple[SourceEvent, ...]:
        operation = ProviderOperation.DISCOVER_EVENTS
        competition_id = self._request_text(
            competition_external_id,
            operation=operation,
            field_name="competition_external_id",
        )
        after = self._request_time(starts_after, operation=operation, field_name="starts_after")
        before = self._request_time(starts_before, operation=operation, field_name="starts_before")
        if after is not None and before is not None and after > before:
            raise self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                "starts_after cannot be later than starts_before",
            )

        records = await self._load_sports(operation, emit_success=False)
        competition = next((value for value in records if value.key == competition_id), None)
        if competition is None or _GROUP_TO_SPORT.get(competition.group) is None:
            raise self._error(
                operation,
                ProviderErrorKind.UNSUPPORTED,
                "competition is not available as a supported canonical sport",
            )

        query = {"dateFormat": "iso"}
        if after is not None:
            query["commenceTimeFrom"] = after.isoformat().replace("+00:00", "Z")
        if before is not None:
            query["commenceTimeTo"] = before.isoformat().replace("+00:00", "Z")
        payload, response = await self._request_json(
            operation,
            f"/sports/{quote(competition_id, safe='')}/events",
            query,
        )
        try:
            events = tuple(
                _source_event(value, competition=competition)
                for value in _sequence(payload, path="events")
            )
        except (_SchemaError, ProviderContractError) as exc:
            raise self._validated_payload_error(operation, response, exc) from exc

        for event in events:
            self._event_competitions[event.external_id] = competition_id
        ordered = tuple(
            sorted(events, key=lambda value: (value.scheduled_start, value.external_id))
        )
        self._emit(
            operation,
            outcome=ProviderTelemetryOutcome.SUCCESS,
            response=response,
            item_count=len(ordered),
        )
        return ordered

    async def fetch_odds(self, external_event_id: str) -> OddsSnapshot | None:
        operation = ProviderOperation.FETCH_ODDS
        event_id = self._request_text(
            external_event_id,
            operation=operation,
            field_name="external_event_id",
        )
        competition_id = self._event_competitions.get(event_id)
        if competition_id is None:
            raise self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                "event must be discovered before fetching event odds",
            )

        payload, response = await self._request_json(
            operation,
            f"/sports/{quote(competition_id, safe='')}/events/{quote(event_id, safe='')}/odds",
            {
                "regions": ",".join(self._config.regions),
                "markets": ",".join(self._config.markets),
                "dateFormat": "iso",
                "oddsFormat": "decimal",
                "includeSids": "true" if self._config.include_sids else "false",
            },
        )
        try:
            item = _mapping(payload, path="event")
            returned_id = _text(item.get("id"), path="event.id")
            returned_sport = _text(item.get("sport_key"), path="event.sport_key")
            if returned_id != event_id:
                raise _SchemaError("event.id does not match the requested event")
            if returned_sport != competition_id:
                raise _SchemaError("event.sport_key does not match the discovered competition")
            markets = _source_markets(
                item,
                event_id=event_id,
                basketball_full_event_bookmakers=frozenset(
                    self._config.basketball_full_event_bookmakers
                ),
            )
            ingested_at = _utc(self._clock(), field_name="clock")
            snapshot = OddsSnapshot(
                provider_id=self.provider.id,
                external_event_id=event_id,
                markets=markets,
                ingested_at=ingested_at,
                trace_id=f"the-odds-api:{event_id}:{ingested_at.isoformat()}",
            )
        except (_SchemaError, ProviderContractError) as exc:
            raise self._validated_payload_error(operation, response, exc) from exc

        self._emit(
            operation,
            outcome=ProviderTelemetryOutcome.SUCCESS,
            response=response,
            item_count=len(snapshot.markets),
        )
        return snapshot

    def stream_odds(self, external_event_ids: tuple[str, ...]) -> AsyncIterator[OddsSnapshot]:
        _ = external_event_ids
        raise self._error(
            ProviderOperation.STREAM_ODDS,
            ProviderErrorKind.UNSUPPORTED,
            "The Odds API Phase 6 adapter does not provide streaming",
        )

    async def health(self) -> ProviderHealth:
        operation = ProviderOperation.HEALTH
        try:
            _ = await self._load_sports(operation)
        except ProviderError as error:
            state = (
                ProviderHealthState.DEGRADED
                if error.kind
                in {ProviderErrorKind.RATE_LIMITED, ProviderErrorKind.MALFORMED_RESPONSE}
                else ProviderHealthState.UNAVAILABLE
            )
            return ProviderHealth(
                provider_id=self.provider.id,
                state=state,
                checked_at=_utc(self._clock(), field_name="clock"),
                detail=f"{error.kind.value}: {error}",
            )
        return ProviderHealth(
            provider_id=self.provider.id,
            state=ProviderHealthState.HEALTHY,
            checked_at=_utc(self._clock(), field_name="clock"),
        )

    async def rate_limit(self) -> RateLimitSnapshot | None:
        if self._last_rate_limit is None:
            _ = await self._load_sports(ProviderOperation.RATE_LIMIT)
        return self._last_rate_limit

    async def _load_sports(
        self,
        operation: ProviderOperation,
        *,
        emit_success: bool = True,
    ) -> tuple[_SportRecord, ...]:
        payload, response = await self._request_json(operation, "/sports", {"all": "false"})
        try:
            records = _sport_records(payload)
        except _SchemaError as exc:
            raise self._validated_payload_error(operation, response, exc) from exc
        if emit_success:
            self._emit(
                operation,
                outcome=ProviderTelemetryOutcome.SUCCESS,
                response=response,
                item_count=len(records),
            )
        return records

    async def _request_json(
        self,
        operation: ProviderOperation,
        path: str,
        query: Mapping[str, str],
    ) -> tuple[object, HttpResponse]:
        request_query = dict(query)
        request_query["apiKey"] = self._config.api_key
        try:
            response = await self._transport.get(
                url=f"{self._config.base_url}{path}",
                query=request_query,
                timeout_seconds=self._config.request_timeout_seconds,
            )
        except HttpTransportError as exc:
            error = self._error(
                operation,
                ProviderErrorKind.TRANSPORT,
                "upstream transport failed",
                retryable=True,
            )
            self._emit(operation, outcome=ProviderTelemetryOutcome.FAILURE, error=error)
            raise error from exc

        self._capture_rate_limit(response)
        if not 200 <= response.status_code < 300:
            error = self._http_error(operation, response)
            self._emit(
                operation,
                outcome=ProviderTelemetryOutcome.FAILURE,
                response=response,
                error=error,
            )
            raise error

        try:
            text = response.body.decode("utf-8")
            payload: object = json.loads(text, parse_float=Decimal, parse_int=Decimal)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            error = self._malformed(operation, "response body is not valid UTF-8 JSON")
            self._emit(
                operation,
                outcome=ProviderTelemetryOutcome.FAILURE,
                response=response,
                error=error,
            )
            raise error from exc

        return payload, response

    def _validated_payload_error(
        self,
        operation: ProviderOperation,
        response: HttpResponse,
        error: Exception,
    ) -> ProviderError:
        provider_error = self._malformed(operation, str(error))
        self._emit(
            operation,
            outcome=ProviderTelemetryOutcome.FAILURE,
            response=response,
            error=provider_error,
        )
        return provider_error

    def _capture_rate_limit(self, response: HttpResponse) -> None:
        remaining = _header_int(response.headers, "x-requests-remaining")
        used = _header_int(response.headers, "x-requests-used")
        retry_after = _retry_after(response.headers)
        if remaining is None and used is None and retry_after is None:
            return
        limit = None if remaining is None or used is None else remaining + used
        self._last_rate_limit = RateLimitSnapshot(
            provider_id=self.provider.id,
            observed_at=_utc(self._clock(), field_name="clock"),
            limit=limit,
            remaining=remaining if limit is not None else None,
            retry_after=retry_after,
        )

    def _emit(
        self,
        operation: ProviderOperation,
        *,
        outcome: ProviderTelemetryOutcome,
        response: HttpResponse | None = None,
        item_count: int | None = None,
        error: ProviderError | None = None,
    ) -> None:
        self._telemetry.emit(
            ProviderTelemetryEvent(
                provider_id=self.provider.id,
                operation=operation.value,
                observed_at=_utc(self._clock(), field_name="clock"),
                outcome=outcome,
                http_status=None if response is None else response.status_code,
                item_count=item_count,
                quota_remaining=(
                    None
                    if response is None
                    else _header_int(response.headers, "x-requests-remaining")
                ),
                quota_used=(
                    None if response is None else _header_int(response.headers, "x-requests-used")
                ),
                request_cost=(
                    None if response is None else _header_int(response.headers, "x-requests-last")
                ),
                error_kind=None if error is None else error.kind.value,
            )
        )

    def _http_error(self, operation: ProviderOperation, response: HttpResponse) -> ProviderError:
        retry_after = _retry_after(response.headers)
        status = response.status_code
        if status == 401:
            return self._error(
                operation,
                ProviderErrorKind.AUTHENTICATION,
                "The Odds API rejected authentication",
            )
        if status == 403:
            return self._error(
                operation,
                ProviderErrorKind.AUTHORIZATION,
                "The Odds API rejected authorization",
            )
        if status == 429:
            return self._error(
                operation,
                ProviderErrorKind.RATE_LIMITED,
                "The Odds API rate limit was exceeded",
                retryable=True,
                retry_after=retry_after,
            )
        if status == 400:
            return self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                "The Odds API rejected the request",
            )
        if status >= 500:
            return self._error(
                operation,
                ProviderErrorKind.UPSTREAM,
                f"The Odds API returned HTTP {status}",
                retryable=True,
                retry_after=retry_after,
            )
        return self._error(
            operation,
            ProviderErrorKind.UPSTREAM,
            f"The Odds API returned unexpected HTTP {status}",
            retryable=False,
            retry_after=retry_after,
        )

    def _request_text(
        self,
        value: object,
        *,
        operation: ProviderOperation,
        field_name: str,
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            raise self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                f"{field_name} must be non-empty text",
            )
        return value.strip()

    def _request_time(
        self,
        value: datetime | None,
        *,
        operation: ProviderOperation,
        field_name: str,
    ) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                f"{field_name} must be timezone-aware",
            )
        return value.astimezone(UTC)

    def _malformed(self, operation: ProviderOperation, message: str) -> ProviderError:
        return self._error(
            operation,
            ProviderErrorKind.MALFORMED_RESPONSE,
            f"malformed The Odds API response: {message}",
        )

    def _error(
        self,
        operation: ProviderOperation,
        kind: ProviderErrorKind,
        message: str,
        *,
        retryable: bool = False,
        retry_after: timedelta | None = None,
    ) -> ProviderError:
        return ProviderError(
            provider_id=self.provider.id,
            operation=operation.value,
            kind=kind,
            message=message,
            retryable=retryable,
            retry_after=retry_after,
        )
