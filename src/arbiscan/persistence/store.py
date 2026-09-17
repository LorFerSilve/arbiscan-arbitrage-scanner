"""Durable, replay-oriented persistence for canonical ArbiScan evidence."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from arbiscan.domain.errors import DomainValidationError
from arbiscan.domain.models import OddsQuote, Opportunity, StakePlan
from arbiscan.domain.serialization import dumps, loads


class PersistenceError(RuntimeError):
    """Raised when durable evidence cannot be written or reconstructed safely."""


@dataclass(frozen=True, slots=True)
class OpportunityEvidence:
    """Evidence required to reproduce one previously emitted opportunity."""

    opportunity: Opportunity
    quotes: tuple[OddsQuote, ...]
    stake_plan: StakePlan | None


_MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE canonical_snapshots (
            entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, event_id TEXT,
            provider_id TEXT, occurred_at TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY (entity_type, entity_id)
        );
        CREATE INDEX idx_snapshots_event_time ON canonical_snapshots(event_id, occurred_at);
        CREATE INDEX idx_snapshots_provider_time ON canonical_snapshots(provider_id, occurred_at);
        CREATE TABLE opportunity_quotes (
            opportunity_id TEXT NOT NULL, quote_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
            PRIMARY KEY (opportunity_id, quote_id), UNIQUE (opportunity_id, ordinal)
        );
        CREATE INDEX idx_opportunity_quotes_quote ON opportunity_quotes(quote_id);
        CREATE TABLE opportunity_stake_plans (
            opportunity_id TEXT PRIMARY KEY, stake_plan_id TEXT NOT NULL UNIQUE
        );
        CREATE TABLE audit_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL, action TEXT NOT NULL, recorded_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE INDEX idx_audit_entity_time
            ON audit_events(entity_type, entity_id, recorded_at);
        """,
    ),
    (
        2,
        """
        ALTER TABLE canonical_snapshots ADD COLUMN transport_provider_id TEXT;
        UPDATE canonical_snapshots
            SET transport_provider_id = provider_id
            WHERE entity_type = 'odds_quote' AND transport_provider_id IS NULL;
        CREATE INDEX idx_snapshots_transport_provider_time
            ON canonical_snapshots(transport_provider_id, occurred_at);
        """,
    ),
)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PersistenceError("persistence timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _id(value: object) -> str:
    identifier = getattr(value, "value", None)
    if not isinstance(identifier, str) or not identifier:
        raise PersistenceError("canonical identifier must expose a non-empty string value")
    return identifier


def _quote_transport_id(quote: OddsQuote) -> str:
    provider_id = quote.transport_provider_id
    if provider_id is None:
        raise PersistenceError("validated odds quote must expose transport_provider_id")
    return _id(provider_id)


def _payloads_equivalent(entity_type: str, left: str, right: str) -> bool:
    """Compare persisted payloads semantically across supported schema revisions."""
    model_type: type[OddsQuote] | type[Opportunity] | type[StakePlan] | None = {
        "odds_quote": OddsQuote,
        "opportunity": Opportunity,
        "stake_plan": StakePlan,
    }.get(entity_type)
    if model_type is None:
        return False
    try:
        return loads(left, model_type) == loads(right, model_type)
    except DomainValidationError:
        return False


class SqliteAuditStore:
    """Transactional canonical snapshot and audit-evidence repository."""

    def __init__(self, database: str | Path) -> None:
        self._database = str(database)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def migrate(self) -> None:
        """Apply all schema migrations exactly once."""
        try:
            with self._connect() as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                )
                applied = {
                    row[0] for row in connection.execute("SELECT version FROM schema_migrations")
                }
                for version, sql in _MIGRATIONS:
                    if version in applied:
                        continue
                    for statement in sql.split(";"):
                        if statement.strip():
                            connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, datetime.now(UTC).isoformat()),
                    )
        except sqlite3.Error as exc:
            raise PersistenceError("failed to migrate persistence schema") from exc

    def persist_quote(self, quote: OddsQuote) -> None:
        self._persist_snapshot(
            "odds_quote",
            _id(quote.id),
            _id(quote.event_id),
            _id(quote.provider_id),
            _quote_transport_id(quote),
            quote.ingested_at,
            dumps(quote),
        )

    def persist_opportunity(
        self,
        opportunity: Opportunity,
        quotes: Iterable[OddsQuote],
        *,
        stake_plan: StakePlan | None = None,
    ) -> None:
        """Atomically persist an opportunity and all evidence needed for replay."""
        quote_by_id = {_id(quote.id): quote for quote in quotes}
        expected = tuple(_id(quote_id) for quote_id in opportunity.quote_ids)
        if set(quote_by_id) != set(expected) or len(quote_by_id) != len(expected):
            raise PersistenceError(
                "opportunity evidence must contain exactly its referenced quotes"
            )
        if stake_plan is not None and _id(stake_plan.opportunity_id) != _id(opportunity.id):
            raise PersistenceError("stake plan belongs to a different opportunity")

        try:
            with self._connect() as connection:
                opportunity_id = _id(opportunity.id)
                for quote_id in expected:
                    quote = quote_by_id[quote_id]
                    self._upsert(
                        connection,
                        "odds_quote",
                        quote_id,
                        _id(quote.event_id),
                        _id(quote.provider_id),
                        _quote_transport_id(quote),
                        quote.ingested_at,
                        dumps(quote),
                    )
                self._upsert(
                    connection,
                    "opportunity",
                    opportunity_id,
                    _id(opportunity.event_id),
                    None,
                    None,
                    opportunity.detected_at,
                    dumps(opportunity),
                )
                for ordinal, quote_id in enumerate(expected):
                    connection.execute(
                        "INSERT OR IGNORE INTO opportunity_quotes"
                        "(opportunity_id, quote_id, ordinal) VALUES (?, ?, ?)",
                        (opportunity_id, quote_id, ordinal),
                    )
                if stake_plan is not None:
                    plan_id = _id(stake_plan.id)
                    existing_plan = connection.execute(
                        "SELECT stake_plan_id FROM opportunity_stake_plans "
                        "WHERE opportunity_id = ?",
                        (opportunity_id,),
                    ).fetchone()
                    if existing_plan is not None and existing_plan[0] != plan_id:
                        raise PersistenceError(
                            "opportunity already has different persisted stake-plan evidence"
                        )
                    self._upsert(
                        connection,
                        "stake_plan",
                        plan_id,
                        _id(opportunity.event_id),
                        None,
                        None,
                        stake_plan.created_at,
                        dumps(stake_plan),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO opportunity_stake_plans"
                        "(opportunity_id, stake_plan_id) VALUES (?, ?)",
                        (opportunity_id, plan_id),
                    )
        except sqlite3.Error as exc:
            raise PersistenceError("failed to persist opportunity evidence") from exc

    def reconstruct_opportunity(self, opportunity_id: str) -> OpportunityEvidence:
        """Load and validate the complete canonical evidence for an opportunity."""
        try:
            with self._connect() as connection:
                opportunity = loads(
                    self._payload(connection, "opportunity", opportunity_id), Opportunity
                )
                rows = connection.execute(
                    "SELECT quote_id FROM opportunity_quotes WHERE opportunity_id = ? ORDER BY ordinal",
                    (opportunity_id,),
                ).fetchall()
                quotes = tuple(
                    loads(self._payload(connection, "odds_quote", row[0]), OddsQuote)
                    for row in rows
                )
                stake_row = connection.execute(
                    "SELECT stake_plan_id FROM opportunity_stake_plans WHERE opportunity_id = ?",
                    (opportunity_id,),
                ).fetchone()
                stake_plan = (
                    None
                    if stake_row is None
                    else loads(self._payload(connection, "stake_plan", stake_row[0]), StakePlan)
                )
        except (sqlite3.Error, DomainValidationError) as exc:
            raise PersistenceError("failed to reconstruct opportunity evidence") from exc
        if tuple(quote.id for quote in quotes) != opportunity.quote_ids:
            raise PersistenceError("persisted opportunity evidence is incomplete or inconsistent")
        return OpportunityEvidence(opportunity, quotes, stake_plan)

    def purge_quotes_before(self, cutoff: datetime) -> int:
        """Delete old unreferenced quotes while preserving opportunity evidence."""
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM canonical_snapshots WHERE entity_type = 'odds_quote' "
                    "AND occurred_at < ? AND entity_id NOT IN (SELECT quote_id FROM opportunity_quotes)",
                    (_utc_text(cutoff),),
                )
                return cursor.rowcount
        except sqlite3.Error as exc:
            raise PersistenceError("failed to apply quote retention") from exc

    def _persist_snapshot(
        self,
        entity_type: str,
        entity_id: str,
        event_id: str | None,
        provider_id: str | None,
        transport_provider_id: str | None,
        occurred_at: datetime,
        payload: str,
    ) -> None:
        try:
            with self._connect() as connection:
                self._upsert(
                    connection,
                    entity_type,
                    entity_id,
                    event_id,
                    provider_id,
                    transport_provider_id,
                    occurred_at,
                    payload,
                )
        except sqlite3.Error as exc:
            raise PersistenceError("failed to persist canonical snapshot") from exc

    @staticmethod
    def _upsert(
        connection: sqlite3.Connection,
        entity_type: str,
        entity_id: str,
        event_id: str | None,
        provider_id: str | None,
        transport_provider_id: str | None,
        occurred_at: datetime,
        payload: str,
    ) -> None:
        existing = connection.execute(
            "SELECT payload FROM canonical_snapshots WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        ).fetchone()
        if existing is not None:
            existing_payload = existing[0]
            if not isinstance(existing_payload, str):
                raise PersistenceError("persisted canonical payload is not text")
            if existing_payload != payload and not _payloads_equivalent(
                entity_type, existing_payload, payload
            ):
                raise PersistenceError("canonical ID collision with different persisted content")
            return
        connection.execute(
            "INSERT INTO canonical_snapshots"
            "(entity_type, entity_id, event_id, provider_id, transport_provider_id, "
            "occurred_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                entity_type,
                entity_id,
                event_id,
                provider_id,
                transport_provider_id,
                _utc_text(occurred_at),
                payload,
            ),
        )
        connection.execute(
            "INSERT INTO audit_events"
            "(entity_type, entity_id, action, recorded_at, payload) VALUES (?, ?, ?, ?, ?)",
            (entity_type, entity_id, "created", datetime.now(UTC).isoformat(), payload),
        )

    @staticmethod
    def _payload(connection: sqlite3.Connection, entity_type: str, entity_id: str) -> str:
        row = connection.execute(
            "SELECT payload FROM canonical_snapshots WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        ).fetchone()
        if row is None:
            raise PersistenceError(f"missing persisted {entity_type}: {entity_id}")
        payload = row[0]
        if not isinstance(payload, str):
            raise PersistenceError("persisted canonical payload is not text")
        return payload
