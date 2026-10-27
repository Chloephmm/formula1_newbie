"""Fetch and validate one exact Formula 1 Grand Prix qualifying session.

Fetching is deliberately side-effect free: raw pages and retrieval metadata are
returned with normalized rows, and no cache is changed until a caller separately
merges an accepted validation result.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from src.data import jolpica
from src.pipeline.events import EventContractError, roster_version, validate_roster_record


SOURCE_COLUMNS = (
    "season",
    "round",
    "race_name",
    "circuit_id",
    "driver_id",
    "code",
    "constructor_id",
    "quali_position",
    "q1",
    "q2",
    "q3",
)
MAX_QUALIFYING_PAGES = 1_000


class QualifyingValidationError(ValueError):
    """A fetched event cannot be accepted without guessing."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.reason_code = code


@dataclass
class PageEvidence:
    """Raw provider pages kept separately from non-semantic retrieval metadata."""

    source_pages: tuple[dict[str, Any], ...]
    retrieval_metadata: list[dict[str, Any]]


@dataclass
class QualifyingFetch:
    """Untrusted fetch result; callers must pass it through validation."""

    rows: pd.DataFrame
    page_evidence: PageEvidence

    @property
    def source_pages(self) -> tuple[dict[str, Any], ...]:
        return self.page_evidence.source_pages

    @property
    def retrieval_metadata(self) -> list[dict[str, Any]]:
        return self.page_evidence.retrieval_metadata


@dataclass
class AcceptedQualifying:
    """Validated data suitable for a later, explicit cache merge."""

    rows: pd.DataFrame
    roster: pd.DataFrame
    source_version: str
    notes: tuple[str, ...]
    imputation_policy: dict[str, str]


def _fail(code: str, message: str) -> None:
    raise QualifyingValidationError(code, message)


