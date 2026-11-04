"""Stage a validated candidate or safely publish an estimated prediction.

Default Monday behavior writes only the active compatibility snapshot. Candidate
mode never modifies the feed. --publish-candidate synchronizes all four interfaces
for the current active race without retraining. --refresh-schedule fetches only
the calendar, leaving race results and qualifying training data untouched.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml"))

from src.data.jolpica import get_schedule  # noqa: E402
from src.model.forecast import forecast, next_race  # noqa: E402
from src.model.retrain import retrain_live  # noqa: E402
from src.publication.estimated import (  # noqa: E402
    ensure_estimated_publishable, make_candidate, publish_candidate, validate_schedule,
)
from src.publication.service import PublicationPaths, _atomic_json, read_json  # noqa: E402

DATA_ROOT = ROOT / "web" / "public" / "data"
RAW_ROOT = ROOT / "ml" / "data" / "raw"


def expected_codes(raw_dir: Path, schedule: dict) -> set[str]:
    results = pd.concat([pd.read_parquet(p) for p in sorted(raw_dir.glob("results_*.parquet"))])
    dates = pd.to_datetime(results["date"], utc=True, errors="coerce")
    results = results[dates < pd.Timestamp(schedule["race_start_at"]).normalize()]
    if results.empty:
        raise ValueError("no completed race before target")
    latest = results.sort_values(["season", "round"]).iloc[-1]
    entrants = results[(results.season == latest.season) & (results["round"] == latest["round"])]
    if entrants.driver_id.duplicated().any() or entrants.code.isna().any() or entrants.code.duplicated().any():
        raise ValueError("expected participants have duplicate or missing identities")
    return set(entrants.code)


def refresh_schedule(season: int, round_number: int, *, raw_dir: Path = RAW_ROOT) -> None:
    schedule = get_schedule(season)
    selected = schedule[(schedule.season == season) & (schedule["round"] == round_number)]
    if len(selected) != 1:
        raise ValueError("refreshed schedule does not contain exactly one target event")
    validate_schedule(selected.iloc[0].to_dict())
    path = raw_dir / f"schedule_{season}.parquet"
    temporary = path.with_suffix(".parquet.tmp")
    try:
        schedule.to_parquet(temporary, index=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(asof: str, *, candidate_output: Path | None = None,
         publish_from: Path | None = None, refresh: bool = False,
         clock=lambda: datetime.now(timezone.utc)) -> dict:
    paths = PublicationPaths(DATA_ROOT)
    tgt = next_race(asof)
    if tgt is None:
        raise ValueError(f"No race on/after {asof} in cached schedule")
    identity = (int(tgt.season), int(tgt["round"]))
    if refresh:
        refresh_schedule(*identity)
        tgt = next_race(asof)
        if tgt is None or (int(tgt.season), int(tgt["round"])) != identity:
            raise ValueError("target changed after schedule refresh; inspect the calendar before retrying")
    schedule = tgt.to_dict()
    timing = validate_schedule(schedule)
    season, rnd = identity
    codes = expected_codes(RAW_ROOT, schedule)
    if candidate_output and candidate_output.resolve().is_relative_to(DATA_ROOT.resolve()):
        raise ValueError("candidate output must be outside the published feed")
    if publish_from:
        candidate = read_json(publish_from)
        if candidate is None:
            raise ValueError("candidate file does not exist")
        publish_candidate(paths, candidate, schedule, codes, clock=clock)
        print(f"Published validated candidate for {candidate['race_id']}")
        return candidate
    if candidate_output is None:
        ensure_estimated_publishable(paths, f"{season}-{rnd}", timing, clock(), require_active=False)
    print(f"Training candidate: {schedule['race_name']} ({season}-{rnd})", flush=True)
    cutoff = pd.Timestamp(schedule["race_start_at"]).date().isoformat()
    models = retrain_live(cutoff, season, rnd)
    candidate = make_candidate(forecast(asof, models=models), schedule, codes, clock())
    if candidate_output:
        _atomic_json(candidate_output, candidate)
        print(f"Candidate only: {candidate_output}")
    else:
        publish_candidate(paths, candidate, schedule, codes, clock=clock, active_only=True)
        print(f"Wrote {paths.active}")
    for row in candidate["forecast"]["preQualifyingPodium"][:5]:
        print(f"  {row['code']}: {row['podiumProbability']:.2%}")
    return candidate


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asof", default=datetime.now(timezone.utc).date().isoformat())
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--candidate-output", type=Path)
    group.add_argument("--publish-candidate", type=Path)
    parser.add_argument("--refresh-schedule", action="store_true")
    args = parser.parse_args()
    main(args.asof, candidate_output=args.candidate_output,
         publish_from=args.publish_candidate, refresh=args.refresh_schedule)
