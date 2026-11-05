# Feature2 qualifying pipeline execution record

## Scope

Implemented on the user's existing `feature2` checkout, starting at `c9abe03`.
No new worktree, production publication, merge, deployment or server was started.
Changes are intentionally uncommitted for review and the user's later merge.

Source plan: `2026-10-26-automatic-qualifying-refresh.md`, supplied from
`C:/Users/user/Documents/Projects/formula1_newbie/docs/superpowers/plans/`.
That document includes a prior feature1 execution history; its completion claims
are not evidence of deployment or verification of this feature2 implementation.

## Implementation mapping

| Plan area | Feature2 implementation |
| --- | --- |
| Event contract and timing | `ml/src/pipeline/events.py`, `state.py`; UTC, observed end or explicit +90-minute estimate, five-hour wait, hourly retry, final reserve, immutable freeze |
| Exact-event input validation | `qualifying.py`; pagination, identity, roster, classified/no-lap validation and evidence-backed exceptions |
| Leakage-safe model inputs | `ml/src/model/event_forecast.py`, explicit raw-history arguments in feature builders and retraining; filter before features; actual mode Stage 2 only |
| Reproducibility | Preserve feature2 deterministic parameters and DNF semantics; content hashes and complete runtime/model manifests |
| Artifacts/publication | `artifacts.py`, `publish.py`; immutable candidates, remote byte confirmation before deadline, receipts, atomic feed, fast-forward conflict handling |
| Workflow controller | `check_qualifying.py`; stdlib due gate, durable attempt markers, schedule recheck after training, freeze selection |
| Monday responsibilities | `refresh_for_next_race.py`, `precompute_confirmed.py`, `publish_refresh.py`; original schedules and five fetches retained; next initial, benchmark, saved evaluation and archived final |
| Saved-only dashboard | `prediction_data.py`, `confirmed_feed.py`, existing `app.py` layout; shared cache, fragment reruns, confirmed receipt/ID/timestamps, same-event last-good behavior |
| Live evaluation | `evaluation.py`; separate confirmed initial/final metrics; legacy references explicitly excluded |
| Migration | Preserve existing public forecasts and raw datasets. Add only an evidenced Austin legacy reference, not a fabricated schema-2 initial |

The existing rendering layout was retained instead of replacing it with the older
reference app. The adapter exposes canonical feed content to those rendering
helpers. Older compatibility/diagnostic scripts remain but are not called by the
production workflows.

## Local verification

Final checks on 2026-11-04:

| Command/check | Observed result |
| --- | --- |
| `python -m pytest ml/tests --ignore=ml/tests/test_prediction_publication.py -q --tb=short` | 398 passed, 2 skipped; skips require the absent generated processed-feature dataset |
| Full publication suite | 53 passed, 1 transport timeout during the long-running session |
| Publication rerun: `-k 'feed or freeze or promotion_rechecks_all_uploaded_bytes_after_concurrent_change'` | 22 passed, 32 deselected; includes the timed-out case and affected feed/freeze paths |
| `python -S ml/scripts/check_qualifying.py --dry-run --now 2026-11-04T12:00:00Z` | Exit 0; `event_bootstrap_required`; no live feed is seeded locally |
| Actionlint with the narrowly documented queue compatibility exception below | Exit 0 |
| `git diff --check` with repository line-ending settings | Exit 0 |

Python checks used CPython 3.11.14 with the existing locked test environment and
Streamlit 1.66.1. The original full publication run was not clean; the failed case
passed the targeted rerun. These results are local evidence, not a hosted CI run.

Tests cover boundary timestamps, missing/partial/corrected qualifying, no redundant
training, feature leakage, hashes, publication deadlines, failed pushes and remote
conflicts, final selection, Monday rollover, legacy exclusion, and dashboard reads.
Git-publication tests use disposable local bare repositories, never the real origin.

The dashboard AppTest switches a fixture feed from estimated to actual qualifying
and confirms that mode and prediction ID change together on rerun. Training and
Jolpica functions are patched to fail if a visitor invokes them. This is not proof
of a timed rerun in a deployed, already-open browser.

`check_qualifying.py --dry-run` is checked with Python `-S`, so the cheap gate cannot
depend on installed ML packages. Use this safe command locally; production entry
points require the original repository's GitHub Action environment on `main`.

Actionlint 1.7.12 rejects only the new `concurrency.queue` property. GitHub's
[current concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
explicitly supports `queue: max` with `cancel-in-progress: false`. Validation with
only that exact diagnostic ignored passes; shellcheck is unavailable and disabled.
The queue setting is retained to prevent monitor ticks from replacing pending
Monday runs. No other actionlint warnings are suppressed.

An independent review agent could not run because of the account usage limit.
Local review and automated checks were performed; independent review remains open.

## Acceptance still required after authorized merge/deployment

- Review and commit this feature2 diff, then merge to `main` when approved.
- Confirm the three Actions are enabled and the repository token may write contents.
- Seed a genuine initial before qualifying; if that deadline is missed, retain
  `missing_initial` and wait for eligible actual qualifying. Never backdate a forecast.
- Check the published raw GitHub feed URL and immutable receipt bytes from the
  deployed environment, not only a local checkout.
- Keep a deployed page open through a saved-feed transition. Without a click or
  manual reload, verify mode and prediction ID update together, actual values are
  retained on transient failure, and Monday rollover preserves an explicitly
  selected archive race. Scheduling/cache delays mean exactly 60 seconds is not
  guaranteed.
- Verify the final selected receipt predates the two-hour cutoff, and late runs do
  not replace it. Check Monday completed results, metrics and next-event forecast.

Until those checks are performed, this is a locally implemented pipeline, not a
claim that GitHub automation or the deployed page is already running this version.

## Post-merge bootstrap repair (2026-11-05)

Hosted qualifying publisher run [41942994403](https://github.com/Chloephmm/formula1_newbie/actions/runs/41942994403)
failed before training because the committed legacy schedule cache has no
`schedule_source`. The existing public forecast was not replaced.

The local `feature2` repair fetches a fresh Jolpica calendar when that provenance
is missing or blank, requires exactly one matching season/round, and retains the
normal event validation. It does not invent provenance or overwrite raw caches.
API errors and ambiguous/missing target events fail before model execution.

Verification for this repair:

- Ten bootstrap regression cases: nine failed before the fix and all ten pass
  afterward. Related targeted suites: 68 passed.
- ML suite excluding the unchanged publication suite: 408 passed, 2 existing
  skips for the absent generated processed-feature dataset. The publication
  suite was not rerun for this repair.
- A live-calendar, in-memory Brazil round 20 forecast passed artifact validation
  using the round 19 prior-race roster. Both model stages ran; no output was
  saved or published. Calendar observation: `2026-11-05T00:44:44Z`.
- Focused independent inspection reported no correctness issue, but its
  subsequent verification attempt was interrupted by the account usage limit;
  it did not provide a completed review sign-off.

This repair remains local and uncommitted on `feature2`. Commit/push and merge
are user-controlled. A successful hosted bootstrap and published-feed check are
still required after the repair reaches `main`.
