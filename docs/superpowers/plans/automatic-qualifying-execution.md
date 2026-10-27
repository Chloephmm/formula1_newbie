# Automatic qualifying execution record

Branch: `feature1` (tracking `origin/feature1`, as explicitly requested).
Working directory: `C:/Users/user/Documents/Projects/formula1_newbie` (direct checkout, explicitly requested).

Relocated after Task 2 by fast-forwarding this clean feature1 checkout with all 10 local commits through 2681000. The previous checkout at `C:/Users/user/Documents/Codex/Formula1` remains intact as a backup; no remote push occurred.
Relocation verification: source and destination HEAD/tree matched; the ML test suite passed in the new directory (61 passed, 2 skipped). Tests used a fresh, uniquely named temporary directory to avoid a Windows permission conflict with an existing pytest temporary root. Only disposable test/Python caches were left behind in the former implementation worktree.
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
| 2 State and deadline policy | 35bd7ee + e745866 + 7c0bf93; 17 focused / 61 full passed, 2 skipped | Passed after terminal-state regression fixes | Passed; minor status issues also fixed |
| 3 Qualifying validation | In progress | Pending | Pending |
| 4 Forecast/training modes | Pending | Pending | Pending |
| 5 Artifact contracts | Pending | Pending | Pending |
| 6 Publication and freeze | Pending | Pending | Pending |
| 7 Monitor and Monday jobs | Pending | Pending | Pending |
| 8 Saved-data UI reader/view | Pending | Pending | Pending |
| 9 End-to-end and RUN removal | Pending | Pending | Pending |
| 10 Documentation/migration | Pending | Pending | Pending |

## Verification

Baseline: `python -m pytest ml/tests -q --disable-warnings` — 7 passed, 2 skipped, 1 warning (21.91s). The skipped tests need the absent processed feature table. Local installed runtime is Python 3.12.10; planned CI runtime remains Python 3.11. Record any compatibility differences rather than claiming the local runtime is identical.
