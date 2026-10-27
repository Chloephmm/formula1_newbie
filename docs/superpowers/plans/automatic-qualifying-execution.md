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
| 4 Forecast/training modes | a09d51d + ebd50f2; 22 focused / 180 full passed, 2 skipped | Passed; post-fix recheck passed | Passed after enriched-schema and wrapper fixes; no remaining findings |
| 5 Artifact contracts | Pending | Pending | Pending |
| 6 Publication and freeze | Pending | Pending | Pending |
| 7 Monitor and Monday jobs | Pending | Pending | Pending |
| 8 Saved-data UI reader/view | Pending | Pending | Pending |
| 9 End-to-end and RUN removal | Pending | Pending | Pending |
| 10 Documentation/migration | Pending | Pending | Pending |

## Completed Task 4 batch

- User authorized the next task. Task 4 is complete on `feature1` in the requested project directory, using a fresh implementer and independent spec/quality reviews, including post-fix re-reviews.
- Starting commit: e5b4dee. Fresh full-suite baseline: 163 passed, 2 expected missing-feature-table skips in 14.15 seconds. No existing working-tree edits preceded this task.
- Scope includes explicit forecast modes, strict pre-event raw-history filtering, backward-compatible feature-builder injection, and a narrow changed-input generation seam. Artifact contracts, scheduling/publication integration, and UI/RUN removal remain later tasks. No push, merge, deployment, live API request, or tracked forecast/data rewrite is authorized by this continuation.
- Initial implementation committed in a09d51d. Parent independent full verification: 178 passed, 2 expected skips. Spec review passed after checking the entire seven-file diff and additional cold-start, immutability, and reuse-context probes.
- Quality review and parent reproduction found a schema collision when Task 3's accepted qualifying rows (which include `circuit_id`) enter Stage 1 history. A parent wrapper probe also found that the existing `qualifying_start_at` field was not preferred over the display estimate. Both are fixed in ebd50f2, with a composed accepted-row-replacement/training regression and known-session/NaN-fallback wrapper coverage. Spec and quality re-reviews passed with no remaining findings; each reviewer independently passed all 22 focused tests.
- Independent final code verification at ebd50f2: 180 passed, 2 expected skips in 4.89 seconds; compilation of model, feature, and pipeline modules passed using an isolated temporary bytecode cache; committed diff check passed. All new forecasting/controller tests run from fixtures without live network or production model fitting.
- Task 5 must address the existing multiply-by-three podium normalization's possible values above 1, together with canonical provenance/artifact validation. Task 4 retains the model families and scoring baseline; it does not enable publication.
- Current progress: Tasks 1-4 complete, 6 tasks remaining. Task 5 is next. No saved forecast, model artifact, workflow, UI file, remote ref, or deployment was modified by this batch. RUN remains until Task 9.

## Task 4 contracts

- `forecast_event(event, *, mode, history, entries, models, qualifying=None)` selects only the explicitly supplied mode. Predicted qualifying calls Stage 1 then Stage 2; actual qualifying requires `AcceptedQualifying` and calls Stage 2 only. Actual generation leaves initial-mode lists empty rather than reconstructing the saved initial.
- `build_event_features(event, history, entries)` accepts raw `results` and `qualifying` DataFrames plus an explicit roster list/DataFrame. It filters by target identity and recorded cutoff before calculating features, retains existing cold-start values, and uses roster names/teams for substitutes.
- `retrain_live(..., history=None)` shares one cutoff-filtered raw snapshot across both stages. The optional raw-table arguments in both feature builders preserve their existing no-argument interfaces. Stage 1 accepts mixed legacy and validated qualifying schemas.
- `generate_actual_candidate(...)` validates the event input before fitting Stage 2, or reuses a successful candidate only when its input hash, event, mode, source version, and cutoff match. It performs no fetching, scheduling, persistence, Git operations, or publication. Canonical hashing and artifact validation remain Task 5 responsibilities.
- Official qualifying positions and actual missing gaps remain distinct from model-only positions/gaps. Independent composition checks include an explicitly authorized unclassified entrant, without inventing an official classification.
- `forecast(asof, models=None)` is explicitly an offline, predicted-only reconstruction wrapper. It never treats cached target qualifying or the selected date as proof of actual availability. Known schedule fields take precedence; an older date-only cache retains the explicitly labeled display estimate only. No session timing or mode eligibility is derived from that estimate in the new production interfaces.

## Completed Task 3 batch

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
