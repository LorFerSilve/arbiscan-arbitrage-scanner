"""Explicit resolution results for fail-closed normalization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class ResolutionStatus(StrEnum):
    """Outcome of deterministic source-to-canonical resolution."""

    RESOLVED = "resolved"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class Resolution(Generic[T]):
    """A canonical value or an explicit fail-closed resolution outcome."""

    status: ResolutionStatus
    value: T | None = None
    candidates: tuple[T, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        candidates = tuple(self.candidates)
        object.__setattr__(self, "candidates", candidates)
        if not isinstance(self.status, ResolutionStatus):
            raise ValueError("resolution status must be ResolutionStatus")
        if not isinstance(self.detail, str):
            raise ValueError("resolution detail must be text")

        if self.status is ResolutionStatus.RESOLVED:
            if self.value is None:
                raise ValueError("resolved result requires a value")
            if candidates:
                raise ValueError("resolved result cannot expose candidates")
            return

        if self.value is not None:
            raise ValueError("unresolved result cannot expose a value")
        if self.status is ResolutionStatus.UNKNOWN and candidates:
            raise ValueError("unknown result cannot expose candidates")
        if self.status is ResolutionStatus.AMBIGUOUS and len(candidates) < 2:
            raise ValueError("ambiguous result requires at least two candidates")

    @property
    def is_resolved(self) -> bool:
        """Return whether this result contains exactly one canonical value."""
        return self.status is ResolutionStatus.RESOLVED

    @classmethod
    def resolved(cls, value: T, *, detail: str = "") -> Resolution[T]:
        return cls(status=ResolutionStatus.RESOLVED, value=value, detail=detail)

    @classmethod
    def unknown(cls, *, detail: str) -> Resolution[T]:
        return cls(status=ResolutionStatus.UNKNOWN, detail=detail)

    @classmethod
    def ambiguous(
        cls,
        candidates: tuple[T, ...],
        *,
        detail: str,
    ) -> Resolution[T]:
        return cls(
            status=ResolutionStatus.AMBIGUOUS,
            candidates=candidates,
            detail=detail,
        )
