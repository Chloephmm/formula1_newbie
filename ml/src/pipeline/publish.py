"""Confirm immutable saved output before selecting it in the public feed.

``stage_candidate`` writes only a private directory. ``GitPublisher`` commits
immutable candidate files using a private index, pushes with fast-forward checks,
then asks the injected *saved-output transport* for the exact committed bytes.
The transport signature is ``reader(commit, repository_path, timeout=seconds)``;
production must use the same HTTP origin/path as the page, pinned to ``commit``.
Reading the local checkout is not publication evidence.

Feed schema 1 is one atomic JSON revision: ``revision`` (SHA-256 of all other
fields), ``feed_updated_at`` (revision creation, NOT delivery or eligibility),
``event`` (full canonical event),
``current_event_id`` (season-round), ``status``, and ``current``, ``previous``,
``initial``. Each non-null selection embeds its original ``event`` context,
``prediction`` (artifact schema 2) and ``publication`` (receipt schema 1).
Previous/initial always belong to the same
event. ``initial`` is the first *confirmed* initial, never a reconstructed model.
Status-only writers may preserve these selections verbatim. Historical readers
can read the corresponding event's ``feed.json`` using the identical schema.

All repository writers must also share the workflow's writer concurrency group.
The local exclusive lock prevents overlapping writers in one checkout; Git's
fast-forward check protects against other checkouts. No worktree/index reset,
force push, or automatic rebase is used. A changed semantic context requires a
new plan; only disjoint changes can be replayed (at most two conflict retries).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from typing import Any

from .artifacts import (
    ArtifactCollisionError, canonical_bytes, digest, validate_prediction,
    write_immutable,
)
from .events import event_windows, parse_utc, roster_version, schedule_hash
from .state import _is_frozen


DATA = "web/public/data"
FEED_PATH = f"{DATA}/prediction_feed.json"
COMPATIBILITY_PATH = f"{DATA}/next_race_prediction.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


class PublicationError(RuntimeError):
    """An attempt failed or remains uncertain; preserve existing confirmation evidence."""


class ReplanRequired(PublicationError):
    """The candidate's original event/source/publication context changed."""


def _identity(event: Mapping[str, Any]) -> tuple[int, int]:
    values = event.get("season"), event.get("round")
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
           for value in values):
        raise ValueError("event identity requires positive integer season and round")
    return values


def _event_path(event: Mapping[str, Any]) -> str:
    season, round_number = _identity(event)
    return f"{DATA}/prediction_snapshots/{season}-{round_number}"


def _text(value: str | datetime) -> str:
    # Keep microseconds: rounding a verification backwards could create eligibility.
    return parse_utc(value).isoformat().replace("+00:00", "Z")


def _encoded(value: Any) -> bytes:
    return canonical_bytes(value) + b"\n"


