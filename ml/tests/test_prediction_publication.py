"""Publication integration tests use only disposable local bare Git remotes."""
from __future__ import annotations

from datetime import timedelta
import importlib
import hashlib
import json
import subprocess

import pytest

from src.pipeline.artifacts import canonical_bytes, digest
from src.pipeline.events import parse_utc
from test_prediction_artifacts import _accepted, _event, _forecast, _prediction


DATA = "web/public/data"
EVENT = f"{DATA}/prediction_snapshots/2026-20"
FEED = f"{DATA}/prediction_feed.json"


def api():
    assert importlib.util.find_spec("src.pipeline.publish") is not None, "publication module missing"
    return importlib.import_module("src.pipeline.publish")


def git(repo, *args, input=None):
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", *args], cwd=repo,
        input=input, capture_output=True, timeout=20, check=True,
    )
    return result.stdout


def put(repo, path, payload):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical_bytes(payload) + b"\n")


class Clock:
    def __init__(self, at="2026-10-30T13:00:00Z"):
        self.now = parse_utc(at)

    def __call__(self):
        return self.now


@pytest.fixture
def remote(tmp_path):
    bare = tmp_path / "remote.git"
    bare.mkdir()
    git(bare, "init", "--bare", "--initial-branch=main")
    repo = tmp_path / "writer"
    git(tmp_path, "clone", str(bare), str(repo))
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Publication tests")
    put(repo, f"{EVENT}/event.json", _event())
    put(repo, f"{EVENT}/status.json", {})
    git(repo, "add", ".")
    git(repo, "commit", "-m", "seed")
    git(repo, "push", "origin", "main")
    return repo, bare


def read_remote(bare, path):
    result = subprocess.run(
        ["git", "-C", str(bare), "show", f"main:{path}"],
        capture_output=True, timeout=20,
    )
    return result.stdout if result.returncode == 0 else None


def make_publisher(remote, clock=None, reader=None, runner=None):
    module = api()
    repo, bare = remote
    def saved_output(commit, path, *, timeout):
        assert timeout > 0
        return git(bare, "show", f"{commit}:{path}")
    return module.GitPublisher(
        repo, remote="origin", branch="main", clock=clock or Clock(),
        remote_reader=reader or saved_output, git_runner=runner or module.run_git,
    )


def stage(tmp_path, prediction=None, **kwargs):
    event = kwargs.pop("event", _event())
    return api().stage_candidate(
        tmp_path / "private", event, prediction or _prediction(), **kwargs,
    )


def actual(source="a" * 64, event=None):
    forecast = _forecast()
    forecast.update(
        mode="actual_qualifying", hasRealGrid=True,
        realGridPodium=forecast["preQualifyingPodium"],
        realQualifying=[dict(row, modelPosition=row["position"], modelGap=row["gap"])
                        for row in forecast["predictedQualifying"]],
        predictedQualifying=[], preQualifyingPodium=[],
    )
    return _prediction(
        mode="actual_qualifying", qualifying=_accepted(source), forecast=forecast,
        generated_at="2026-11-01T01:00:00Z",
        event=event or _event(),
    )


def compete(remote, path, payload):
    repo, bare = remote
    other = bare.parent / "competitor"
    if not other.exists():
        git(bare.parent, "clone", str(bare), str(other))
        git(other, "config", "user.email", "other@example.invalid")
        git(other, "config", "user.name", "Concurrent writer")
    git(other, "pull", "--ff-only", "origin", "main")
    put(other, path, payload)
    git(other, "add", path)
    git(other, "commit", "-m", "concurrent change")
    git(other, "push", "origin", "main")


class PushFault:
    def __init__(self, callback=None, *, unknown=False, reject=False, every=False):
        self.callback, self.unknown, self.reject, self.every = callback, unknown, reject, every
        self.pushes = 0

    def __call__(self, args, **kwargs):
        module = api()
        if args[0] == "push":
            self.pushes += 1
            if self.pushes == 1 or self.every:
                if self.callback:
                    self.callback()
                if self.unknown:
                    module.run_git(args, **kwargs)
                    raise subprocess.TimeoutExpired(args, kwargs["timeout"])
                if self.reject:
                    raise subprocess.CalledProcessError(1, args, stderr=b"rejected")
        return module.run_git(args, **kwargs)


