"""OddsPapi V4 REST adapter used as ArbiScan's second real odds-data integration."""

from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

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

ODDSPAPI_PROVIDER_ID = ProviderId("provider:oddspapi")
ODDSPAPI_BASE_URL = "https://api.oddspapi.io/v4"

# Phase 6 originally embedded the first transport name in bookmaker IDs. Those IDs
# are already part of the canonical quote surface, so Phase 16.3 deliberately reuses
# that existing namespace for exact slug overlaps instead of creating duplicate price
# providers. A future explicit data migration may rename the namespace.
_LEGACY_SHARED_BOOKMAKER_PREFIX = "bookmaker:the-odds-api:"

Clock = Callable[[], datetime]


class _SchemaError(ValueError):
    """Internal payload-schema error translated at the provider boundary."""


@dataclass(frozen=True, slots=True)
class OddsPapiConfig:
    """Runtime configuration for OddsPapi without exposing its API key in repr."""

    api_key: str = field(repr=False, compare=False)
    base_url: str = ODDSPAPI_BASE_URL
    request_timeout_seconds: float = 10.0
    language: str = "en"

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ProviderContractError("OddsPapi API key must be non-empty text")
        object.__setattr__(self, "api_key", self.api_key.strip())

        if not isinstance(self.base_url, str) or not self.base_url.startswith("https://"):
            raise ProviderContractError("OddsPapi base_url must use HTTPS")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

        timeout = self.request_timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ProviderContractError("OddsPapi request timeout must be numeric")
        if not math.isfinite(float(timeout)) or timeout <= 0:
            raise ProviderContractError("OddsPapi request timeout must be finite and positive")
        object.__setattr__(self, "request_timeout_seconds", float(timeout))

        if not isinstance(self.language, str) or not self.language.strip():
            raise ProviderContractError("OddsPapi language must be non-empty text")
        language = self.language.strip().casefold()
        # Phase 16.3 resolves MVP market semantics using the provider's English
        # catalogue names. Accepting another locale would make the same market data
        # silently disappear, so fail fast until locale-independent IDs are proven.
        if language != "en":
            raise ProviderContractError("OddsPapi Phase 16.3 requires language='en'")
        object.__setattr__(self, "language", language)


@dataclass(frozen=True, slots=True)
class _SportRecord:
    external_id: int
    slug: str
    name: str
    sport: Sport | None


@dataclass(frozen=True, slots=True)
class _MarketRecord:
    external_id: str
    sport_id: int
    name: str
    player_prop: bool
    period: str
    market_type: str
    handicap: Decimal
    outcomes: Mapping[str, str]


_SLUG_TO_SPORT: Mapping[str, Sport] = MappingProxyType(
    {"soccer": Sport.FOOTBALL, "tennis": Sport.TENNIS}
)
_KNOWN_FIXTURE_STATUS_IDS = frozenset({0, 1, 2, 3})


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


