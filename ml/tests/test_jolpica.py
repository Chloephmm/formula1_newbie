"""Unit tests for the Jolpica data helpers (pure functions — no network)."""
import pytest

from src.data import jolpica
from src.data.jolpica import laptime_to_seconds


def test_laptime_to_seconds_parses():
    assert laptime_to_seconds("1:29.708") == pytest.approx(89.708)
    assert laptime_to_seconds("0:58.402") == pytest.approx(58.402)
    assert laptime_to_seconds("58.402") == pytest.approx(58.402)


def test_laptime_to_seconds_handles_bad_input():
    for bad in (None, "", "   ", "not-a-time", 123):
        assert laptime_to_seconds(bad) is None


def _schedule_page(*, qualifying_date="2026-03-07", qualifying_time="15:00:00Z"):
    return {
        "RaceTable": {
            "Races": [
                {
                    "season": "2026",
                    "round": "1",
                    "raceName": "Australian Grand Prix",
                    "Circuit": {
                        "circuitId": "albert_park",
                        "circuitName": "Albert Park Grand Prix Circuit",
                        "Location": {"country": "Australia", "locality": "Melbourne"},
                    },
                    "date": "2026-03-08",
                    "time": "04:00:00Z",
                    "Qualifying": {"date": qualifying_date, "time": qualifying_time},
                }
            ]
        }
    }


def test_schedule_uses_nested_qualifying_and_race_timestamps(monkeypatch):
    monkeypatch.setattr(jolpica, "_iter_pages", lambda path: iter([_schedule_page()]))
    monkeypatch.setattr(
        jolpica,
        "_utc_now_iso",
        lambda: "2026-01-02T03:04:05Z",
        raising=False,
    )

    row = jolpica.get_schedule(2026).iloc[0]

    assert row["date"] == "2026-03-08"
    assert row["qualifying_start_at"] == "2026-03-07T15:00:00Z"
    assert row["qualifying_end_at"] == "2026-03-07T18:00:00Z"
    assert row["end_time_estimated"] == True
    assert row["race_start_at"] == "2026-03-08T04:00:00Z"
    assert row["schedule_updated_at"] == "2026-01-02T03:04:05Z"


def test_schedule_reflects_postponed_qualifying_instead_of_inferring_from_race(monkeypatch):
    pages = iter([
        _schedule_page(),
        _schedule_page(qualifying_date="2026-03-08", qualifying_time="01:30:00Z"),
    ])
    monkeypatch.setattr(jolpica, "_iter_pages", lambda path: iter([next(pages)]))

    original = jolpica.get_schedule(2026).iloc[0]
    postponed = jolpica.get_schedule(2026).iloc[0]

    assert original["qualifying_start_at"] == "2026-03-07T15:00:00Z"
    assert postponed["qualifying_start_at"] == "2026-03-08T01:30:00Z"
    assert postponed["qualifying_end_at"] == "2026-03-08T04:30:00Z"
    assert postponed["race_start_at"] == original["race_start_at"]


def test_schedule_does_not_infer_qualifying_when_jolpica_omits_it(monkeypatch):
    page = _schedule_page()
    del page["RaceTable"]["Races"][0]["Qualifying"]
    monkeypatch.setattr(jolpica, "_iter_pages", lambda path: iter([page]))

    row = jolpica.get_schedule(2026).iloc[0]

    assert row["qualifying_start_at"] is None
    assert row["qualifying_end_at"] is None


def _qualifying_race(driver_id, position):
    return {
        "season": "2026",
        "round": "4",
        "raceName": "Miami Grand Prix",
        "Circuit": {"circuitId": "miami"},
        "QualifyingResults": [
            {
                "position": str(position),
                "Driver": {
                    "driverId": driver_id,
                    "code": driver_id[:3].upper(),
                    "givenName": "Test",
                    "familyName": driver_id,
                },
                "Constructor": {"constructorId": "team", "name": "Test Team"},
                "Q1": f"1:2{position}.000",
            }
        ],
    }


def test_round_qualifying_fetch_collects_all_pages_and_metadata(monkeypatch):
    pages = [
        {
            "total": "2",
            "offset": "0",
            "limit": "1",
            "RaceTable": {"Races": [_qualifying_race("driver_a", 1)]},
        },
        {
            "total": "2",
            "offset": "1",
            "limit": "1",
            "RaceTable": {"Races": [_qualifying_race("driver_b", 2)]},
        },
    ]
    requested_paths = []

    def fake_pages(path):
        requested_paths.append(path)
        yield from pages

    monkeypatch.setattr(jolpica, "_iter_pages", fake_pages)

    result = jolpica.get_qualifying_round(2026, 4)

    assert requested_paths == ["2026/4/qualifying"]
    assert result.data["driver_id"].tolist() == ["driver_a", "driver_b"]
    assert result.data["driver_name"].tolist() == ["Test driver_a", "Test driver_b"]
    assert result.data["constructor_name"].tolist() == ["Test Team", "Test Team"]
    assert result.pagination.reported_total == 2
    assert result.pagination.fetched_count == 2
    assert result.pagination.pages_fetched == 2
    assert result.pagination.offsets == (0, 1)
    assert result.pagination.complete is True


def test_round_qualifying_fetch_does_not_mark_repeated_page_offsets_complete(monkeypatch):
    pages = [
        {
            "total": "2",
            "offset": "0",
            "limit": "1",
            "RaceTable": {"Races": [_qualifying_race("driver_a", 1)]},
        },
        {
            "total": "2",
            "offset": "0",
            "limit": "1",
            "RaceTable": {"Races": [_qualifying_race("driver_b", 2)]},
        },
    ]
    monkeypatch.setattr(jolpica, "_iter_pages", lambda path: iter(pages))

    result = jolpica.get_qualifying_round(2026, 4)

    assert result.pagination.fetched_count == result.pagination.reported_total
    assert result.pagination.complete is False


def test_round_qualifying_fetch_advances_by_returned_page_limit(monkeypatch):
    calls = []

    def fake_get(path, params):
        calls.append((path, dict(params)))
        offset = params["offset"]
        driver = "driver_a" if offset == 0 else "driver_b"
        return {
            "MRData": {
                "total": "2",
                "offset": str(offset),
                "limit": "1",
                "RaceTable": {"Races": [_qualifying_race(driver, offset + 1)]},
            }
        }

    monkeypatch.setattr(jolpica, "_get", fake_get)

    result = jolpica.get_qualifying_round(2026, 4)

    assert [(path, params["offset"]) for path, params in calls] == [
        ("2026/4/qualifying", 0),
        ("2026/4/qualifying", 1),
    ]
    assert result.data["driver_id"].tolist() == ["driver_a", "driver_b"]
    assert result.pagination.complete is True


@pytest.mark.parametrize("returned_limit", ["0", "invalid"])
def test_page_iteration_rejects_non_positive_or_invalid_returned_limit(
    monkeypatch, returned_limit
):
    monkeypatch.setattr(
        jolpica,
        "_get",
        lambda path, params: {
            "MRData": {
                "total": "2",
                "offset": str(params["offset"]),
                "limit": returned_limit,
                "RaceTable": {"Races": []},
            }
        },
    )

    with pytest.raises(ValueError, match="page limit"):
        list(jolpica._iter_pages("2026/4/qualifying"))