def test_stage_does_not_write_public_files_and_rejects_invalid_model(tmp_path, remote):
    candidate = stage(tmp_path)
    assert candidate.prediction["prediction_id"] == _prediction()["prediction_id"]
    assert read_remote(remote[1], FEED) is None
    broken = _prediction()
    broken["forecast"]["error"] = "model_failed"
    with pytest.raises(ValueError):
        stage(tmp_path, broken)
    assert read_remote(remote[1], FEED) is None


def test_confirmed_commit_promotes_one_feed_and_compatibility(remote, tmp_path):
    result = make_publisher(remote).publish_candidate(stage(tmp_path))
    feed = json.loads(read_remote(remote[1], FEED))
    assert result["confirmed"] is True
    assert feed["schema_version"] == 1
    assert feed["event"]["round"] == 20
    assert feed["current"]["publication"] == result
    assert feed["initial"] == feed["current"]
    assert feed["previous"] is None
    compatibility = json.loads(read_remote(remote[1], f"{DATA}/next_race_prediction.json"))
    assert compatibility["forecast"] == _prediction()["forecast"]
    assert compatibility["race"] == _prediction()["forecast"]["race"]
    assert compatibility["generatedAt"] == _prediction()["generated_at"]
    assert compatibility["asof"] == "2026-10-30"
    assert git(remote[0], "status", "--porcelain") == b""


@pytest.mark.parametrize("failure", ["wrong_bytes", "reader_error", "slow_read", "slow_push"])
def test_failed_or_late_candidate_never_replaces_prior_feed(remote, tmp_path, failure):
    make_publisher(remote).publish_candidate(stage(tmp_path))
    before = read_remote(remote[1], FEED)
    clock = Clock("2026-11-01T15:59:59Z")
    candidate = stage(tmp_path, actual(), expected_current_id=_prediction()["prediction_id"])
    def reader(commit, path, *, timeout):
        if failure == "reader_error":
            raise OSError("readback unavailable")
        if failure == "slow_read":
            clock.now += timedelta(seconds=2)
        data = git(remote[1], "show", f"{commit}:{path}")
        return b"{}" if failure == "wrong_bytes" else data
    runner = None
    if failure == "slow_push":
        runner = PushFault(callback=lambda: setattr(clock, "now", clock.now + timedelta(seconds=2)))
    with pytest.raises(api().PublicationError):
        make_publisher(remote, clock, reader, runner).publish_candidate(candidate)
    assert read_remote(remote[1], FEED) == before
    receipts = git(remote[1], "ls-tree", "-r", "--name-only", "main", f"{EVENT}/publications").splitlines()
    assert len(receipts) == 1
    assert not (candidate.directory / "confirmation.json").exists()


def test_write_failure_leaves_served_selection_unchanged(remote, tmp_path, monkeypatch):
    before = read_remote(remote[1], FEED)
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(api(), "write_immutable", fail)
    with pytest.raises(OSError, match="disk full"):
        stage(tmp_path)
    assert read_remote(remote[1], FEED) == before


def test_uncertain_push_is_reconciled_without_duplicate_receipts(remote, tmp_path):
    runner = PushFault(unknown=True)
    candidate = stage(tmp_path)
    publisher = make_publisher(remote, runner=runner)
    first = publisher.publish_candidate(candidate)
    second = publisher.publish_candidate(candidate)
    assert first == second
    assert runner.pushes == 2  # immutable candidate, then confirmed feed; no retry duplicate
    assert len(git(remote[1], "ls-tree", "-r", "--name-only", "main", f"{EVENT}/publications").splitlines()) == 1


def test_disjoint_stats_race_rebuilds_on_latest_parent_without_changing_prediction(remote, tmp_path):
    runner = PushFault(callback=lambda: compete(remote, f"{DATA}/stats.json", {"new": True}))
    candidate = stage(tmp_path)
    result = make_publisher(remote, runner=runner).publish_candidate(candidate)
    assert json.loads(read_remote(remote[1], f"{DATA}/stats.json")) == {"new": True}
    assert read_remote(remote[1], result["version_path"]) == canonical_bytes(candidate.prediction) + b"\n"
    assert runner.pushes == 3


