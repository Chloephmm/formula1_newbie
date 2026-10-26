# Automatic qualifying execution record

Branch: `feature1` (tracking `origin/feature1`, as explicitly requested).
Worktree: `.worktrees/automatic-qualifying-refresh`.
No remote push, merge, or deployment is authorized by this record.

## Decisions

- Use the documented estimated qualifying end (start + 90 minutes), with source/provenance.
- Retain the saved ML-based forecast until a valid actual-qualifying forecast is eligible.
- Preserve Monday schedules and work, with shared publication safety.
- User confirmed strict pre-cutoff availability verification; feed/browser display may lag.
- Existing hindsight backtests remain labeled benchmarks; live scoring uses saved archives.

## Task review ledger

| Task | Implementation | Spec review | Quality review |
|---|---|---|---|
| 1 Event timing and roster | 0d7378b + 7744f47 + 997c4e3; 39 focused / 44 full passed, 2 skipped | Passed after regression fixes | Passed after roster-coherence fixes |
| 2 State and deadline policy | In progress | Pending | Pending |
| 3 Qualifying validation | Pending | Pending | Pending |
| 4 Forecast/training modes | Pending | Pending | Pending |
| 5 Artifact contracts | Pending | Pending | Pending |
| 6 Publication and freeze | Pending | Pending | Pending |
| 7 Monitor and Monday jobs | Pending | Pending | Pending |
| 8 Saved-data UI reader/view | Pending | Pending | Pending |
| 9 End-to-end and RUN removal | Pending | Pending | Pending |
| 10 Documentation/migration | Pending | Pending | Pending |

## Verification

Baseline: `python -m pytest ml/tests -q --disable-warnings` — 7 passed, 2 skipped, 1 warning (21.91s). The skipped tests need the absent processed feature table. Local installed runtime is Python 3.12.10; planned CI runtime remains Python 3.11. Record any compatibility differences rather than claiming the local runtime is identical.
