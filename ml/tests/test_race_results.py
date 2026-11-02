"""Recorded race results remain independent from immutable predictions."""
import json

import pandas as pd
import pytest

from src.publication.race_results import export_race_results
from streamlit_app.prediction_feed import FeedError, load_race_results


def test_export_is_round_scoped_and_leaves_frozen_prediction_untouched(tmp_path):
    raw, public = tmp_path / "raw", tmp_path / "public"
    raw.mkdir()
    (public / "predictions").mkdir(parents=True)
    frozen = public / "predictions/2026-18.json"
    frozen.write_text('{"frozen_at":"2026-10-25T18:00:00Z"}')
    original = frozen.read_bytes()
    rows = [dict(season=2026, round=round_number, position=1, driver_id="antonelli",
                 code="ANT", driver_name="Kimi Antonelli", constructor_id="mercedes",
                 constructor_name="Mercedes", points=25, laps=56, status="Finished")
            for round_number in (17, 18)]
    pd.DataFrame(rows).to_parquet(raw / "results_2026.parquet")
    index = {"races": [{"season": 2026, "round": 18}]}
    export_race_results(raw, public, index, dry_run=True)
    assert not (public / "predictions/2026-18-results.json").exists()
    export_race_results(raw, public, index, dry_run=False)
    result = load_race_results(public, base_url=None, race_id="2026-18")
    assert len(result["results"]) == 1
    assert frozen.read_bytes() == original


def test_wrong_event_result_feed_is_rejected(tmp_path):
    (tmp_path / "predictions").mkdir()
    path = tmp_path / "predictions/2026-18-results.json"
    path.write_text(json.dumps({"schema_version": 2, "race_id": "2026-17", "results": []}))
    with pytest.raises(FeedError, match="different event"):
        load_race_results(tmp_path, base_url=None, race_id="2026-18")