@pytest.mark.parametrize("change", ["schedule", "source", "published", "freeze", "roster"])
def test_semantic_concurrent_change_requires_replanning(remote, tmp_path, change):
    def alter():
        if change in {"schedule", "roster"}:
            event = _event()
            if change == "schedule":
                event["race_start_at"] = "2026-11-01T19:00:00Z"
            else:
                event["roster"][0]["constructor_id"] = "changed"
            compete(remote, f"{EVENT}/event.json", event)
        elif change == "published":
            compete(remote, FEED, {"event": _event(), "current": {"prediction": {"prediction_id": "b" * 64}}})
        else:
            compete(remote, f"{EVENT}/status.json", {"qualifying_source_version": "b" * 64} if change == "source" else {"frozen_at": "2026-10-30T12:00:00Z"})
    runner = PushFault(callback=alter)
    with pytest.raises(api().ReplanRequired):
        make_publisher(remote, runner=runner).publish_candidate(stage(tmp_path))
    assert runner.pushes == 1
    assert read_remote(remote[1], f"{EVENT}/initial.json") is None


def test_conflict_retries_are_bounded(remote, tmp_path):
    runner = PushFault(reject=True, every=True)
    with pytest.raises(api().PublicationError):
        make_publisher(remote, runner=runner).publish_candidate(stage(tmp_path))
    assert runner.pushes == 3
    assert read_remote(remote[1], FEED) is None


def test_actual_keeps_confirmed_initial_and_previous_and_rejects_mode_regression(remote, tmp_path):
    initial = stage(tmp_path)
    first = make_publisher(remote).publish_candidate(initial)
    prediction = actual()
    current = stage(tmp_path, prediction, expected_current_id=initial.prediction["prediction_id"])
    second = make_publisher(remote, Clock("2026-11-01T02:00:00Z")).publish_candidate(current)
    feed = json.loads(read_remote(remote[1], FEED))
    assert feed["previous"]["publication"] == first
    assert feed["initial"]["publication"] == first
    assert feed["current"]["publication"] == second
    compatibility = json.loads(read_remote(remote[1], f"{DATA}/next_race_prediction.json"))
    assert compatibility["forecast"]["preQualifyingPodium"] == initial.prediction["forecast"]["preQualifyingPodium"]
    assert compatibility["forecast"]["realGridPodium"] == prediction["forecast"]["realGridPodium"]
    old = stage(tmp_path, expected_current_id=prediction["prediction_id"], expected_source_version="a" * 64)
    with pytest.raises(api().ReplanRequired, match="mode"):
        make_publisher(remote).publish_candidate(old)
    assert json.loads(read_remote(remote[1], FEED)) == feed


def test_verified_receipt_can_be_persisted_and_promoted_after_deadline(remote, tmp_path):
    clock = Clock("2026-11-01T15:59:59Z")
    candidate = stage(tmp_path, actual())
    module = api()
    def runner(args, **kwargs):
        if args[0] == "push" and (candidate.directory / "confirmation.json").exists():
            clock.now += timedelta(seconds=5)
        return module.run_git(args, **kwargs)
    receipt = make_publisher(remote, clock, runner=runner).publish_candidate(candidate)
    assert parse_utc(receipt["published_at"]) < parse_utc("2026-11-01T16:00:00Z")
    assert clock.now > parse_utc("2026-11-01T16:00:00Z")
    assert json.loads(read_remote(remote[1], FEED))["current"]["publication"] == receipt


def test_freeze_uses_confirmed_time_exact_event_and_is_immutable(remote, tmp_path):
    module = api()
    receipt = make_publisher(remote).publish_candidate(stage(tmp_path))
    late = dict(receipt, published_at="2026-11-01T16:00:00Z")
    unconfirmed = dict(receipt, confirmed=False)
    assert module.select_final([late, unconfirmed], "2026-11-01T16:00:00Z", event=_event()) is None
    selected = module.select_final([receipt, late], "2026-11-01T16:00:00Z", event=_event())
    assert selected == receipt
    wrong_event = dict(receipt, round=21)
    assert module.select_final([wrong_event], "2026-11-01T16:00:00Z", event=_event()) is None
    final = module.write_final(_event(), selected, root=tmp_path / "data")
    path = tmp_path / "data/prediction_snapshots/2026-20/final.json"
    before = path.read_bytes()
    assert final["prediction_id"] == receipt["prediction_id"]
    module.write_final(_event(race_start_at="2026-11-01T19:00:00Z"), None, root=tmp_path / "data")
    assert path.read_bytes() == before


