"""Canonical enumerations shared across providers and subsystems."""

from enum import StrEnum


class Sport(StrEnum):
    """Sports currently representable by the canonical model."""

    FOOTBALL = "football"
    TENNIS = "tennis"
    MOTORSPORT = "motorsport"


class ParticipantKind(StrEnum):
    """Semantic participant categories independent of a provider schema."""

    TEAM = "team"
    INDIVIDUAL = "individual"
    DRIVER = "driver"
    CONSTRUCTOR = "constructor"
    OTHER = "other"


class EventStatus(StrEnum):
    """Canonical sporting-event lifecycle state."""

    SCHEDULED = "scheduled"
    LIVE = "live"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class MarketKind(StrEnum):
    """Provider-independent market semantics."""

    MATCH_WINNER_2_WAY = "match_winner_2_way"
    MATCH_WINNER_3_WAY = "match_winner_3_way"
    QUALIFICATION_WINNER = "qualification_winner"
    TOTAL_POINTS = "total_points"
    HANDICAP = "handicap"
    SET_WINNER = "set_winner"
    OUTRIGHT_WINNER = "outright_winner"


class MarketPeriod(StrEnum):
    """Scope over which a market settles."""

    FULL_EVENT = "full_event"
    REGULATION = "regulation"
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"
    SET = "set"
    PERIOD = "period"
    QUARTER = "quarter"
    RACE = "race"
    TOURNAMENT = "tournament"


class SelectionKind(StrEnum):
    """Semantic market outcome represented without provider labels."""

    PARTICIPANT = "participant"
    DRAW = "draw"
    OVER = "over"
    UNDER = "under"
    YES = "yes"
    NO = "no"


class QuoteStatus(StrEnum):
    """Eligibility state of an odds quote."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class ProviderKind(StrEnum):
    """Type of source producing odds data."""

    BOOKMAKER = "bookmaker"
    AGGREGATOR = "aggregator"
    EXCHANGE = "exchange"
    SYNTHETIC = "synthetic"


class OpportunityStatus(StrEnum):
    """Lifecycle state of a detected arbitrage opportunity."""

    ACTIVE = "active"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