def _integer(value: object, *, path: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise _SchemaError(f"{path} must be an integer >= {minimum}")
    return value


def _decimal(value: object, *, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise _SchemaError(f"{path} must be numeric")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise _SchemaError(f"{path} must be a decimal number") from exc
    if not parsed.is_finite():
        raise _SchemaError(f"{path} must be finite")
    return parsed


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


def _iso_query(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _retry_after(headers: Mapping[str, str]) -> timedelta | None:
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        seconds = int(raw)
    except ValueError:
        return None
    return None if seconds < 0 else timedelta(seconds=seconds)


def _sport_records(payload: object) -> tuple[_SportRecord, ...]:
    records: list[_SportRecord] = []
    for index, raw in enumerate(_sequence(payload, path="sports")):
        item = _mapping(raw, path=f"sports[{index}]")
        slug = _text(item.get("slug"), path=f"sports[{index}].slug").casefold()
        records.append(
            _SportRecord(
                external_id=_integer(item.get("sportId"), path=f"sports[{index}].sportId"),
                slug=slug,
                name=_text(item.get("sportName"), path=f"sports[{index}].sportName"),
                sport=_SLUG_TO_SPORT.get(slug),
            )
        )
    return tuple(records)


def _fixture_status(item: Mapping[str, object], *, path: str) -> tuple[int, str]:
    status_id = _integer(item.get("statusId"), path=f"{path}.statusId")
    if status_id not in _KNOWN_FIXTURE_STATUS_IDS:
        raise _SchemaError(f"{path}.statusId is not a documented fixture status")
    return status_id, _text(item.get("statusName"), path=f"{path}.statusName")


def _source_event(
    raw: object,
    *,
    expected_tournament_id: str,
    expected_sport: Sport,
    expected_sport_id: int,
) -> SourceEvent:
    item = _mapping(raw, path="fixture")
    fixture_id = _text(item.get("fixtureId"), path="fixture.fixtureId")
    sport_id = _integer(item.get("sportId"), path="fixture.sportId")
    tournament_id = str(_integer(item.get("tournamentId"), path="fixture.tournamentId"))
    if tournament_id != expected_tournament_id:
        raise _SchemaError("fixture.tournamentId does not match the requested tournament")
    if sport_id != expected_sport_id:
        raise _SchemaError("fixture.sportId does not match the discovered tournament sport")

    participant1_id = _integer(item.get("participant1Id"), path="fixture.participant1Id")
    participant2_id = _integer(item.get("participant2Id"), path="fixture.participant2Id")
    if participant1_id == participant2_id:
        raise _SchemaError("fixture participant IDs must differ")
    participant1_name = _text(item.get("participant1Name"), path="fixture.participant1Name")
    participant2_name = _text(item.get("participant2Name"), path="fixture.participant2Name")
    if participant1_name.casefold() == participant2_name.casefold():
        raise _SchemaError("fixture participant names must differ")
    _status_id, status_name = _fixture_status(item, path="fixture")

    return SourceEvent(
        external_id=fixture_id,
        sport=expected_sport,
        competition_external_id=tournament_id,
        participants=(
            SourceParticipant(
                external_id=str(participant1_id),
                name=participant1_name,
                role="participant1",
            ),
            SourceParticipant(
                external_id=str(participant2_id),
                name=participant2_name,
                role="participant2",
            ),
        ),
        scheduled_start=_timestamp(item.get("startTime"), path="fixture.startTime"),
        source_status=status_name,
    )


def _market_records(payload: object) -> Mapping[str, _MarketRecord]:
    records: dict[str, _MarketRecord] = {}
    target_names = {
        "full time result",
        "match winner",
        "winner",
        "over under full time",
        "asian handicap",
        "both teams to score",
    }
    for index, raw in enumerate(_sequence(payload, path="markets")):
        item = _mapping(raw, path=f"markets[{index}]")
        market_id = str(_integer(item.get("marketId"), path=f"markets[{index}].marketId"))
        sport_id = _integer(item.get("sportId"), path=f"markets[{index}].sportId")
        name = _text(item.get("marketName"), path=f"markets[{index}].marketName")
        if name.casefold() not in target_names:
            continue
        if market_id in records:
            raise _SchemaError("markets contains duplicate target marketId values")

        outcomes: dict[str, str] = {}
        for outcome_index, raw_outcome in enumerate(
            _sequence(item.get("outcomes"), path=f"markets[{index}].outcomes")
        ):
            outcome = _mapping(
                raw_outcome,
                path=f"markets[{index}].outcomes[{outcome_index}]",
            )
            outcome_id = str(
                _integer(
                    outcome.get("outcomeId"),
                    path=f"markets[{index}].outcomes[{outcome_index}].outcomeId",
                )
            )
            if outcome_id in outcomes:
                raise _SchemaError("target market contains duplicate outcomeId values")
            outcomes[outcome_id] = _text(
                outcome.get("outcomeName"),
                path=f"markets[{index}].outcomes[{outcome_index}].outcomeName",
            )
        if not outcomes:
            raise _SchemaError("target market.outcomes must not be empty")

        records[market_id] = _MarketRecord(
            external_id=market_id,
            sport_id=sport_id,
            name=name,
            player_prop=_boolean(item.get("playerProp"), path=f"markets[{index}].playerProp"),
            period=_text(item.get("period"), path=f"markets[{index}].period").casefold(),
            market_type=_text(
                item.get("marketType"),
                path=f"markets[{index}].marketType",
            ).casefold(),
            handicap=_decimal(item.get("handicap"), path=f"markets[{index}].handicap"),
            outcomes=MappingProxyType(outcomes),
        )
    return MappingProxyType(records)


def _is_supported_market(record: _MarketRecord, sport: Sport) -> bool:
    if record.player_prop:
        return False
    name = record.name.casefold()
    if sport is Sport.FOOTBALL:
        winner = (
            name == "full time result"
            and record.period == "fulltime"
            and record.market_type == "1x2"
            and record.handicap == Decimal(0)
            and len(record.outcomes) == 3
        )
        total = (
            name == "over under full time"
            and record.period == "fulltime"
            and record.market_type == "totals"
            and record.handicap > Decimal(0)
            and len(record.outcomes) == 2
            and {value.casefold() for value in record.outcomes.values()} == {"over", "under"}
        )
        asian_handicap = (
            name == "asian handicap"
            and record.period == "fulltime"
            and len(record.outcomes) == 2
            and {value.casefold() for value in record.outcomes.values()} == {"1", "2"}
        )
        both_teams_to_score = (
            name == "both teams to score"
            and record.period == "fulltime"
            and record.market_type == "totals"
            and record.handicap == Decimal(0)
            and len(record.outcomes) == 2
            and {value.casefold() for value in record.outcomes.values()} == {"yes", "no"}
        )
        return winner or total or asian_handicap or both_teams_to_score
    if sport is Sport.TENNIS:
        return (
            name in {"match winner", "winner"}
            and record.period in {"fulltime", "match"}
            and record.market_type == "winner"
            and record.handicap == Decimal(0)
            and len(record.outcomes) == 2
        )
    return False


def _shared_bookmaker_provider(slug: str) -> Provider:
    normalized = slug.strip().casefold()
    if not normalized or any(char.isspace() for char in normalized):
        raise _SchemaError("bookmaker slug must be non-empty and contain no whitespace")
    return Provider(
        id=ProviderId(f"{_LEGACY_SHARED_BOOKMAKER_PREFIX}{normalized}"),
        name=slug,
        kind=ProviderKind.BOOKMAKER,
    )


def _selection_timestamp(item: Mapping[str, object], *, path: str) -> datetime:
    bookmaker_changed = _optional_timestamp(
        item.get("bookmakerChangedAt"),
        path=f"{path}.bookmakerChangedAt",
    )
    changed = _timestamp(item.get("changedAt"), path=f"{path}.changedAt")
    return bookmaker_changed or changed


def _source_markets(
    payload: Mapping[str, object],
    *,
    event_id: str,
    sport: Sport,
    sport_id: int,
    catalog: Mapping[str, _MarketRecord],
) -> tuple[SourceMarket, ...]:
    bookmaker_odds = _mapping(payload.get("bookmakerOdds"), path="odds.bookmakerOdds")
    markets: list[SourceMarket] = []
    for bookmaker_slug in sorted(bookmaker_odds):
        bookmaker = _mapping(
            bookmaker_odds[bookmaker_slug],
            path=f"odds.bookmakerOdds.{bookmaker_slug}",
        )
        bookmaker_active = _boolean(
            bookmaker.get("bookmakerIsActive"),
            path=f"odds.bookmakerOdds.{bookmaker_slug}.bookmakerIsActive",
        )
        suspended = _boolean(
            bookmaker.get("suspended"),
            path=f"odds.bookmakerOdds.{bookmaker_slug}.suspended",
        )
        _text(
            bookmaker.get("bookmakerFixtureId"),
            path=f"odds.bookmakerOdds.{bookmaker_slug}.bookmakerFixtureId",
        )
        price_provider = _shared_bookmaker_provider(bookmaker_slug)
        raw_markets = _mapping(
            bookmaker.get("markets"),
            path=f"odds.bookmakerOdds.{bookmaker_slug}.markets",
        )

        for market_id in sorted(raw_markets, key=lambda value: (len(value), value)):
            record = catalog.get(market_id)
            if (
                record is None
                or record.sport_id != sport_id
                or not _is_supported_market(record, sport)
            ):
                continue
            raw_market = _mapping(
                raw_markets[market_id],
                path=f"odds.bookmakerOdds.{bookmaker_slug}.markets.{market_id}",
            )
            market_active = _boolean(
                raw_market.get("marketActive"),
                path=f"odds.bookmakerOdds.{bookmaker_slug}.markets.{market_id}.marketActive",
            )
            _text(
                raw_market.get("bookmakerMarketId"),
                path=f"odds.bookmakerOdds.{bookmaker_slug}.markets.{market_id}.bookmakerMarketId",
            )
            raw_outcomes = _mapping(
                raw_market.get("outcomes"),
                path=f"odds.bookmakerOdds.{bookmaker_slug}.markets.{market_id}.outcomes",
            )
            if set(raw_outcomes) != set(record.outcomes):
                raise _SchemaError(
                    f"supported market {market_id} outcomes do not match the market catalog"
                )

            for outcome_id in sorted(record.outcomes, key=lambda value: (len(value), value)):
                raw_outcome = _mapping(
                    raw_outcomes[outcome_id],
                    path=(
                        f"odds.bookmakerOdds.{bookmaker_slug}.markets.{market_id}."
                        f"outcomes.{outcome_id}"
                    ),
                )
                players = _mapping(
                    raw_outcome.get("players"),
                    path=(
                        f"odds.bookmakerOdds.{bookmaker_slug}.markets.{market_id}."
                        f"outcomes.{outcome_id}.players"
                    ),
                )
                if set(players) != {"0"}:
                    raise _SchemaError(
                        f"non-player market {market_id} must contain exactly players['0']"
                    )
                quote = _mapping(
                    players["0"],
                    path=(
                        f"odds.bookmakerOdds.{bookmaker_slug}.markets.{market_id}."
                        f"outcomes.{outcome_id}.players.0"
                    ),
                )
                quote_active = _boolean(
                    quote.get("active"),
                    path=f"market.{market_id}.outcome.{outcome_id}.active",
                )
                bookmaker_outcome_id = _text(
                    quote.get("bookmakerOutcomeId"),
                    path=f"market.{market_id}.outcome.{outcome_id}.bookmakerOutcomeId",
                )
                price = _decimal(
                    quote.get("price"),
                    path=f"market.{market_id}.outcome.{outcome_id}.price",
                )
                if price <= Decimal(1):
                    raise _SchemaError(f"market.{market_id}.outcome.{outcome_id}.price must be > 1")
                source_timestamp = _selection_timestamp(
                    quote,
                    path=f"market.{market_id}.outcome.{outcome_id}",
                )
                source_status = (
                    "active"
                    if bookmaker_active and not suspended and market_active and quote_active
                    else "suspended"
                )
                markets.append(
                    SourceMarket(
                        external_event_id=event_id,
                        external_market_id=f"{bookmaker_slug}:{market_id}:{outcome_id}:0",
                        label=f"{bookmaker_slug} {record.name}",
                        selections=(
                            SourceSelectionQuote(
                                external_selection_id=f"{outcome_id}:0:{bookmaker_outcome_id}",
                                label=record.outcomes[outcome_id],
                                price=str(price),
                                odds_format=SourceOddsFormat.DECIMAL,
                                source_status=source_status,
                                handicap=(
                                    record.handicap
                                    if (
                                        sport is Sport.FOOTBALL
                                        and record.name.casefold() == "asian handicap"
                                        and record.outcomes[outcome_id].casefold() == "1"
                                    )
                                    else (
                                        -record.handicap
                                        if (
                                            sport is Sport.FOOTBALL
                                            and record.name.casefold() == "asian handicap"
                                            and record.outcomes[outcome_id].casefold() == "2"
                                        )
                                        else None
                                    )
                                ),
                            ),
                        ),
                        source_status=source_status,
                        price_provider=price_provider,
                        source_timestamp=source_timestamp,
                        line=(
                            record.handicap
                            if (
                                sport is Sport.FOOTBALL
                                and record.name.casefold()
                                in {"over under full time", "asian handicap"}
                            )
                            else None
                        ),
                    )
                )
    return tuple(markets)


def _account_rate_limit(
    payload: object,
    *,
    provider_id: ProviderId,
    observed_at: datetime,
) -> RateLimitSnapshot | None:
    account = _mapping(payload, path="account")
    current_id = _optional_text(
        account.get("current_subscription_id"),
        path="account.current_subscription_id",
    )
    subscriptions = _sequence(account.get("subscriptions"), path="account.subscriptions")
    selected: Mapping[str, object] | None = None
    for index, raw in enumerate(subscriptions):
        subscription = _mapping(raw, path=f"account.subscriptions[{index}]")
        subscription_id = _text(
            subscription.get("subscription_id"),
            path=f"account.subscriptions[{index}].subscription_id",
        )
        active = _boolean(
            subscription.get("is_active"),
            path=f"account.subscriptions[{index}].is_active",
        )
        if current_id is not None and subscription_id == current_id:
            selected = subscription
            break
        if current_id is None and active and selected is None:
            selected = subscription
    if selected is None:
        return None

    request_limit = _integer(
        selected.get("request_limit"),
        path="account.subscription.request_limit",
    )
    request_count = _integer(
        selected.get("request_count"),
        path="account.subscription.request_count",
    )
    return RateLimitSnapshot(
        provider_id=provider_id,
        observed_at=observed_at,
        limit=request_limit,
        remaining=max(request_limit - request_count, 0),
    )


class OddsPapiProvider(ProviderAdapter):
    """Strict development-only OddsPapi V4 REST adapter for Phase 16.3."""

    def __init__(
        self,
        *,
        config: OddsPapiConfig,
        transport: AsyncHttpTransport | None = None,
        telemetry: ProviderTelemetrySink | None = None,
        canonical_id_hooks: CanonicalIdHooks | None = None,
        clock: Clock = _utc_now,
    ) -> None:
        if not isinstance(config, OddsPapiConfig):
            raise ProviderContractError("config must be OddsPapiConfig")
        self._config = config
        self._transport = transport or UrllibAsyncHttpTransport()
        self._telemetry = telemetry or NullProviderTelemetry()
        self._canonical_id_hooks = canonical_id_hooks
        self._clock = clock
        self._provider = Provider(
            id=ODDSPAPI_PROVIDER_ID,
            name="OddsPapi",
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
        self._competition_sports: dict[str, tuple[Sport, int]] = {}
        # Keep the complete discovered event identity. Odds snapshots must agree with
        # it before prices are emitted; otherwise a corrected/rescheduled fixture can
        # be attached to stale canonical identity.
        self._event_context: dict[str, tuple[SourceEvent, int]] = {}
        self._market_catalog: Mapping[str, _MarketRecord] | None = None
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
        operation = ProviderOperation.SUPPORTED_SPORTS
        payload, response = await self._request_json(
            operation,
            "/sports",
            {"language": self._config.language},
        )
        try:
            records = _sport_records(payload)
            sports = tuple(
                sorted(
                    {record.sport for record in records if record.sport is not None},
                    key=lambda value: value.value,
                )
            )
        except (_SchemaError, ProviderContractError) as exc:
            raise self._validated_payload_error(operation, response, exc) from exc
        self._emit(
            operation,
            outcome=ProviderTelemetryOutcome.SUCCESS,
            response=response,
            item_count=len(sports),
        )
        return sports

    async def discover_competitions(self, sport: Sport) -> tuple[SourceCompetition, ...]:
        operation = ProviderOperation.DISCOVER_COMPETITIONS
        if not isinstance(sport, Sport):
            raise self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                "sport must be a canonical Sport",
            )
        sport_record = await self._resolve_sport_record(sport, operation=operation)
        payload, response = await self._request_json(
            operation,
            "/tournaments",
            {"sportId": str(sport_record.external_id), "language": self._config.language},
        )
        try:
            competitions: list[SourceCompetition] = []
            for index, raw in enumerate(_sequence(payload, path="tournaments")):
                item = _mapping(raw, path=f"tournaments[{index}]")
                tournament_id = str(
                    _integer(
                        item.get("tournamentId"),
                        path=f"tournaments[{index}].tournamentId",
                    )
                )
                competitions.append(
                    SourceCompetition(
                        external_id=tournament_id,
                        sport=sport,
                        name=_text(
                            item.get("tournamentName"),
                            path=f"tournaments[{index}].tournamentName",
                        ),
                        region=_text(
                            item.get("categoryName"),
                            path=f"tournaments[{index}].categoryName",
                        ),
                    )
                )
                self._competition_sports[tournament_id] = (sport, sport_record.external_id)
            ordered = tuple(
                sorted(competitions, key=lambda value: (value.name.casefold(), value.external_id))
            )
        except (_SchemaError, ProviderContractError) as exc:
            raise self._validated_payload_error(operation, response, exc) from exc
        self._emit(
            operation,
            outcome=ProviderTelemetryOutcome.SUCCESS,
            response=response,
            item_count=len(ordered),
        )
        return ordered

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
        context = self._competition_sports.get(competition_id)
        if context is None:
            raise self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                "competition must be discovered before discovering fixtures",
            )
        sport, sport_id = context
        after = self._request_time(starts_after, operation=operation, field_name="starts_after")
        before = self._request_time(starts_before, operation=operation, field_name="starts_before")
        if after is not None and before is not None and after > before:
            raise self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                "starts_after cannot be later than starts_before",
            )

        query = {"tournamentId": competition_id, "language": self._config.language}
        if after is not None:
            query["from"] = _iso_query(after)
        if before is not None:
            query["to"] = _iso_query(before)
        payload, response = await self._request_json(operation, "/fixtures", query)
        try:
            events = tuple(
                _source_event(
                    raw,
                    expected_tournament_id=competition_id,
                    expected_sport=sport,
                    expected_sport_id=sport_id,
                )
                for raw in _sequence(payload, path="fixtures")
            )
            ordered = tuple(
                sorted(events, key=lambda value: (value.scheduled_start, value.external_id))
            )
        except (_SchemaError, ProviderContractError) as exc:
            raise self._validated_payload_error(operation, response, exc) from exc

        for event in ordered:
            self._event_context[event.external_id] = (event, sport_id)
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
        context = self._event_context.get(event_id)
        if context is None:
            raise self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                "event must be discovered before fetching event odds",
            )
        discovered_event, sport_id = context
        competition_id = discovered_event.competition_external_id
        sport = discovered_event.sport
        catalog = await self._load_market_catalog(operation)
        payload, response = await self._request_json(
            operation,
            "/odds",
            {
                "fixtureId": event_id,
                "oddsFormat": "decimal",
                "language": self._config.language,
                "verbosity": "3",
            },
        )
        try:
            item = _mapping(payload, path="odds")
            returned_event = _source_event(
                item,
                expected_tournament_id=competition_id,
                expected_sport=sport,
                expected_sport_id=sport_id,
            )
            if returned_event.external_id != event_id:
                raise _SchemaError("odds.fixtureId does not match the requested event")
            if returned_event.participants != discovered_event.participants:
                raise _SchemaError("odds participants do not match the discovered fixture")
            if returned_event.scheduled_start != discovered_event.scheduled_start:
                raise _SchemaError("odds.startTime does not match the discovered fixture")

            status_id, _status_name = _fixture_status(item, path="odds")
            has_odds = _boolean(item.get("hasOdds"), path="odds.hasOdds")
            ingested_at = _utc(self._clock(), field_name="clock")
            if not has_odds:
                snapshot = None
            else:
                markets = _source_markets(
                    item,
                    event_id=event_id,
                    sport=sport,
                    sport_id=sport_id,
                    catalog=catalog,
                )
                if status_id != 0:
                    markets = tuple(self._suspend_market(market) for market in markets)
                snapshot = OddsSnapshot(
                    provider_id=self.provider.id,
                    external_event_id=event_id,
                    markets=markets,
                    ingested_at=ingested_at,
                    source_timestamp=_timestamp(item.get("updatedAt"), path="odds.updatedAt"),
                    trace_id=f"oddspapi:{event_id}:{ingested_at.isoformat()}",
                )
        except (_SchemaError, ProviderContractError) as exc:
            raise self._validated_payload_error(operation, response, exc) from exc

        self._emit(
            operation,
            outcome=ProviderTelemetryOutcome.SUCCESS,
            response=response,
            item_count=0 if snapshot is None else len(snapshot.markets),
        )
        return snapshot

    @staticmethod
    def _suspend_market(market: SourceMarket) -> SourceMarket:
        return SourceMarket(
            external_event_id=market.external_event_id,
            external_market_id=market.external_market_id,
            label=market.label,
            selections=tuple(
                SourceSelectionQuote(
                    external_selection_id=selection.external_selection_id,
                    label=selection.label,
                    price=selection.price,
                    odds_format=selection.odds_format,
                    source_status="suspended",
                    handicap=selection.handicap,
                )
                for selection in market.selections
            ),
            source_status="suspended",
            price_provider=market.price_provider,
            source_timestamp=market.source_timestamp,
            line=market.line,
            period_index=market.period_index,
        )

    def stream_odds(self, external_event_ids: tuple[str, ...]) -> AsyncIterator[OddsSnapshot]:
        _ = external_event_ids
        raise self._error(
            ProviderOperation.STREAM_ODDS,
            ProviderErrorKind.UNSUPPORTED,
            "OddsPapi Phase 16.3 adapter intentionally exposes REST snapshots only",
        )

    async def health(self) -> ProviderHealth:
        operation = ProviderOperation.HEALTH
        try:
            payload, response = await self._request_json(
                operation,
                "/sports",
                {"language": self._config.language},
            )
            try:
                records = _sport_records(payload)
                if not any(record.sport is not None for record in records):
                    raise _SchemaError("sports response contains no Phase-16 supported sport")
            except (_SchemaError, ProviderContractError) as exc:
                raise self._validated_payload_error(operation, response, exc) from exc
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
        self._emit(operation, outcome=ProviderTelemetryOutcome.SUCCESS, response=response)
        return ProviderHealth(
            provider_id=self.provider.id,
            state=ProviderHealthState.HEALTHY,
            checked_at=_utc(self._clock(), field_name="clock"),
        )

    async def rate_limit(self) -> RateLimitSnapshot | None:
        operation = ProviderOperation.RATE_LIMIT
        payload, response = await self._request_json(operation, "/account", {})
        try:
            snapshot = _account_rate_limit(
                payload,
                provider_id=self.provider.id,
                observed_at=_utc(self._clock(), field_name="clock"),
            )
        except (_SchemaError, ProviderContractError) as exc:
            raise self._validated_payload_error(operation, response, exc) from exc
        self._last_rate_limit = snapshot
        self._emit(operation, outcome=ProviderTelemetryOutcome.SUCCESS, response=response)
        return snapshot

    async def _resolve_sport_record(
        self,
        sport: Sport,
        *,
        operation: ProviderOperation,
    ) -> _SportRecord:
        payload, response = await self._request_json(
            operation,
            "/sports",
            {"language": self._config.language},
        )
        try:
            records = _sport_records(payload)
            matches = tuple(record for record in records if record.sport is sport)
            if len(matches) != 1:
                raise _SchemaError(
                    f"OddsPapi returned {len(matches)} records for canonical sport {sport.value}"
                )
            return matches[0]
        except (_SchemaError, ProviderContractError) as exc:
            raise self._validated_payload_error(operation, response, exc) from exc

    async def _load_market_catalog(
        self,
        operation: ProviderOperation,
    ) -> Mapping[str, _MarketRecord]:
        if self._market_catalog is not None:
            return self._market_catalog
        payload, response = await self._request_json(
            operation,
            "/markets",
            {"language": self._config.language},
        )
        try:
            catalog = _market_records(payload)
        except (_SchemaError, ProviderContractError) as exc:
            raise self._validated_payload_error(operation, response, exc) from exc
        self._market_catalog = catalog
        return catalog

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
            payload: object = json.loads(text, parse_float=Decimal)
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

    def _emit(
        self,
        operation: ProviderOperation,
        *,
        outcome: ProviderTelemetryOutcome,
        response: HttpResponse | None = None,
        item_count: int | None = None,
        error: ProviderError | None = None,
    ) -> None:
        quota_remaining = None if self._last_rate_limit is None else self._last_rate_limit.remaining
        quota_used = None
        if (
            self._last_rate_limit is not None
            and self._last_rate_limit.limit is not None
            and self._last_rate_limit.remaining is not None
        ):
            quota_used = self._last_rate_limit.limit - self._last_rate_limit.remaining
        self._telemetry.emit(
            ProviderTelemetryEvent(
                provider_id=self.provider.id,
                operation=operation.value,
                observed_at=_utc(self._clock(), field_name="clock"),
                outcome=outcome,
                http_status=None if response is None else response.status_code,
                item_count=item_count,
                quota_remaining=quota_remaining,
                quota_used=quota_used,
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
                "OddsPapi rejected authentication",
            )
        if status == 403:
            return self._error(
                operation,
                ProviderErrorKind.AUTHORIZATION,
                "OddsPapi rejected authorization",
            )
        if status == 429:
            return self._error(
                operation,
                ProviderErrorKind.RATE_LIMITED,
                "OddsPapi rate limit was exceeded",
                retryable=True,
                retry_after=retry_after,
            )
        if status in {400, 404, 405, 409, 422}:
            return self._error(
                operation,
                ProviderErrorKind.INVALID_REQUEST,
                f"OddsPapi rejected the request with HTTP {status}",
            )
        if status >= 500:
            return self._error(
                operation,
                ProviderErrorKind.UPSTREAM,
                f"OddsPapi returned HTTP {status}",
                retryable=True,
                retry_after=retry_after,
            )
        return self._error(
            operation,
            ProviderErrorKind.UPSTREAM,
            f"OddsPapi returned unexpected HTTP {status}",
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
            f"malformed OddsPapi response: {message}",
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