def test_freeze_without_eligible_receipt_is_unavailable_and_never_reconstructed(tmp_path):
    final = api().write_final(_event(), None, root=tmp_path / "data")
    assert final["status"] == "unavailable"
    assert final["prediction_id"] is None


def test_initial_cannot_be_verified_at_qualifying_start(remote, tmp_path):
    with pytest.raises(api().PublicationError):
        make_publisher(remote, Clock("2026-10-31T18:00:00Z")).publish_candidate(stage(tmp_path))
    assert read_remote(remote[1], FEED) is None


@pytest.mark.parametrize("change", ["raw", "rollover"])
def test_overlapping_raw_or_global_event_change_cannot_be_overwritten(remote, tmp_path, change):
    raw_path = "ml/data/raw/qualifying_2026.parquet"
    files = {raw_path: b"candidate full season"} if change == "raw" else None
    candidate = stage(tmp_path, files=files, expected_file_checksums={raw_path: None} if files else None)
    def alter():
        if change == "raw":
            compete(remote, raw_path, {"other_event": "new qualifying"})
        else:
            compete(remote, FEED, {"event": _event(round=21), "current_event_id": "2026-21", "current": None})
    runner = PushFault(callback=alter)
    with pytest.raises(api().ReplanRequired):
        make_publisher(remote, runner=runner).publish_candidate(candidate)
    if change == "raw":
        assert json.loads(read_remote(remote[1], raw_path))["other_event"] == "new qualifying"
    else:
        assert json.loads(read_remote(remote[1], FEED))["current_event_id"] == "2026-21"


def test_stage_rejects_reserved_paths_and_mutable_files_without_baseline(tmp_path):
    with pytest.raises(ValueError, match="permitted"):
        stage(tmp_path, files={FEED: b"{}"})
    with pytest.raises(ValueError, match="baseline"):
        stage(tmp_path, files={"ml/data/raw/qualifying_2026.parquet": b"raw"})


def test_corrupt_or_conflicting_existing_final_fails_closed(tmp_path, remote):
    module = api()
    receipt = make_publisher(remote).publish_candidate(stage(tmp_path))
    root = tmp_path / "data"
    module.write_final(_event(), receipt, root=root)
    with pytest.raises(module.ArtifactCollisionError):
        module.write_final(_event(), None, root=root)
    path = root / "prediction_snapshots/2026-20/final.json"
    path.write_bytes(b'{"season":2026,"round":20}')
    with pytest.raises(module.ArtifactCollisionError):
        module.write_final(_event(), receipt, root=root)


def test_initial_freeze_rechecks_current_qualifying_deadline_without_discarding_postponed_fallback(remote, tmp_path):
    module = api()
    receipt = make_publisher(remote).publish_candidate(stage(tmp_path))
    earlier = _event(qualifying_start_at="2026-10-30T12:00:00Z", qualifying_end_observed_at="2026-10-30T13:00:00Z")
    assert module.select_final([receipt], "2026-11-01T16:00:00Z", event=earlier) is None
    postponed = _event(race_start_at="2026-11-01T19:00:00Z")
    assert module.select_final([receipt], "2026-11-01T17:00:00Z", event=postponed) == receipt
    invalid = dict(receipt, qualifying_source_version="a" * 64)
    invalid["publication_id"] = digest({key: value for key, value in invalid.items() if key != "publication_id"})
    assert module.select_final([invalid], "2026-11-01T16:00:00Z", event=_event()) is None


