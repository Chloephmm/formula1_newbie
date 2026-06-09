"""Build the model-ready feature table from cached raw data.

Run from the ml/ directory:
    python scripts/build_features.py

Reads ml/data/raw/*.parquet, writes ml/data/processed/features.parquet.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # add ml/ to sys.path

from src.features.build_features import main  # noqa: E402

if __name__ == "__main__":
    main()
