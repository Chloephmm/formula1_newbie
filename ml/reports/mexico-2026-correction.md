# Mexico City forecast correction — 2026-19

Implemented and published locally on 2026-10-30. No commit, push, deployment or
remote GitHub workflow dispatch was performed. The existing UI was not changed
by this correction.

## Forecast comparison

| Driver | Previously saved podium probability | Corrected |
| --- | ---: | ---: |
| Verstappen | 71.67% | 74.67% |
| Leclerc | 61.70% | 63.63% |
| Hamilton | 52.75% | 53.38% |
| Antonelli | 41.03% | 34.92% |
| Russell | 32.17% | 21.31% |

Qualifying estimates are unchanged. All 22 entrants are present; the rounded
podium probabilities sum to 3.0. The forecast still uses **estimated qualifying**.
Actual qualifying will be handled by the existing automated publication schedule.

The full per-driver probability, qualifying and DNF-feature comparison is in
`mexico-2026-comparison.json`; the validated candidate is in
`mexico-2026-candidate.json`. DNF comparisons reconstruct the old classification
rule on the same cached data. They do not recover the original model environment.
The cause of the original saved-versus-local discrepancy remains unconfirmed;
these probability changes must not be attributed to the DNF fix alone.

## Changes

- Shared normalized finish classification: lapped finishers no longer count as DNF.
- Race-local pit-lane grid defaults eliminate dependence on later field sizes.
- Canonical row order, deterministic single-thread CPU fits, unchanged model
  hyperparameters/calibration and feature lists.
- Python 3.11.14 dependency lock, explicit Ubuntu 24.04 workflow runner and genuine
  stage-specific training provenance. Stage 1 survives actual-mode updates;
  replacement models without provenance cannot inherit stale Stage 2 metadata.
- Schedule-only cache migration, candidate/comparison commands and guarded
  publication. Status-only hourly runs cannot revert newer active predictions.
- Stronger candidate validation and pre-training/pre-write freeze, cutoff and
  actual-to-estimated downgrade protections.
- Existing backtest metrics recomputed. Workflow schedules/output allowlists,
  archived forecasts and UI layout preserved.

## Verification

- Locked Python 3.11 environment: **119 passed** (ML/publication/feed suites).
- Existing Python 3.12 environment: **121 passed**, including Streamlit smoke tests.
- Processed feature table rebuilt: 5,501 rows, seven features, zero missing feature values.
- Two independent real-data fits produced exactly equal published qualifying and
  podium arrays, with equal training-table hashes.
- Both stages use 270 historical races. Stage 1 uses 5,422 rows with valid qualifying
  targets; Stage 2 uses 5,501 rows. Mexico round 19 is excluded; Austin round 18 is included.
- Only the schedule raw-data file changed; cached race/qualifying results did not.
- Austin archive SHA-256 remains
  `5426e740cf9ab54423ccc70db4fd4b377d67af751b09e0ab10d228df808a8681`.
- Spec review and separate code-quality review completed without remaining blockers.
- After publication, the existing tab at `http://127.0.0.1:8503/` changed from
  VER 72% / LEC 62% to VER 75% / LEC 64% through normal polling. No click,
  navigation, browser refresh or visitor-triggered model run was used.
- Post-publication Streamlit/feed checks: **7 passed**; active/archive JSON and
  status publication timestamps agree.

Local reproduction was verified on Windows; the Ubuntu GitHub jobs were not
dispatched. The lock and provenance document the runtime rather than promising
bit-identical results across operating systems.

## Existing backtest results

Across 66 races in 2024–2026, live podium hit rate is 69.19%, winner accuracy
57.58%, qualifying pole accuracy 27.27%, and mean qualifying-position error 3.35.
The reported median-gap metric averages each race's median absolute error
(0.554 seconds). The podium backtest uses actual qualifying and an uncalibrated
base model; it does **not** measure the complete estimated-qualifying production
pipeline. No evaluation methodology or accuracy-bar layout was redesigned.

See `docs/ml-reproducibility.md` for setup and safe candidate/publication commands.