def test_staging_writes_private_raw_and_page_bytes_and_detects_mutation(tmp_path, remote):
    path = "ml/data/raw/qualifying_2026.parquet"
    candidate = stage(tmp_path, files={path: b"validated parquet"}, expected_file_checksums={path: None})
    assert (candidate.directory / "files" / path).read_bytes() == b"validated parquet"
    assert json.loads((candidate.directory / "page.json").read_bytes())["forecast"] == candidate.prediction["forecast"]
    candidate.files[path] = b"changed after validation"
    with pytest.raises(api().PublicationError, match="context changed"):
        make_publisher(remote).publish_candidate(candidate)
    assert read_remote(remote[1], FEED) is None


def test_retained_initial_keeps_original_event_context_after_schedule_change(tmp_path, remote):
    initial = stage(tmp_path)
    make_publisher(remote).publish_candidate(initial)
    event = _event(race_start_at="2026-11-01T19:00:00Z")
    compete(remote, f"{EVENT}/event.json", event)
    prediction = actual(event=event)
    candidate = stage(tmp_path, prediction, event=event, expected_current_id=initial.prediction["prediction_id"])
    make_publisher(remote, Clock("2026-11-01T02:00:00Z")).publish_candidate(candidate)
    feed = json.loads(read_remote(remote[1], FEED))
    assert feed["initial"]["event"] == _event()
    assert feed["current"]["event"] == event
    assert json.loads(read_remote(remote[1], f"{EVENT}/initial.json")) == initial.prediction


def test_corrupt_retained_selection_is_never_promoted_as_fallback(tmp_path, remote):
    initial = stage(tmp_path)
    make_publisher(remote).publish_candidate(initial)
    feed = json.loads(read_remote(remote[1], FEED))
    feed["initial"]["prediction"]["forecast"]["error"] = "corrupt"
    compete(remote, FEED, feed)
    candidate = stage(tmp_path, actual(), expected_current_id=initial.prediction["prediction_id"])
    with pytest.raises(api().PublicationError, match="selection"):
        make_publisher(remote, Clock("2026-11-01T02:00:00Z")).publish_candidate(candidate)
    assert json.loads(read_remote(remote[1], FEED)) == feed


def test_failed_promotion_keeps_durable_receipt_and_retries_after_deadline(tmp_path, remote):
    candidate = stage(tmp_path, actual())
    clock = Clock("2026-11-01T15:59:59Z")
    module = api()
    def reject_promotion(args, **kwargs):
        if args[0] == "push" and (candidate.directory / "confirmation.json").exists():
            raise subprocess.CalledProcessError(1, args)
        return module.run_git(args, **kwargs)
    with pytest.raises(module.PublicationError, match="retry limit"):
        make_publisher(remote, clock, runner=reject_promotion).publish_candidate(candidate)
    receipt = json.loads((candidate.directory / "confirmation.json").read_bytes())
    assert read_remote(remote[1], FEED) is None
    clock.now += timedelta(minutes=5)
    def no_new_verification(*args, **kwargs):
        pytest.fail("already confirmed bytes must not acquire a new eligibility timestamp")
    assert make_publisher(remote, clock, reader=no_new_verification).publish_candidate(candidate) == receipt


def test_uncertain_promotion_is_reconciled(tmp_path, remote):
    candidate = stage(tmp_path)
    module = api()
    def timeout_after_promotion(args, **kwargs):
        value = module.run_git(args, **kwargs)
        if args[0] == "push" and (candidate.directory / "confirmation.json").exists():
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        return value
    receipt = make_publisher(remote, runner=timeout_after_promotion).publish_candidate(candidate)
    assert json.loads(read_remote(remote[1], FEED))["current"]["publication"] == receipt


def test_feed_builder_versions_status_without_new_eligibility(remote, tmp_path):
    module = api()
    module.publish_candidate(stage(tmp_path), publisher=make_publisher(remote))
    original = json.loads(read_remote(remote[1], FEED))
    assert original["revision"] == digest({key: value for key, value in original.items() if key != "revision"})
    updated = module.build_feed(
        _event(), dict(original["status"], final_state="frozen"),
        current=original["current"], previous=original["previous"], initial=original["initial"],
        updated_at="2026-11-01T16:05:00.123456Z",
    )
    assert updated["revision"] != original["revision"]
    assert updated["feed_updated_at"] == "2026-11-01T16:05:00.123456Z"
    assert updated["current"]["publication"] == original["current"]["publication"]