def _checksum(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _remaining(clock: Callable, deadline: datetime) -> float:
    remaining = (deadline - parse_utc(clock())).total_seconds()
    if remaining <= 0:
        raise PublicationError("publication deadline reached")
    return remaining


def _deadline(event, mode):
    cutoff = event_windows(event)["cutoff_at"]
    return min(cutoff, parse_utc(event["qualifying_start_at"])) if mode == "predicted_qualifying" else cutoff


@dataclass(frozen=True)
class Candidate:
    directory: Path
    event: dict
    prediction: dict
    expected_current_id: str | None
    expected_source_version: str | None
    expected_feed_event_id: str
    expected_file_checksums: dict[str, str | None]
    files: dict[str, bytes]

    @property
    def version_path(self) -> str:
        return f"{_event_path(self.event)}/versions/{self.prediction['prediction_id']}.json"


def stage_candidate(
    private_root: str | Path, event: Mapping, prediction: Mapping, *,
    expected_current_id: str | None = None,
    expected_source_version: str | None = None,
    expected_feed_event_id: str | None = None,
    expected_file_checksums: Mapping[str, str | None] | None = None,
    files: Mapping[str, bytes] | None = None,
) -> Candidate:
    """Validate and stage a candidate without touching any served file.

    Expected fields are the pre-generation remote baseline, not the new source.
    Rollover must name the previous global feed event explicitly. Mutable raw
    files require baseline byte checksums (None means the path was absent).
    Additional bytes may include raw qualifying Parquet and this event's immutable
    source/check evidence. Feed, status, initial and final paths are reserved.
    The caller owns cleanup of the returned private staging directory.
    """
    event, prediction = copy.deepcopy(dict(event)), copy.deepcopy(dict(prediction))
    validate_prediction(prediction, event)
    for value in (expected_current_id, expected_source_version):
        if value is not None and not SHA256.fullmatch(value):
            raise ValueError("expected context versions must be SHA-256 digests")
    baseline = dict(expected_file_checksums or {})
    extra = {}
    for path, content in (files or {}).items():
        parsed = PurePosixPath(path)
        permitted = (
            re.fullmatch(r"ml/data/raw/qualifying_\d{4}\.parquet", path)
            or path.startswith(f"{_event_path(event)}/sources/")
            or path.startswith(f"{_event_path(event)}/checks/")
        )
        if not permitted or parsed.is_absolute() or ".." in parsed.parts or "\\" in path:
            raise ValueError(f"candidate file path is not permitted: {path}")
        if not isinstance(content, bytes):
            raise TypeError("candidate file content must be bytes")
        if path.startswith("ml/data/raw/") and path not in baseline:
            raise ValueError("mutable candidate file requires a baseline checksum")
        extra[path] = content
    if set(baseline) - set(extra) or any(value is not None and not SHA256.fullmatch(value)
                                       for value in baseline.values()):
        raise ValueError("invalid candidate baseline checksums")
    feed_event_id = expected_feed_event_id or f"{event['season']}-{event['round']}"
    if not re.fullmatch(r"[1-9][0-9]*-[1-9][0-9]*", feed_event_id):
        raise ValueError("invalid expected feed event identity")
    root = Path(private_root)
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="publication-", dir=root))
    write_immutable(directory / "prediction.json", prediction)
    write_immutable(directory / "page.json", _compatibility(prediction, None))
    for path, content in extra.items():
        target = directory / "files" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    candidate = Candidate(directory, event, prediction, expected_current_id,
                          expected_source_version, feed_event_id, baseline, extra)
    write_immutable(directory / "context.json", _stage_context(candidate))
    return candidate


def _stage_context(candidate):
    return {
        "event": candidate.event, "expected_current_id": candidate.expected_current_id,
        "expected_source_version": candidate.expected_source_version,
        "expected_feed_event_id": candidate.expected_feed_event_id,
        "expected_file_checksums": candidate.expected_file_checksums,
        "extra_checksums": {path: _checksum(value) for path, value in candidate.files.items()},
    }


def _receipt_id(receipt):
    return digest({key: value for key, value in receipt.items() if key != "publication_id"})


def _valid_receipt(receipt: Mapping) -> bool:
    try:
        _identity(receipt)
        mode = receipt["mode"]
        if mode not in {"predicted_qualifying", "actual_qualifying"}:
            return False
        published = parse_utc(receipt["published_at"])
        eligible = published < parse_utc(receipt["cutoff_at"])
        if mode == "predicted_qualifying":
            eligible &= published < parse_utc(receipt["qualifying_start_at"])
            if "qualifying_source_version" not in receipt or receipt["qualifying_source_version"] is not None:
                return False
        elif not SHA256.fullmatch(receipt["qualifying_source_version"]):
            return False
        return (
            type(receipt.get("schema_version")) is int and receipt["schema_version"] == 1
            and receipt.get("confirmed") is True
            and eligible and COMMIT.fullmatch(receipt["commit"]) is not None
            and all(SHA256.fullmatch(receipt[field]) for field in (
                "prediction_id", "checksum", "event_schedule_hash", "roster_version"))
            and receipt["publication_id"] == _receipt_id(receipt)
            and receipt["version_path"] == f"{_event_path(receipt)}/versions/{receipt['prediction_id']}.json"
        )
    except (KeyError, TypeError, ValueError):
        return False


