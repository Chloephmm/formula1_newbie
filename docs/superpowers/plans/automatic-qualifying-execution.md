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
| 3 Qualifying validation | bfcedb2 + 103b4f4 + 32d5b97; 97 qualifying / 163 full passed, 2 skipped | Passed after four boundary fixes; final recheck passed | Passed after timing canonicalization and defensive driver-ID fixes; 141 combined focused tests passed |
| 4 Forecast/training modes | Pending | Pending | Pending |
| 5 Artifact contracts | Pending | Pending | Pending |
| 6 Publication and freeze | Pending | Pending | Pending |
| 7 Monitor and Monday jobs | Pending | Pending | Pending |
| 8 Saved-data UI reader/view | Pending | Pending | Pending |
| 9 End-to-end and RUN removal | Pending | Pending | Pending |
| 10 Documentation/migration | Pending | Pending | Pending |

## Current continuation

- User authorized continuing the next task with Subagent-Driven execution. This batch covers Task 3, preceded by the reviewed short-window correction in Tasks 1-2.
- Prerequisite correction implemented in 7beeae4: canonical event construction and schedule overrides allow a coherent schedule whose first check reaches or exceeds cutoff. Four composed regressions cover construction/override and equality/overrun. Independent focused verification: 58 passed; implementer full verification: 65 passed, 2 skipped. Independent spec and subsequent quality reviews passed with no remaining findings.
- Task 3 implemented by a fresh subagent after prerequisite review clearance. The initial spec review and parent probes found lossy event-ID coercion, malformed lap-time acceptance, continued fetching after a known page-count mismatch, and nullable missing merge identities. Regression tests reproduced the failures before fixes; spec re-review passed at 103b4f4. Quality review then found floating-point differences between equivalent lap formats and a defensive missing-driver-ID gap. Fixes in 32d5b97 use exact decimal arithmetic before one float conversion and reject invalid merge driver IDs; both spec and quality re-reviews passed with no remaining findings.
- Independent final full-suite verification at 32d5b97: 163 passed, 2 expected skips in 12.07 seconds. The quality reviewer independently passed 141 combined qualifying/Jolpica/event tests and checked 60,000 equivalent millisecond lap-format pairs. No live model generation, workflow/UI changes, live event overrides, or remote publication is part of this task.
- This batch is complete: Tasks 1-3 are implemented and reviewed, with 7 tasks remaining. Task 4 is next. RUN remains in the existing UI until Task 9; the new automatic workflow and publication path are not yet enabled.
- Fresh continuation baseline: 61 passed, 2 skipped (missing processed feature table). Tests use a unique temporary directory and disable pytest cache to avoid Windows ownership conflicts.
- Before later tasks, resolve the plan-review follow-ups: separate candidate eligibility verification from feed delivery; enforce the pre-qualifying initial deadline through publication; provide schedule bootstrap/recovery; assign archived-forecast scoring an explicit implementation/test task; guard feature-branch diagnostics from production publication; reconcile illustrative state snippets with the validated contract.

## Task 3 contracts

- `fetch_target_qualifying(season, round_number, get_page=None)` returns a `QualifyingFetch` containing normalized rows plus separately retained raw pages and retrieval metadata. It reuses the existing throttled Jolpica client; the season-wide Monday fetch interface is unchanged.
- `validate_qualifying(event, rows, page_evidence)` returns `AcceptedQualifying` with rows, canonical roster, semantic source version, notes, and imputation policy. Rejection exposes stable `code` / `reason_code` values.
- Accepted rows preserve official `quali_position` and actual `quali_time_gap_to_pole`; separate `model_position` and `model_quali_time_gap_to_pole` carry authorized model-only inputs. An unclassified eligible entrant needs an evidence-backed explicit positive integer `model_position`; no live exception was added.
- `replace_target_rows(existing, accepted_rows, season, round_number)` is a pure DataFrame merge. Fetching and validation perform no Parquet writes; later controller integration owns persistence after validation.
- The validation hash ignores retrieval timestamps, row/page ordering, page layout, and equivalent lap-time text while tracking semantic source and roster-policy changes. Raw timing strings remain available separately.
- Tests use injected HTTP fixtures, including incomplete/malformed responses and semantic-version equivalence. No live Jolpica request was used to establish correctness.

## Verification

Baseline: `python -m pytest ml/tests -q --disable-warnings` — 7 passed, 2 skipped, 1 warning (21.91s). The skipped tests need the absent processed feature table. Local installed runtime is Python 3.12.10; planned CI runtime remains Python 3.11. Record any compatibility differences rather than claiming the local runtime is identical.