def test_git_reads_existing_blob_from_long_checkout_path(remote, tmp_path):
    long_repo = tmp_path / ("nested-" + "x" * 70) / "reader"
    git(tmp_path, "clone", "--no-checkout", str(remote[1]), str(long_repo))
    git(long_repo, "config", "core.longpaths", "false")
    clock = Clock()
    publisher = make_publisher((long_repo, remote[1]), clock)
    head = git(long_repo, "rev-parse", "HEAD").decode().strip()
    path = f"{EVENT}/event.json"
    assert len(str(long_repo / f"{head}:{path}")) > 260
    assert publisher._read(head, path, clock() + timedelta(seconds=30)) == canonical_bytes(_event()) + b"\n"


def test_git_read_rejects_tree_instead_of_regular_file(remote):
    clock = Clock()
    publisher = make_publisher(remote, clock)
    head = git(remote[0], "rev-parse", "HEAD").decode().strip()
    with pytest.raises(api().PublicationError, match="regular file"):
        publisher._read(head, EVENT, clock() + timedelta(seconds=30))


def confirmed_selection(tmp_path):
    candidate = stage(tmp_path)
    receipt = api().confirm_publication(
        candidate, "a" * 40, clock=Clock(),
        remote_reader=lambda commit, path, timeout: canonical_bytes(candidate.prediction) + b"\n",
    )
    return candidate, {"event": candidate.event, "prediction": candidate.prediction, "publication": receipt}


@pytest.mark.parametrize("mutation", ["qualifying_deadline", "cutoff_deadline", "late_publication", "before_generation"])
def test_feed_rejects_receipt_times_inconsistent_with_original_context(tmp_path, mutation):
    _, selection = confirmed_selection(tmp_path)
    receipt = selection["publication"]
    if mutation in {"qualifying_deadline", "late_publication"}:
        receipt["qualifying_start_at"] = "2030-10-31T18:00:00Z"
    if mutation in {"cutoff_deadline", "late_publication"}:
        receipt["cutoff_at"] = "2030-11-01T16:00:00Z"
    if mutation == "late_publication":
        receipt["published_at"] = "2026-11-02T00:00:00Z"
    if mutation == "before_generation":
        receipt["published_at"] = "2026-10-30T11:59:59Z"
    receipt["publication_id"] = digest({key: value for key, value in receipt.items() if key != "publication_id"})
    for position in ("current", "previous", "initial"):
        with pytest.raises(api().PublicationError, match="selection"):
            api().build_feed(_event(), {}, updated_at="2026-11-02T01:00:00Z", **{position: selection})


def test_confirmation_cannot_precede_prediction_generation(tmp_path):
    candidate = stage(tmp_path)
    with pytest.raises(api().PublicationError, match="generation"):
        api().confirm_publication(
            candidate, "a" * 40, clock=Clock("2026-10-30T11:59:59Z"),
            remote_reader=lambda commit, path, timeout: canonical_bytes(candidate.prediction) + b"\n",
        )
    assert not (candidate.directory / "confirmation.json").exists()


def test_saved_confirmation_rechecks_original_event_deadlines(tmp_path):
    candidate, selection = confirmed_selection(tmp_path)
    receipt = selection["publication"]
    receipt["cutoff_at"] = "2030-11-01T16:00:00Z"
    receipt["publication_id"] = digest({key: value for key, value in receipt.items() if key != "publication_id"})
    (candidate.directory / "confirmation.json").write_bytes(canonical_bytes(receipt) + b"\n")
    with pytest.raises(api().PublicationError, match="selection"):
        api().confirm_publication(
            candidate, "a" * 40, clock=Clock("2026-11-02T00:00:00Z"),
            remote_reader=lambda *args, **kwargs: pytest.fail("saved receipt must be checked locally"),
        )


