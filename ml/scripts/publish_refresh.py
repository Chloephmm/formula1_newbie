"""Fast-forward-only publisher for recurring non-candidate repository writers.

Prediction candidates use ``GitPublisher`` because eligibility needs remote-byte
confirmation.  This smaller publisher coordinates the Monday data/metrics refresh,
the stats refresh, and status-only monitor updates in the same Actions concurrency
group without staging unrelated working-tree changes or force-pushing.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
REMOTE = "origin"
BRANCH = "main"


def _git(*args: str, input_bytes: bytes | None = None, env=None) -> bytes:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT,
        input=input_bytes,
        env=env,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return result.stdout


def _allowed(kind: str, path: str) -> bool:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or "\\" in path:
        return False
    if kind == "stats":
        return path == "web/public/data/stats.json"
    if kind == "weekly":
        return bool(
            re.fullmatch(r"ml/data/raw/[A-Za-z0-9_-]+\.parquet", path)
            or path == "ml/models/live_metrics.json"
            or path == "web/public/data/next_race_prediction.json"
            or re.fullmatch(
                r"web/public/data/prediction_snapshots/[1-9][0-9]*-[1-9][0-9]*/"
                r"(?:event|status|final)\.json",
                path,
            )
        )
    if kind == "monitor":
        return bool(
            path == "web/public/data/prediction_feed.json"
            or re.fullmatch(
                r"web/public/data/prediction_snapshots/[1-9][0-9]*-[1-9][0-9]*/"
                r"(?:status|feed|final)\.json",
                path,
            )
            or re.fullmatch(
                r"web/public/data/prediction_snapshots/[1-9][0-9]*-[1-9][0-9]*/"
                r"checks/[0-9a-f]{64}\.json",
                path,
            )
        )
    raise ValueError(f"unsupported publication kind: {kind}")


def _dirty_paths(kind: str) -> list[str]:
    raw = _git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    records = [item for item in raw.split(b"\0") if item]
    paths: list[str] = []
    for record in records:
        if len(record) < 4:
            raise RuntimeError("malformed git status output")
        state = record[:2].decode("ascii", errors="strict")
        path = record[3:].decode("utf-8")
        if state[0] in {"R", "C"}:
            raise RuntimeError("renames/copies are not supported by the refresh publisher")
        normalized = Path(path).as_posix()
        if _allowed(kind, normalized):
            if "D" in state:
                raise RuntimeError(f"refresh publisher will not delete {normalized}")
            paths.append(normalized)
    return sorted(set(paths))


def _remote_head() -> str:
    _git("fetch", "--no-tags", REMOTE, f"refs/heads/{BRANCH}")
    return _git("rev-parse", "FETCH_HEAD").decode().strip()


def _remote_changed(base: str, head: str) -> set[str]:
    if base == head:
        return set()
    return set(
        _git("diff", "--name-only", "-z", base, head)
        .decode("utf-8")
        .rstrip("\0")
        .split("\0")
    ) - {""}


def _commit_on(parent: str, paths: list[str], message: str) -> str:
    with tempfile.TemporaryDirectory(prefix="f1-refresh-index-") as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
        _git("read-tree", parent, env=env)
        for path in paths:
            content = (ROOT / path).read_bytes()
            blob = _git("hash-object", "-w", "--stdin", input_bytes=content).decode().strip()
            _git(
                "update-index",
                "--add",
                "--cacheinfo",
                f"100644,{blob},{path}",
                env=env,
            )
        tree = _git("write-tree", env=env).decode().strip()
        current_tree = _git("rev-parse", f"{parent}^{{tree}}").decode().strip()
        if tree == current_tree:
            return parent
        return _git(
            "commit-tree", tree, "-p", parent, "-m", message
        ).decode().strip()


def publish_paths(kind: str, *, message: str | None = None) -> str | None:
    """Publish only the allowlisted dirty paths and return the new commit."""

    paths = _dirty_paths(kind)
    if not paths:
        print("Nothing changed.")
        return None
    base = _git("rev-parse", "HEAD").decode().strip()
    commit_message = message or {
        "weekly": "chore: weekly data + accuracy bar refresh [skip ci]",
        "stats": "chore: refresh F1 stats",
        "monitor": "chore: record qualifying monitor status [skip ci]",
    }[kind]
    for attempt in range(3):
        parent = _remote_head()
        overlap = _remote_changed(base, parent).intersection(paths)
        if overlap:
            joined = ", ".join(sorted(overlap))
            raise RuntimeError(f"remote changed the same refresh paths: {joined}")
        commit = _commit_on(parent, paths, commit_message)
        if commit == parent:
            print("Nothing changed against the current remote head.")
            return None
        try:
            _git("push", REMOTE, f"{commit}:refs/heads/{BRANCH}")
            print(f"Published {kind} refresh at {commit}.")
            return commit
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise RuntimeError("refresh publication conflict retry limit reached")
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", required=True, choices=("weekly", "stats", "monitor"))
    parser.add_argument("--message")
    args = parser.parse_args()
    publish_paths(args.kind, message=args.message)


if __name__ == "__main__":
    main()
