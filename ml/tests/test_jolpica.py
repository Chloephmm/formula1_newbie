"""Unit tests for the Jolpica data helpers (pure functions — no network)."""
import pytest

from src.data.jolpica import laptime_to_seconds


def test_laptime_to_seconds_parses():
    assert laptime_to_seconds("1:29.708") == pytest.approx(89.708)
    assert laptime_to_seconds("0:58.402") == pytest.approx(58.402)
    assert laptime_to_seconds("58.402") == pytest.approx(58.402)


def test_laptime_to_seconds_handles_bad_input():
    for bad in (None, "", "   ", "not-a-time", 123):
        assert laptime_to_seconds(bad) is None