def _validate_selection(selection, target):
    """Check retained bytes using their original event, including old schedules."""
    if selection is None:
        return
    try:
        event, prediction, receipt = (selection[key] for key in ("event", "prediction", "publication"))
        validate_prediction(prediction, event)
        valid = (
            _identity(event) == _identity(target) == _identity(receipt)
            and _valid_receipt(receipt)
            and receipt["checksum"] == _checksum(_encoded(prediction))
            and all(receipt[field] == prediction[field] for field in (
                "prediction_id", "mode", "qualifying_source_version",
                "event_schedule_hash", "roster_version"))
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise PublicationError("retained confirmed selection is malformed")


def confirm_publication(
    candidate: Candidate, commit: str, *, remote_reader: Callable,
    clock: Callable = lambda: datetime.now(timezone.utc),
) -> dict:
    """Record the real completion time of a successful immutable-byte readback.

    A saved confirmation may be delivered later, but a new late read cannot create
    one. The durable local receipt supports retry after a failed promotion.
    """
    if not COMMIT.fullmatch(commit):
        raise ValueError("confirmation requires an immutable Git commit")
    expected = _encoded(candidate.prediction)
    saved = candidate.directory / "confirmation.json"
    if saved.exists():
        receipt = json.loads(saved.read_bytes())
        if (not _valid_receipt(receipt) or receipt["commit"] != commit
                or receipt["checksum"] != _checksum(expected)):
            raise PublicationError("saved confirmation does not match candidate")
        return receipt
    deadline = _deadline(candidate.event, candidate.prediction["mode"])
    try:
        retrieved = remote_reader(commit, candidate.version_path,
                                  timeout=_remaining(clock, deadline))
    except (OSError, subprocess.SubprocessError) as exc:
        raise PublicationError("saved-output readback failed") from exc
    # Never trust a transport-provided timestamp or HTTP status alone.
    verified_at = parse_utc(clock())
    if verified_at >= deadline:
        raise PublicationError("saved-output verification completed after deadline")
    if not isinstance(retrieved, bytes) or retrieved != expected:
        raise PublicationError("saved-output version/checksum mismatch")
    prediction, event = candidate.prediction, candidate.event
    receipt = {
        "schema_version": 1, "confirmed": True,
        "season": event["season"], "round": event["round"],
        "prediction_id": prediction["prediction_id"], "mode": prediction["mode"],
        "qualifying_source_version": prediction["qualifying_source_version"],
        "event_schedule_hash": prediction["event_schedule_hash"],
        "roster_version": prediction["roster_version"],
        "qualifying_start_at": _text(event["qualifying_start_at"]),
        "cutoff_at": _text(event_windows(event)["cutoff_at"]),
        "commit": commit, "version_path": candidate.version_path,
        "checksum": _checksum(expected), "published_at": _text(verified_at),
    }
    receipt["publication_id"] = _receipt_id(receipt)
    write_immutable(saved, receipt)  # May finish late; verified_at cannot be backdated.
    return receipt


def run_git(args, *, cwd, timeout, input=None, env=None):
    """Bounded Git runner; replace only this boundary for transport fault tests."""
    result = subprocess.run(
        ["git", "-c", f"safe.directory={Path(cwd).as_posix()}", *args],
        cwd=cwd, input=input, env=env, capture_output=True, timeout=timeout,
        check=True,
    )
    return result.stdout


class GitPublisher:
    def __init__(self, repo: str | Path, *, remote: str, branch: str,
                 remote_reader: Callable, clock: Callable = lambda: datetime.now(timezone.utc),
                 git_runner: Callable = run_git, delivery_seconds: float = 120):
        self.repo = Path(repo).resolve()
        if not remote or remote.startswith("-") or not re.fullmatch(r"[A-Za-z0-9_./-]+", branch) or branch.startswith(("-", "/")) or ".." in branch:
            raise ValueError("invalid Git publication remote/branch")
        if not 0 < delivery_seconds <= 300:
            raise ValueError("delivery budget must be in (0, 300] seconds")
        self.remote, self.branch = remote, branch
        self.remote_reader, self.clock, self.git_runner = remote_reader, clock, git_runner
        self.delivery_seconds = delivery_seconds

    def _git(self, args, deadline, **kwargs):
        result = self.git_runner(args, cwd=self.repo,
                                 timeout=min(30, _remaining(self.clock, deadline)), **kwargs)
        _remaining(self.clock, deadline)
        return result

    def _head(self, deadline):
        self._git(["fetch", "--no-tags", self.remote, f"refs/heads/{self.branch}"], deadline)
        return self._git(["rev-parse", "FETCH_HEAD"], deadline).decode().strip()

    def _read(self, head, path, deadline):
        # Avoid `git show`'s fallback to statting the working tree for absent
        # objects (including Windows path limits). Other Git errors stay errors.
        if not self._git(["ls-tree", "-z", head, "--", path], deadline):
            return None
        return self._git(["show", f"{head}:{path}"], deadline)

    def _json(self, head, path, deadline):
        data = self._read(head, path, deadline)
        if data is None:
            return None
        value = json.loads(data)
        if not isinstance(value, dict):
            raise PublicationError(f"remote object is malformed: {path}")
        return value

    @contextmanager
    def _lock(self, deadline):
        common = self._git(["rev-parse", "--git-common-dir"], deadline).decode().strip()
        lock = (self.repo / common).resolve() / "codex-publication.lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise PublicationError("publication writer lock is held") from exc
        try:
            os.close(descriptor)
            yield
        finally:
            lock.unlink()

    def _context(self, head, candidate, deadline):
        base = _event_path(candidate.event)
        event = self._json(head, f"{base}/event.json", deadline)
        status = self._json(head, f"{base}/status.json", deadline) or {}
        final = self._json(head, f"{base}/final.json", deadline)
        feed = self._json(head, FEED_PATH, deadline)
        target_id = f"{candidate.event['season']}-{candidate.event['round']}"
        if feed:
            feed_identity = _identity(feed.get("event", {}))
            feed_id = f"{feed_identity[0]}-{feed_identity[1]}"
            if feed_id not in {candidate.expected_feed_event_id, target_id}:
                raise ReplanRequired("global feed event changed")
        if feed and _identity(feed.get("event", {})) != _identity(candidate.event):
            feed = None  # A prior event is never this event's fallback.
        if feed is None:
            feed = self._json(head, f"{base}/feed.json", deadline)
        if event is not None and (
            _identity(event) != _identity(candidate.event)
            or schedule_hash(event) != candidate.prediction["event_schedule_hash"]
            or roster_version(event["roster"]) != candidate.prediction["roster_version"]
        ):
            raise ReplanRequired("event schedule or roster changed")
        if final is not None or _is_frozen(status):
            raise ReplanRequired("event is frozen")
        current = (feed or {}).get("current")
        prediction = (current or {}).get("prediction") or {}
        if prediction.get("mode") == "actual_qualifying" and candidate.prediction["mode"] != "actual_qualifying":
            raise ReplanRequired("prediction mode would regress")
        if prediction.get("prediction_id") not in {candidate.expected_current_id, candidate.prediction["prediction_id"]}:
            raise ReplanRequired("published prediction changed")
        for field in ("current", "previous", "initial"):
            _validate_selection((feed or {}).get(field), candidate.event)
        if prediction.get("prediction_id") == candidate.prediction["prediction_id"]:
            receipt = current.get("publication", {})
            if not _valid_receipt(receipt) or receipt["checksum"] != _checksum(_encoded(candidate.prediction)):
                raise PublicationError("current confirmation is malformed")
            return status, feed, receipt
        if prediction.get("prediction_id") != candidate.expected_current_id:
            raise ReplanRequired("published prediction changed")
        if status.get("qualifying_source_version") != candidate.expected_source_version:
            raise ReplanRequired("accepted source changed")
        for path, baseline in candidate.expected_file_checksums.items():
            value = self._read(head, path, deadline)
            current_hash = _checksum(value) if value is not None else None
            if current_hash not in {baseline, _checksum(candidate.files[path])}:
                raise ReplanRequired(f"candidate data path changed: {path}")
        return status, feed, None

    def _commit(self, head, files, deadline, *, immutable=()):
        changes = {}
        for path, content in files.items():
            old = self._read(head, path, deadline)
            if old == content:
                continue
            if old is not None and path in immutable:
                raise ReplanRequired(f"immutable file collision: {path}")
            changes[path] = content
        if not changes:
            return head
        with tempfile.TemporaryDirectory(prefix="f1-publication-index-") as temporary:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
            self._git(["read-tree", head], deadline, env=env)
            for path, content in changes.items():
                blob = self._git(["hash-object", "-w", "--stdin"], deadline, input=content).decode().strip()
                self._git(["update-index", "--add", "--cacheinfo", f"100644,{blob},{path}"], deadline, env=env)
            tree = self._git(["write-tree"], deadline, env=env).decode().strip()
            return self._git(["commit-tree", tree, "-p", head, "-m", "Publish prediction artifacts"], deadline).decode().strip()

    def _push(self, commit, deadline):
        try:
            self._git(["push", self.remote, f"{commit}:refs/heads/{self.branch}"], deadline)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # A timed-out push may have succeeded. Reconcile before any retry.
            head = self._head(deadline)
            try:
                self._git(["merge-base", "--is-ancestor", commit, head], deadline)
                return True
            except subprocess.CalledProcessError:
                return False

    def publish_candidate(self, candidate: Candidate) -> dict:
        """Push, verify, then promote; return the immutable confirmation receipt."""
        validate_prediction(candidate.prediction, candidate.event)
        if (candidate.directory / "prediction.json").read_bytes() != _encoded(candidate.prediction):
            raise PublicationError("staged candidate bytes changed")
        if (candidate.directory / "context.json").read_bytes() != _encoded(_stage_context(candidate)):
            raise PublicationError("staged candidate context changed")
        if (candidate.directory / "page.json").read_bytes() != _encoded(_compatibility(candidate.prediction, None)):
            raise PublicationError("staged page candidate changed")
        if any((candidate.directory / "files" / path).read_bytes() != data
               for path, data in candidate.files.items()):
            raise PublicationError("staged raw candidate changed")
        saved_receipt = candidate.directory / "confirmation.json"
        deadline = (_deadline(candidate.event, candidate.prediction["mode"])
                    if not saved_receipt.exists() else
                    parse_utc(self.clock()) + timedelta(seconds=self.delivery_seconds))
        conflicts_left = 2
        try:
            with self._lock(deadline):
                commit = None
                for attempt in range(3):
                    head = self._head(deadline)
                    _, _, existing = self._context(head, candidate, deadline)
                    if existing is not None:
                        return existing
                    if saved_receipt.exists():
                        saved = json.loads(saved_receipt.read_bytes())
                        commit = saved["commit"]
                        self._git(["merge-base", "--is-ancestor", commit, head], deadline)
                        if self._read(head, candidate.version_path, deadline) != _encoded(candidate.prediction):
                            raise ReplanRequired("confirmed version no longer exists unchanged")
                        break
                    files = dict(candidate.files, **{candidate.version_path: _encoded(candidate.prediction)})
                    # Initial/event/selection files are reserved for confirmed promotion.
                    immutable = [path for path in files if not path.startswith("ml/data/raw/")]
                    commit = self._commit(head, files, deadline, immutable=immutable)
                    if commit == head or self._push(commit, deadline):
                        break
                    if conflicts_left == 0:
                        raise PublicationError("conflict retry limit reached")
                    conflicts_left -= 1
                # Fetch again before readback: a successful push does not prove context freshness.
                head = self._head(deadline)
                self._context(head, candidate, deadline)
                receipt = confirm_publication(candidate, commit, remote_reader=self.remote_reader, clock=self.clock)
                delivery_deadline = parse_utc(self.clock()) + timedelta(seconds=self.delivery_seconds)
                return self._promote(candidate, receipt, delivery_deadline, conflicts_left)
        except (OSError, subprocess.SubprocessError) as exc:
            raise PublicationError("publication transport or persistence failed") from exc

    def _promote(self, candidate, receipt, deadline, conflicts_left):
        base = _event_path(candidate.event)
        for attempt in range(3):
            head = self._head(deadline)
            status, previous_feed, existing = self._context(head, candidate, deadline)
            if existing is not None:
                return existing
            prior = (previous_feed or {}).get("current")
            current = {"event": candidate.event, "prediction": candidate.prediction, "publication": receipt}
            initial = (previous_feed or {}).get("initial")
            if initial is None and candidate.prediction["mode"] == "predicted_qualifying":
                initial = current
            status = dict(status, current_prediction_id=candidate.prediction["prediction_id"],
                          qualifying_source_version=candidate.prediction["qualifying_source_version"])
            if candidate.prediction["mode"] == "actual_qualifying":
                status.update(actual_publication_confirmed=True,
                              actual_publication_confirmed_at=receipt["published_at"])
                status.pop("next_qualifying_check_at", None)
            feed = build_feed(candidate.event, status, current=current,
                              previous=prior, initial=initial, updated_at=self.clock())
            receipt_path = f"{base}/publications/{receipt['publication_id']}.json"
            files = {
                receipt_path: _encoded(receipt), FEED_PATH: _encoded(feed),
                f"{base}/feed.json": _encoded(feed),
                COMPATIBILITY_PATH: _encoded(_compatibility(candidate.prediction, initial)),
                f"{base}/event.json": _encoded(candidate.event),
                f"{base}/status.json": _encoded(status),
            }
            # Keep the original archive even if schedule/roster changed since it was saved.
            initial_path = f"{base}/initial.json"
            if initial is not None and self._read(head, initial_path, deadline) is None:
                files[initial_path] = _encoded(initial["prediction"])
            commit = self._commit(head, files, deadline, immutable=(receipt_path, initial_path))
            if commit == head or self._push(commit, deadline):
                return receipt
            if conflicts_left == 0:
                raise PublicationError("confirmation delivery conflict retry limit reached")
            conflicts_left -= 1
        raise AssertionError("unreachable")


def publish_candidate(candidate: Candidate, *, publisher: GitPublisher) -> dict:
    """Functional facade for controllers that inject a publisher instance."""
    return publisher.publish_candidate(candidate)


def build_feed(event: Mapping, status: Mapping, *, current=None, previous=None,
               initial=None, updated_at) -> dict:
    """Build a revision for publication or a status-only/freeze update.

    ``updated_at`` must be the real UTC revision creation time. It does not prove
    delivery and never alters the embedded receipt's eligibility timestamp.
    Callers must still use coordinated, context-checked Git publication.
    """
    season, round_number = _identity(event)
    event_windows(event)
    for selection in (current, previous, initial):
        _validate_selection(selection, event)
    if initial is not None and initial["prediction"]["mode"] != "predicted_qualifying":
        raise PublicationError("initial selection must be predicted qualifying")
    feed = copy.deepcopy({
        "schema_version": 1, "current_event_id": f"{season}-{round_number}",
        "event": dict(event), "status": dict(status), "current": current,
        "previous": previous, "initial": initial, "feed_updated_at": _text(updated_at),
    })
    feed["revision"] = digest(feed)
    return feed


def _compatibility(prediction, initial):
    forecast = copy.deepcopy(prediction["forecast"])
    if prediction["mode"] == "actual_qualifying" and initial is not None:
        for field in ("predictedQualifying", "preQualifyingPodium"):
            forecast[field] = copy.deepcopy(initial["prediction"]["forecast"][field])
    return {
        "asof": prediction["generated_at"][:10],
        "generatedAt": prediction["generated_at"],
        "race": forecast["race"], "forecast": forecast,
    }


def select_final(publications: Iterable[Mapping], cutoff_at, *, event: Mapping | None = None) -> dict | None:
    """Choose deterministic latest confirmed availability, never generation time.

    Pass ``event`` when loading a mixed archive. Without it, mixed event identities
    are rejected rather than implicitly selecting another race.
    """
    publications = list(publications)
    if event is None:
        identities = {_identity(item) for item in publications}
        if len(identities) > 1:
            raise ValueError("freeze requires one exact event identity")
        target = next(iter(identities), None)
    else:
        target = _identity(event)
    cutoff = parse_utc(cutoff_at)
    eligible = [item for item in publications if _valid_receipt(item)
                and _identity(item) == target and parse_utc(item["published_at"]) < cutoff
                and (event is None or (
                    parse_utc(item["published_at"]) < event_windows(event)["cutoff_at"]
                    and (item["mode"] != "predicted_qualifying" or
                         parse_utc(item["published_at"]) < parse_utc(event["qualifying_start_at"]))
                ))]
    if not eligible:
        return None
    return copy.deepcopy(max(eligible, key=lambda item: (parse_utc(item["published_at"]), item["publication_id"])))


def write_final(event: Mapping, selection: Mapping | None, *, root: str | Path) -> dict:
    """Write one terminal selection; subsequent schedule changes never reopen it."""
    season, round_number = _identity(event)
    path = Path(root) / "prediction_snapshots" / f"{season}-{round_number}" / "final.json"
    if path.exists():
        try:
            encoded = path.read_bytes()
            existing = json.loads(encoded)
            prior = existing["publication"]
            valid = (
                encoded == _encoded(existing) and _identity(existing) == (season, round_number)
                and type(existing.get("schema_version")) is int and existing["schema_version"] == 1
                and SHA256.fullmatch(existing["event_schedule_hash"])
                and ((prior is None and existing["status"] == "unavailable")
                     or (isinstance(prior, Mapping) and existing["status"] == "frozen"
                         and select_final([prior], existing["cutoff_at"], event=None) == prior
                         and _identity(prior) == (season, round_number)))
                and all(existing[key] == (prior[key] if prior else None) for key in (
                    "prediction_id", "publication_id", "mode", "qualifying_source_version"))
            )
            parse_utc(existing["cutoff_at"])
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            raise ArtifactCollisionError("existing final is malformed")
        if existing["event_schedule_hash"] == schedule_hash(event) and prior != selection:
            raise ArtifactCollisionError("immutable final selection cannot change")
        return existing
    cutoff = event_windows(event)["cutoff_at"]
    if selection is not None and select_final([selection], cutoff, event=event) is None:
        raise PublicationError("final selection lacks eligible confirmation")
    final = {
        "schema_version": 1, "season": season, "round": round_number,
        "cutoff_at": _text(cutoff), "event_schedule_hash": schedule_hash(event),
        "status": "frozen" if selection is not None else "unavailable",
        "prediction_id": selection["prediction_id"] if selection else None,
        "publication_id": selection["publication_id"] if selection else None,
        "mode": selection["mode"] if selection else None,
        "qualifying_source_version": selection["qualifying_source_version"] if selection else None,
        "publication": dict(selection) if selection else None,
    }
    write_immutable(path, final)
    return final
