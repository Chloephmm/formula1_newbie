# Feature1 restoration — 2026-11-02

## Scope and recovery

Work was performed in the existing `formula1_newbie` checkout on `feature1`,
starting from `origin/main` at `7af3f91cb2d94507006091c3957a1818e44a244f`.
Previously reverted feature1 changes were reapplied as new changes; the old main
history was not rewritten. No worktree, remote push, workflow dispatch, or PR was
used for this restoration.

Before advancing the branch, local Mexico data and the earlier Brazil candidate
were preserved in a named Git stash and a sibling `local-backups` directory.
The original feature1 tip is retained as
`backup/feature1-before-restore-20261102`. These recovery copies were not removed.
Unrelated Streamlit logs and machine-specific run reports are not part of the commits.

## Restored implementation and repairs

- Restore the automatic qualifying monitor, immutable prediction versions,
  confirmed publication receipts, cutoff protections, and read-only Streamlit feed.
- Keep Monday data/accuracy refresh at 06:00 UTC and Monday stats sync at 06:00 UTC
  during March–December. All writers share non-cancelling concurrency and use
  fast-forward, conflict-checked publication.
- Configure Git author identity in all three workflows, including the private-index
  publisher's `commit-tree` operations.
- Persist check-start and final-check markers before fetching or training. Preserve
  those markers during successful actual-qualifying promotion, and record completion.
- Publish refreshed event metadata and status against exact prior remote bytes.
  Disjoint changes can be replayed; changed event, selection, status, or final
  context requires replanning. Frozen status and the final selection are committed
  together so a crash cannot leave a terminal status without its archive.
- Share one finished-race classifier across training and inference: `Finished`,
  `Lapped`, and `+N Lap(s)` are non-DNF after case/whitespace normalization.
  Retirements, non-starts, disqualifications, missing and unknown statuses remain
  DNF. Estimated and actual-qualifying inference use the same historical features;
  the backtest uses the same feature builder. No model tuning was performed.

This restores the implementation previously on feature1, not a new scheduling
redesign: the monitor wakes at minutes 7, 22, 37 and 52, with hourly qualifying
retry gates. Its estimated qualifying duration is 90 minutes, final verification
window 45 minutes before cutoff, and latest model-start buffer 15 minutes. These
are the restored code's settings, not the earlier proposed 180/30-minute policy.
Python 3.11 remains configured in ML workflows; dependencies are not newly locked.

## Preserved data and diagnostic output

The preserved 2026 cache contains 418 race rows and 412 qualifying rows, including
22 Mexico race rows and 21 Mexico qualifying rows. Earlier rounds were checked
against the preserved data. Main's updated stats and standings were retained.

The source response duplicated qualifying P8 for Lawson and Lindblad. Lawson's
qualifying observation was excluded based on the documented disqualification;
his race result remains. Evidence and the exception are recorded in
`ml/reports/2026-20-corrected/input_validation.json`. This is a preserved local data
correction, not a new ingestion rule: a future full-season refresh can reintroduce
the upstream row if the provider still returns it.

`ml/reports/2026-20-corrected/` contains a validated, **unpublished** Brazil round-20
candidate generated with corrected DNF features and Mexico history. It is not a
confirmed publication and must not be copied into the public feed as one. Its
roster is provisional from Mexico, including Hirakawa rather than Ocon.
Existing public prediction JSON and the Austin legacy reference were preserved.

Corrected backtest results are stored in `ml/models/live_metrics.json`:

| Evaluation window | Races | Live podium overlap | Live winner accuracy |
| --- | ---: | ---: | ---: |
| 2024–2026 | 67 | 69.7% | 58.2% |
| 2025–2026 | 43 | 70.5% | 60.5% |
| 2026 | 19 | 63.2% | 73.7% |

The podium backtest uses historical actual qualifying/grid inputs. It is **not**
an end-to-end assessment of forecasts made using estimated qualifying.

## Verification and deployment boundary

Local regression tests cover DNF interpretation, qualifying validation, event
timing, cutoff/freeze protection, publication receipts and conflicts, durable
checkpoints, and Streamlit saved-feed behavior. Publication integration tests use
disposable local bare Git repositories, never the real GitHub remote.

Commands used for verification:

```powershell
python -m pytest ml/tests -q
python -m pytest ml/tests/test_monitor_checkpoints.py -q
python ml/scripts/check_qualifying.py --dry-run
git diff --check
```

Verification completed locally: the full Python 3.12 suite passed 356 tests;
the six checkpoint tests passed separately, including the final atomic-freeze
test added after the full run's collection (357 distinct tests in the final tree).
Python 3.11 model/features/workflow regression coverage passed 52 tests. The
candidate validated again from UTF-8 JSON on disk, with Mexico present and Brazil
absent from both training manifests. The dry-run reported `event_bootstrap_required`;
both staged and unstaged whitespace checks passed.

Streamlit AppTest coverage exercises feed switching and last-known-good behavior.
A deployed, already-open
browser's 60-second polling loop has not been exercised against a real publication
in this restoration. The safe `--dry-run` checks scheduling only; it does not prove
end-to-end GitHub delivery.

After review, pushing and merging these commits would enable the restored workflow
on main. The monitor can bootstrap a missing upcoming-event feed; successful
deployment/publication must still be observed. Local commits alone do not change
the deployed prediction.
