"""Describe real live training inputs and runtime without hashing generated artifacts."""
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import platform
import subprocess

from src.features.common import sort_race_rows
from src.model.data import ML_DIR


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*arguments):
    try:
        return subprocess.check_output(
            ["git", "-C", str(ML_DIR.parent), *arguments], stderr=subprocess.DEVNULL,
            text=True, timeout=10,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def training_metadata(frame, *, cutoff, features, target, model_params, calibration=None):
    """Cache hashes cover full source files; training hash covers selected rows only.

    A missing lock or unavailable Git information is explicitly null. No metadata
    is reconstructed for old models or supplied mock models.
    """
    raw = ML_DIR / "data" / "raw"
    inputs = {
        table: {path.name: _sha256(path) for path in sorted(raw.glob(f"{table}_*.parquet"))}
        for table in ("results", "qualifying")
    }
    code_files = sorted(path for directory in (ML_DIR / "src", ML_DIR / "scripts")
                        for path in directory.rglob("*.py"))
    code_hash = hashlib.sha256()
    for path in code_files:
        code_hash.update(path.relative_to(ML_DIR.parent).as_posix().encode())
        code_hash.update(b"\0")
        code_hash.update(path.read_bytes())
        code_hash.update(b"\0")
    dirty = _git("status", "--porcelain", "--untracked-files=all", "--", "ml/src", "ml/scripts")
    lock = ML_DIR / "requirements-lock.txt"
    columns = ["season", "round", "driver_id", *features, target]
    training_json = sort_race_rows(frame)[columns].to_json(orient="split", index=False, double_precision=15)
    return {
        "training_cutoff": cutoff,
        "row_count": int(len(frame)),
        "race_count": int(len(frame[["season", "round"]].drop_duplicates())),
        "training_data_sha256": hashlib.sha256(training_json.encode()).hexdigest(),
        "input_data_sha256": inputs,
        "dependency_lock_sha256": _sha256(lock) if lock.exists() else None,
        "git_revision": _git("rev-parse", "HEAD"),
        "code_dirty": bool(dirty) if dirty is not None else None,
        "code_sha256": code_hash.hexdigest(),
        "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                    "libraries": {name: version(name) for name in
                                  ("lightgbm", "numpy", "pandas", "scikit-learn", "pyarrow",
                                   "scipy", "joblib", "threadpoolctl")}},
        "model_params": dict(model_params),
        "calibration": calibration,
        "features": list(features),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
