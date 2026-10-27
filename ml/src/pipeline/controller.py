"""Small, pure-ish actual-forecast generation seam.

Scheduling, fetching, hashing, persistence, Git, and publication deliberately remain
outside this module. ``input_hash`` is caller-supplied pending the artifact contract;
it is only a reuse dependency boundary, not proof of publication or provenance.
"""
from __future__ import annotations

from collections.abc import Mapping

from src.model.forecast import (
    _event_cutoff,
    _event_identity,
    _forecast_prepared,
    _prepare_forecast_inputs,
)
from src.model.retrain import train_podium_live


def _same_successful_context(previous, *, event, cutoff, qualifying, input_hash):
    if not isinstance(previous, Mapping):
        return False
    season, round_number = _event_identity(event)
    return (
        previous.get("status") == "success"
        and previous.get("mode") == "actual_qualifying"
        and previous.get("event") == {"season": season, "round": round_number}
        and previous.get("training_cutoff") == cutoff.isoformat()
        and previous.get("qualifying_source_version") == qualifying.source_version
        and previous.get("input_hash") == input_hash
        and isinstance(previous.get("forecast"), Mapping)
    )


def generate_actual_candidate(
    event, *, history, entries, qualifying, input_hash, previous_candidate=None
):
    """Validate inputs, reuse an unchanged success, or fit Stage 2 once.

    The supplied hash is intentionally not generated or interpreted here. Task 5 owns
    canonical hashing and immutable artifact metadata.
    """

    if not isinstance(input_hash, str) or not input_hash:
        raise ValueError("input_hash must be a non-empty caller-supplied value")
    prepared, features, actual_rows = _prepare_forecast_inputs(
        event, mode="actual_qualifying", history=history, entries=entries,
        qualifying=qualifying,
    )
    cutoff = _event_cutoff(event)
    if _same_successful_context(
        previous_candidate, event=event, cutoff=cutoff,
        qualifying=qualifying, input_hash=input_hash,
    ):
        return previous_candidate

    season, round_number = _event_identity(event)
    podium_model = train_podium_live(
        cutoff,
        results=prepared["results"], qualifying=prepared["qualifying"],
        target_season=season, target_round=round_number,
    )
    result = _forecast_prepared(
        event, mode="actual_qualifying", features=features,
        models={"podium": podium_model}, actual_rows=actual_rows,
    )
    return {
        "status": "success",
        "mode": "actual_qualifying",
        "event": {"season": season, "round": round_number},
        "training_cutoff": cutoff.isoformat(),
        "qualifying_source_version": qualifying.source_version,
        "input_hash": input_hash,
        "forecast": result,
    }
