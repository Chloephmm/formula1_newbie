"""Shared status semantics and canonical race/driver row order."""
import pandas as pd


def is_finished(status: pd.Series) -> pd.Series:
    """Recognize classified finishes; unknown or missing statuses count as DNFs."""
    normalized = status.fillna("").astype(str).str.strip().str.lower()
    return normalized.str.fullmatch(r"finished|lapped|\+\s*\d+\s+laps?", na=False)


def sort_race_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Stable chronological order, with driver ID as the within-race tie breaker."""
    keys = [key for key in ("season", "round", "driver_id") if key in frame]
    return frame.sort_values(keys, kind="stable").reset_index(drop=True)
