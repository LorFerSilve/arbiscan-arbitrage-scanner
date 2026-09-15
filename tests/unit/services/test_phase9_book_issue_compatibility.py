"""Compatibility regressions for Phase-9 vertical-slice book diagnostics."""

from arbiscan.domain import EventId, MarketId
from arbiscan.marketbook import MarketBookDiagnostic, MarketBookDiagnosticCode
from arbiscan.services.vertical_slice import (
    BookIssueCode,
    _compatibility_book_issues,
)


def test_insufficient_outcomes_remains_visible_to_legacy_book_issue_consumers() -> None:
    market_id = MarketId("market:single-outcome")
    diagnostic = MarketBookDiagnostic(
        code=MarketBookDiagnosticCode.INSUFFICIENT_OUTCOMES,
        event_id=EventId("event:test"),
        market_id=market_id,
        detail="canonical market defines fewer than two outcomes",
    )

    issues = _compatibility_book_issues((diagnostic,))

    assert len(issues) == 1
    assert issues[0].market_id == market_id
    assert issues[0].code is BookIssueCode.EVALUATION_REJECTED
    assert issues[0].detail == diagnostic.detail
