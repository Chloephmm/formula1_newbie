"""Parquet cache for Jolpica pulls.

Fetch from the API only when the cached file is missing (or ``refresh=True``).
This keeps re-runs instant and avoids hammering the free API. Cache files live in
``ml/data/raw/`` (gitignored).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

# ml/src/data/cache.py -> parents[2] == ml/
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def cached(name: str, builder: Callable[[], pd.DataFrame], refresh: bool = False) -> pd.DataFrame:
    """Return cached DataFrame ``name``; build + persist it if missing.

    Args:
        name:    file stem, e.g. ``"results_2023"`` -> ``data/raw/results_2023.parquet``
        builder: zero-arg callable that produces the DataFrame on a cache miss
        refresh: if True, ignore any existing cache and rebuild
    """
    path = RAW_DIR / f"{name}.parquet"
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    df = builder()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df
