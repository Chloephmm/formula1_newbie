"""Pure UTC timing decisions for qualifying publication."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


FIVE_HOURS = timedelta(hours=5)
RACE_CUTOFF = timedelta(hours=2)
PROCESSING_BUFFER = timedelta(minutes=30)
TICK_MINUTE = 17


@dataclass(frozen=True)
class PublicationTiming:
    first_check_at: datetime
    cutoff_at: datetime
    latest_processing_start_at: datetime
    first_scheduled_tick_at: datetime
    final_verification_tick_at: datetime
    allowed: bool
    reason: str | None


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("publication timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def next_hourly_tick(value: datetime | str) -> datetime:
    """Return the first :17 UTC tick at or after ``value``."""
    value = _utc(value)
    tick = value.replace(minute=TICK_MINUTE, second=0, microsecond=0)
    if tick < value:
        tick += timedelta(hours=1)
    return tick


def latest_hourly_tick(value: datetime | str) -> datetime:
    """Return the latest :17 UTC tick at or before ``value``."""
    value = _utc(value)
    tick = value.replace(minute=TICK_MINUTE, second=0, microsecond=0)
    if tick > value:
        tick -= timedelta(hours=1)
    return tick


def calculate_publication_timing(
    *, qualifying_end_at: datetime | str, race_start_at: datetime | str
) -> PublicationTiming:
    """Calculate the safe polling window and explain any unusable schedule."""
    qualifying_end_at = _utc(qualifying_end_at)
    race_start_at = _utc(race_start_at)
    first_check_at = qualifying_end_at + FIVE_HOURS
    cutoff_at = race_start_at - RACE_CUTOFF
    latest_processing_start_at = cutoff_at - PROCESSING_BUFFER
    first_scheduled_tick_at = next_hourly_tick(first_check_at)
    final_verification_tick_at = latest_hourly_tick(latest_processing_start_at)

    reason = None
    if first_check_at > cutoff_at:
        reason = "five_hour_wait_exceeds_cutoff"
    elif first_scheduled_tick_at > latest_processing_start_at:
        reason = "insufficient_processing_buffer"

    return PublicationTiming(
        first_check_at=first_check_at,
        cutoff_at=cutoff_at,
        latest_processing_start_at=latest_processing_start_at,
        first_scheduled_tick_at=first_scheduled_tick_at,
        final_verification_tick_at=final_verification_tick_at,
        allowed=reason is None,
        reason=reason,
    )