def _pagination_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        _fail("malformed_pagination", f"pagination {field} must be an integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        _fail("malformed_pagination", f"pagination {field} must be an integer")
    if parsed < 0 or (field == "limit" and parsed == 0):
        _fail("malformed_pagination", f"pagination {field} is out of range")
    return parsed


def _mrdata(page: Mapping[str, Any]) -> Mapping[str, Any]:
    mrdata = page.get("MRData") if isinstance(page, Mapping) else None
    if not isinstance(mrdata, Mapping):
        _fail("malformed_response", "provider page is missing MRData")
    return mrdata


def _rows_from_pages(pages: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for page in pages:
        mrdata = _mrdata(page)
        table = mrdata.get("RaceTable")
        if not isinstance(table, Mapping):
            continue
        races = table.get("Races")
        if not isinstance(races, list):
            continue
        for race in races:
            if not isinstance(race, Mapping):
                continue
            circuit = race.get("Circuit")
            circuit_id = circuit.get("circuitId") if isinstance(circuit, Mapping) else None
            results = race.get("QualifyingResults")
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, Mapping):
                    continue
                driver = result.get("Driver")
                constructor = result.get("Constructor")
                rows.append(
                    {
                        "season": race.get("season"),
                        "round": race.get("round"),
                        "race_name": race.get("raceName"),
                        "circuit_id": circuit_id,
                        "driver_id": (
                            driver.get("driverId") if isinstance(driver, Mapping) else None
                        ),
                        "code": driver.get("code") if isinstance(driver, Mapping) else None,
                        "constructor_id": (
                            constructor.get("constructorId")
                            if isinstance(constructor, Mapping)
                            else None
                        ),
                        "quali_position": result.get("position"),
                        "q1": result.get("Q1"),
                        "q2": result.get("Q2"),
                        "q3": result.get("Q3"),
                    }
                )
    frame = pd.DataFrame(rows, columns=SOURCE_COLUMNS)
    for column in ("season", "round"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def fetch_target_qualifying(
    season: int,
    round_number: int,
    get_page: Callable[[str, dict[str, int]], Mapping[str, Any]] | None = None,
) -> QualifyingFetch:
    """Fetch only ``/{season}/{round}/qualifying`` using bounded pagination."""

    if (
        isinstance(season, bool)
        or not isinstance(season, int)
        or season <= 0
        or isinstance(round_number, bool)
        or not isinstance(round_number, int)
        or round_number <= 0
    ):
        _fail("invalid_target", "season and round must be explicit positive integers")
    request_page = get_page or jolpica._get
    path = f"{season}/{round_number}/qualifying"
    offset = 0
    request_limit = jolpica.PAGE_SIZE
    source_pages: list[dict[str, Any]] = []
    retrieval_metadata: list[dict[str, Any]] = []
    first_limit: int | None = None
    first_total: int | None = None

    for _ in range(MAX_QUALIFYING_PAGES):
        params = {"limit": request_limit, "offset": offset}
        payload = request_page(path, params)
        page = copy.deepcopy(payload)
        mrdata = _mrdata(page)
        returned_limit = _pagination_int(mrdata.get("limit"), "limit")
        returned_total = _pagination_int(mrdata.get("total"), "total")
        returned_offset = _pagination_int(mrdata.get("offset"), "offset")
        source_pages.append(page)
        retrieval_metadata.append(
            {
                "requested_path": path,
                "requested_limit": request_limit,
                "requested_offset": offset,
                "returned_offset": returned_offset,
                "retrieved_at": datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
            }
        )
        if first_limit is None:
            first_limit = returned_limit
            first_total = returned_total
            request_limit = returned_limit
            inconsistent = returned_offset != offset
        else:
            inconsistent = (
                returned_limit != first_limit
                or returned_total != first_total
                or returned_offset != offset
            )
        if inconsistent:
            break
        offset += request_limit
        if offset >= first_total:
            break
    else:
        _fail("malformed_pagination", "qualifying pagination exceeded its safety bound")

    preserved_pages = tuple(copy.deepcopy(source_pages))
    evidence = PageEvidence(
        source_pages=preserved_pages,
        retrieval_metadata=copy.deepcopy(retrieval_metadata),
    )
    return QualifyingFetch(rows=_rows_from_pages(preserved_pages), page_evidence=evidence)


def _validate_pages(
    event: Mapping[str, Any], page_evidence: PageEvidence
) -> tuple[list[Mapping[str, Any]], int]:
    pages = page_evidence.source_pages
    metadata = page_evidence.retrieval_metadata
    if not pages or len(pages) != len(metadata):
        _fail("malformed_pagination", "raw pages and retrieval metadata do not align")

    parsed: list[tuple[int, int, int]] = []
    result_count = 0
    page_counts: list[int] = []
    expected_path = f"{event.get('season')}/{event.get('round')}/qualifying"
    for index, (page, retrieval) in enumerate(zip(pages, metadata)):
        mrdata = _mrdata(page)
        if mrdata.get("series") != "f1":
            _fail("wrong_series", "qualifying evidence is not Formula 1")
        limit = _pagination_int(mrdata.get("limit"), "limit")
        offset = _pagination_int(mrdata.get("offset"), "offset")
        total = _pagination_int(mrdata.get("total"), "total")
        parsed.append((limit, offset, total))

        table = mrdata.get("RaceTable")
        if not isinstance(table, Mapping):
            _fail("wrong_event", "qualifying evidence is missing RaceTable filters")
        try:
            table_season = int(table.get("season"))
            table_round = int(table.get("round"))
        except (TypeError, ValueError) as exc:
            raise QualifyingValidationError(
                "wrong_event", "RaceTable has malformed event filters"
            ) from exc
        if table_season != int(event.get("season")) or table_round != int(
            event.get("round")
        ):
            _fail("wrong_event", "RaceTable filters do not match the target event")

        races = table.get("Races")
        if not isinstance(races, list):
            _fail("malformed_response", "RaceTable Races must be a list")
        page_count = 0
        for race in races:
            if not isinstance(race, Mapping):
                _fail("malformed_response", "race evidence must be an object")
            circuit = race.get("Circuit")
            try:
                same_identity = (
                    int(race.get("season")) == int(event.get("season"))
                    and int(race.get("round")) == int(event.get("round"))
                    and isinstance(circuit, Mapping)
                    and circuit.get("circuitId") == event.get("circuit_id")
                    and race.get("raceName") == event.get("race_name")
                )
            except (TypeError, ValueError):
                same_identity = False
            if not same_identity:
                _fail("wrong_event", "race evidence does not match the target event")
            if "QualifyingResults" not in race or not isinstance(
                race.get("QualifyingResults"), list
            ):
                _fail("wrong_session", "evidence is not Grand Prix QualifyingResults")
            if any(
                not isinstance(result, Mapping)
                for result in race["QualifyingResults"]
            ):
                _fail("malformed_response", "qualifying results must be objects")
            for result in race["QualifyingResults"]:
                for timing_field in ("Q1", "Q2", "Q3"):
                    timing = result.get(timing_field)
                    if (
                        timing_field in result
                        and timing is not None
                        and not isinstance(timing, str)
                    ):
                        _fail(
                            "invalid_lap_time",
                            "present raw qualifying times must be strings",
                        )
            page_count += len(race["QualifyingResults"])
        result_count += page_count
        page_counts.append(page_count)

        if retrieval.get("requested_path") != expected_path:
            _fail("wrong_endpoint", "page evidence was not fetched from target qualifying")
        if retrieval.get("requested_offset") != offset:
            _fail("noncontiguous_pagination", "requested and returned offsets differ")
        if index and retrieval.get("requested_limit") != parsed[0][0]:
            _fail("changing_pagination", "requests did not use the first provider limit")

    first_limit, _, first_total = parsed[0]
    if any(limit != first_limit or total != first_total for limit, _, total in parsed[1:]):
        _fail("changing_pagination", "provider limit or total changed between pages")
    expected_offsets = list(range(0, first_total, first_limit)) or [0]
    actual_offsets = [offset for _, offset, _ in parsed]
    if actual_offsets != expected_offsets:
        _fail("noncontiguous_pagination", "qualifying page offsets are incomplete or extra")
    if result_count != first_total:
        _fail(
            "incomplete_pagination",
            f"qualifying pages contain {result_count} of {first_total} declared results",
        )
    expected_counts = [min(first_limit, first_total - offset) for offset in expected_offsets]
    if page_counts != expected_counts:
        _fail("malformed_page_count", "qualifying page result counts are inconsistent")
    return list(pages), first_total


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _json_value(value: Any) -> Any:
    if _missing(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        if value.is_integer():
            return int(value)
    return value


def _source_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    missing_columns = [column for column in SOURCE_COLUMNS if column not in frame.columns]
    if missing_columns:
        _fail(
            "rows_do_not_match_evidence",
            f"normalized rows are missing source columns: {', '.join(missing_columns)}",
        )
    records = [
        {column: _json_value(row[column]) for column in SOURCE_COLUMNS}
        for _, row in frame.loc[:, SOURCE_COLUMNS].iterrows()
    ]
    records.sort(
        key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":"))
    )
    return records


def _positive_position(value: Any) -> int | None:
    if _missing(value):
        return None
    if isinstance(value, bool):
        _fail("invalid_position", "qualifying positions must be positive integers")
    if isinstance(value, str):
        text = value.strip()
        if not text.isdigit():
            _fail("invalid_position", "qualifying positions must be positive integers")
        position = int(text)
    elif isinstance(value, int):
        position = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        position = int(value)
    else:
        _fail("invalid_position", "qualifying positions must be positive integers")
    if position <= 0:
        _fail("invalid_position", "qualifying positions must be positive integers")
    return position


def _lap_seconds(value: Any) -> float | None:
    if _missing(value):
        return None
    if not isinstance(value, str) or not value.strip():
        _fail("invalid_lap_time", "present qualifying times must be non-empty strings")
    parsed = jolpica.laptime_to_seconds(value)
    if parsed is None or not math.isfinite(parsed) or parsed <= 0:
        _fail("invalid_lap_time", f"invalid qualifying time: {value!r}")
    return float(parsed)


def _normalized_roster(event: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str]:
    roster = event.get("roster")
    if not isinstance(roster, list):
        _fail("invalid_roster", "event roster must be a list")
    try:
        normalized = [validate_roster_record(record) for record in roster]
        version = roster_version(normalized)
    except EventContractError as exc:
        raise QualifyingValidationError(exc.code, str(exc)) from exc
    return normalized, version


def _semantic_hash(
    event: Mapping[str, Any],
    rows: pd.DataFrame,
    semantic_roster_version: str,
) -> str:
    semantic_rows = []
    for record in _source_records(rows):
        semantic_row = {
            key: value
            for key, value in record.items()
            if key not in {"q1", "q2", "q3"}
        }
        for timing_field in ("q1", "q2", "q3"):
            semantic_row[f"{timing_field}_seconds"] = _lap_seconds(
                record[timing_field]
            )
        semantic_row["model_position"] = _json_value(
            rows.loc[
                rows["driver_id"] == record["driver_id"], "model_position"
            ].iloc[0]
        )
        semantic_rows.append(semantic_row)
    semantic_rows.sort(key=lambda row: str(row["driver_id"]))
    payload = {
        "event": {
            "season": int(event["season"]),
            "round": int(event["round"]),
            "race_name": event.get("race_name"),
            "circuit_id": event.get("circuit_id"),
        },
        "rows": semantic_rows,
        "roster_version": semantic_roster_version,
        "imputation_policy": {"no_lap_model_gap": "largest_valid_event_gap"},
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_qualifying(
    event: Mapping[str, Any],
    rows: pd.DataFrame,
    page_evidence: PageEvidence,
) -> AcceptedQualifying:
    """Validate completeness, exact event identity, roster, positions, and timing."""

    if not isinstance(event, Mapping) or not isinstance(rows, pd.DataFrame):
        _fail("invalid_input", "event and normalized rows have invalid types")
    pages, declared_total = _validate_pages(event, page_evidence)
    evidence_rows = _rows_from_pages(pages)
    if len(evidence_rows) != declared_total:
        _fail(
            "malformed_response",
            "normalized qualifying rows do not cover every declared result",
        )
    if _source_records(rows) != _source_records(evidence_rows):
        _fail("rows_do_not_match_evidence", "normalized rows differ from raw evidence")
    if declared_total == 0 or evidence_rows.empty:
        _fail("qualifying_unavailable", "no qualifying results are available")

    roster, semantic_roster_version = _normalized_roster(event)
    roster_by_id = {record["driver_id"]: record for record in roster}
    driver_ids = evidence_rows["driver_id"].tolist()
    if any(not isinstance(driver_id, str) or not driver_id for driver_id in driver_ids):
        _fail("malformed_response", "every qualifying result requires a driver id")
    if len(driver_ids) != len(set(driver_ids)):
        _fail("duplicate_driver", "qualifying results contain duplicate drivers")
    unknown = sorted(set(driver_ids) - set(roster_by_id))
    if unknown:
        _fail("unknown_driver", f"qualifying contains unknown drivers: {unknown}")
    expected = {record["driver_id"] for record in roster if record["expected"]}
    missing_expected = sorted(expected - set(driver_ids))
    if missing_expected:
        _fail(
            "missing_expected_driver",
            f"qualifying is missing expected drivers: {missing_expected}",
        )

    accepted = evidence_rows.copy(deep=True)
    official_positions: list[int | None] = []
    model_positions: list[int | None] = []
    best_times: list[float | None] = []
    eligible_values: list[bool] = []
    seen_official: set[int] = set()
    seen_model: set[int] = set()

    for _, row in accepted.iterrows():
        roster_record = roster_by_id[row["driver_id"]]
        if row["constructor_id"] != roster_record["constructor_id"]:
            _fail(
                "constructor_mismatch",
                f"constructor does not match roster for {row['driver_id']}",
            )
        official = _positive_position(row["quali_position"])
        if official is not None:
            if official in seen_official:
                _fail("duplicate_position", "classified positions must be unique")
            seen_official.add(official)

        parsed_times = [_lap_seconds(row[column]) for column in ("q1", "q2", "q3")]
        valid_times = [value for value in parsed_times if value is not None]
        best_times.append(min(valid_times) if valid_times else None)
        eligible = bool(roster_record["eligible"])
        eligible_values.append(eligible)

        model_position = official
        if official is None and eligible:
            exception = roster_record.get("exception")
            if not exception or exception.get("kind") != "no_qualifying_lap":
                _fail(
                    "unclassified_driver",
                    f"{row['driver_id']} lacks an official qualifying classification",
                )
            if not exception.get("allow_model_position"):
                _fail(
                    "unclassified_driver",
                    f"{row['driver_id']} has no authorized model position",
                )
            model_position = exception.get("model_position")
            if model_position is None:
                _fail(
                    "missing_model_position",
                    f"{row['driver_id']} needs an explicit model position",
                )
        if eligible and model_position is not None:
            if model_position in seen_model:
                _fail(
                    "duplicate_model_position",
                    "modeled qualifying positions must be unique",
                )
            seen_model.add(model_position)
        model_positions.append(model_position if eligible else None)
        official_positions.append(official)

    valid_event_times = [value for value in best_times if value is not None]
    if not valid_event_times:
        _fail("no_valid_lap_times", "qualifying has no valid event timing")
    pole_time = min(valid_event_times)
    actual_gaps = [
        (value - pole_time if value is not None else None) for value in best_times
    ]
    largest_gap = max(gap for gap in actual_gaps if gap is not None)
    model_gaps = [gap if gap is not None else largest_gap for gap in actual_gaps]

    accepted["quali_position"] = pd.array(official_positions, dtype="Int64")
    accepted["best_qualifying_time_seconds"] = best_times
    accepted["quali_time_gap_to_pole"] = actual_gaps
    accepted["model_quali_time_gap_to_pole"] = model_gaps
    accepted["model_position"] = pd.array(model_positions, dtype="Int64")
    accepted["eligible"] = eligible_values
    accepted = accepted.sort_values("driver_id").reset_index(drop=True)
    canonical_roster = pd.DataFrame(copy.deepcopy(roster)).sort_values(
        "driver_id"
    ).reset_index(drop=True)
    source_version = _semantic_hash(event, accepted, semantic_roster_version)
    no_lap_count = sum(value is None for value in best_times)
    notes = (
        f"accepted {len(accepted)} qualifying result rows",
        f"retained {no_lap_count} classified or authorized entrants without a lap",
    )
    return AcceptedQualifying(
        rows=accepted,
        roster=canonical_roster,
        source_version=source_version,
        notes=notes,
        imputation_policy={"no_lap_model_gap": "largest_valid_event_gap"},
    )


def replace_target_rows(
    existing: pd.DataFrame,
    accepted: pd.DataFrame,
    season: int,
    round_number: int,
) -> pd.DataFrame:
    """Purely replace one validated event while preserving every other event."""

    required = {"season", "round", "driver_id"}
    if not required.issubset(accepted.columns):
        if accepted.empty:
            _fail("empty_accepted_rows", "accepted qualifying rows cannot be empty")
        _fail("mixed_event_rows", "accepted rows are missing event identity columns")
    target = (accepted["season"] == season) & (accepted["round"] == round_number)
    if not bool(target.all()):
        _fail("mixed_event_rows", "accepted rows contain more than one event")
    if accepted.empty:
        _fail("empty_accepted_rows", "accepted qualifying rows cannot be empty")
    if accepted.duplicated(["season", "round", "driver_id"]).any():
        _fail("duplicate_accepted_rows", "accepted rows contain duplicate drivers")

    existing_copy = existing.copy(deep=True)
    if required.issubset(existing_copy.columns):
        existing_target = (existing_copy["season"] == season) & (
            existing_copy["round"] == round_number
        )
        other_rows = existing_copy.loc[~existing_target].copy()
    else:
        other_rows = existing_copy
    merged = pd.concat([other_rows, accepted.copy(deep=True)], ignore_index=True, sort=False)
    merged = merged.sort_values(["season", "round", "driver_id"]).reset_index(drop=True)

    if not other_rows.empty:
        preserved = merged.loc[
            ~((merged["season"] == season) & (merged["round"] == round_number)),
            other_rows.columns,
        ].reset_index(drop=True)
        pd.testing.assert_frame_equal(
            preserved,
            other_rows.sort_values(["season", "round", "driver_id"]).reset_index(drop=True),
            check_dtype=False,
        )
    return merged