@pytest.mark.parametrize("changed_file", ["version", "source", "check", "raw"])
@pytest.mark.parametrize("when", ["readback", "promotion_conflict"])
def test_promotion_rechecks_all_uploaded_bytes_after_concurrent_change(remote, tmp_path, changed_file, when):
    raw_path = "ml/data/raw/qualifying_2026.parquet"
    baseline = {"baseline": True}
    compete(remote, raw_path, baseline)
    paths = {"source": f"{EVENT}/sources/accepted.json", "check": f"{EVENT}/checks/checked.json", "raw": raw_path}
    files = {path: canonical_bytes({"candidate": key}) + b"\n" for key, path in paths.items()}
    candidate = stage(tmp_path, files=files, expected_file_checksums={raw_path: hashlib.sha256(canonical_bytes(baseline) + b"\n").hexdigest()})
    paths["version"] = candidate.version_path
    before = read_remote(remote[1], FEED)
    def change_uploaded_file():
        compete(remote, paths[changed_file], baseline if changed_file == "raw" else {"corrupt": True})
    def reader(commit, path, *, timeout):
        verified_bytes = git(remote[1], "show", f"{commit}:{path}")
        if when == "readback":
            change_uploaded_file()
        return verified_bytes
    pushes = 0
    def runner(args, **kwargs):
        nonlocal pushes
        if args[0] == "push":
            pushes += 1
            if when == "promotion_conflict" and pushes == 2:
                change_uploaded_file()
        return api().run_git(args, **kwargs)
    with pytest.raises(api().ReplanRequired):
        make_publisher(remote, reader=reader, runner=runner).publish_candidate(candidate)
    assert read_remote(remote[1], FEED) == before
    assert git(remote[1], "ls-tree", "-r", "--name-only", "main", f"{EVENT}/publications") == b""


@pytest.mark.parametrize("existing", ["malformed", "different", "inconsistent_confirmed"])
def test_existing_initial_must_match_valid_initial_context(remote, tmp_path, existing):
    initial = stage(tmp_path)
    if existing == "inconsistent_confirmed":
        make_publisher(remote).publish_candidate(initial)
    if existing == "malformed":
        payload = {"invalid_initial": True}
    else:
        forecast = _forecast()
        forecast["preQualifyingPodium"][1]["podiumProbability"] = 0.9
        forecast["preQualifyingPodium"][2]["podiumProbability"] = 0.6
        payload = _prediction(forecast=forecast)
        compete(remote, f"{EVENT}/versions/{payload['prediction_id']}.json", payload)
    compete(remote, f"{EVENT}/initial.json", payload)
    before = read_remote(remote[1], FEED)
    candidate = stage(tmp_path, actual(), expected_current_id=initial.prediction["prediction_id"]) if existing == "inconsistent_confirmed" else initial
    clock = Clock("2026-11-01T02:00:00Z") if existing == "inconsistent_confirmed" else Clock()
    with pytest.raises(api().PublicationError, match="initial"):
        make_publisher(remote, clock).publish_candidate(candidate)
    assert read_remote(remote[1], FEED) == before
    assert json.loads(read_remote(remote[1], f"{EVENT}/initial.json")) == payload


def test_existing_initial_identical_to_first_confirmed_candidate_is_retained(remote, tmp_path):
    candidate = stage(tmp_path)
    compete(remote, candidate.version_path, candidate.prediction)
    compete(remote, f"{EVENT}/initial.json", candidate.prediction)
    make_publisher(remote).publish_candidate(candidate)
    feed = json.loads(read_remote(remote[1], FEED))
    assert read_remote(remote[1], f"{EVENT}/initial.json") == canonical_bytes(feed["initial"]["prediction"]) + b"\n"


def test_byte_comparison_crossing_deadline_cannot_create_confirmation(tmp_path):
    candidate = stage(tmp_path, actual())
    clock = Clock("2026-11-01T15:59:59Z")
    class SlowComparison(bytes):
        def __ne__(self, other):
            clock.now += timedelta(seconds=2)
            return super().__ne__(other)
    def reader(commit, path, *, timeout):
        return SlowComparison(canonical_bytes(candidate.prediction) + b"\n")
    with pytest.raises(api().PublicationError, match="deadline"):
        api().confirm_publication(candidate, "a" * 40, clock=clock, remote_reader=reader)
    assert not (candidate.directory / "confirmation.json").exists()
