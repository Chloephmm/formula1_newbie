"""Pure timing decisions for automated qualifying publication."""
from datetime import datetime, timedelta, timezone
import importlib

import pytest


def _timing_module():
    return importlib.import_module("src.publication.timing")


def test_timing_builds_hourly_ticks_and_final_processing_deadline():
    timing = _timing_module()

    decision = timing.calculate_publication_timing(
        qualifying_end_at=datetime(2026, 5, 2, 20, 0, tzinfo=timezone.utc),
        race_start_at=datetime(2026, 5, 3, 20, 0, tzinfo=timezone.utc),
    )

    assert decision.first_check_at == datetime(2026, 5, 3, 1, 0, tzinfo=timezone.utc)
    assert decision.cutoff_at == datetime(2026, 5, 3, 18, 0, tzinfo=timezone.utc)
    assert decision.latest_processing_start_at == datetime(
        2026, 5, 3, 17, 30, tzinfo=timezone.utc
    )
    assert decision.first_scheduled_tick_at == datetime(
        2026, 5, 3, 1, 17, tzinfo=timezone.utc
    )
    assert decision.final_verification_tick_at == datetime(
        2026, 5, 3, 17, 17, tzinfo=timezone.utc
    )
    assert decision.allowed is True
    assert decision.reason is None


def test_timing_keeps_an_exact_17_minute_tick_and_normalizes_to_utc():
    timing = _timing_module()
    eastern = timezone(timedelta(hours=-4))

    decision = timing.calculate_publication_timing(
        qualifying_end_at=datetime(2026, 5, 2, 16, 17, tzinfo=eastern),
        race_start_at=datetime(2026, 5, 3, 16, 0, tzinfo=eastern),
    )

    assert decision.first_check_at == datetime(2026, 5, 3, 1, 17, tzinfo=timezone.utc)
    assert decision.first_scheduled_tick_at == decision.first_check_at
    assert decision.first_scheduled_tick_at.tzinfo == timezone.utc


def test_timing_rejects_when_five_hour_wait_exceeds_cutoff():
    timing = _timing_module()

    decision = timing.calculate_publication_timing(
        qualifying_end_at=datetime(2026, 5, 3, 15, 30, tzinfo=timezone.utc),
        race_start_at=datetime(2026, 5, 3, 22, 0, tzinfo=timezone.utc),
    )

    assert decision.allowed is False
    assert decision.reason == "five_hour_wait_exceeds_cutoff"


def test_timing_rejects_when_no_tick_has_processing_buffer():
    timing = _timing_module()

    decision = timing.calculate_publication_timing(
        qualifying_end_at=datetime(2026, 5, 3, 12, 18, tzinfo=timezone.utc),
        race_start_at=datetime(2026, 5, 3, 20, 30, tzinfo=timezone.utc),
    )

    assert decision.first_check_at < decision.cutoff_at
    assert decision.allowed is False
    assert decision.reason == "insufficient_processing_buffer"


def test_timing_rejects_naive_inputs():
    timing = _timing_module()

    with pytest.raises(ValueError, match="timezone-aware"):
        timing.calculate_publication_timing(
            qualifying_end_at=datetime(2026, 5, 2, 20, 0),
            race_start_at=datetime(2026, 5, 3, 20, 0, tzinfo=timezone.utc),
        )
