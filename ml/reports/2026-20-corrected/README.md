# Brazil 2026 corrected local candidate

This is an **unpublished diagnostic prediction**, not a confirmed public forecast.
It was generated on 2026-11-02 with the shared finished/lapped status correction,
using historical data through Mexico round 19 and excluding Brazil round 20.
Model architecture and predictive hyperparameters were unchanged.

| Driver | Predicted podium probability |
| --- | ---: |
| Max Verstappen | 81.21% |
| Charles Leclerc | 76.83% |
| Lewis Hamilton | 52.50% |
| George Russell | 18.10% |
| Kimi Antonelli | 14.69% |

These are podium probabilities, not win probabilities or predicted finishing
positions. The full classification and qualifying estimates are in `prediction.json`.
The artifact includes its source/model hashes and generation-time provenance;
later publication-adapter edits do not retroactively alter that provenance.

`event.json` records schedule and provisional entrants copied from the latest
completed race, including Hirakawa instead of Ocon. `input_validation.json`
documents the Mexico qualifying exclusion for Lawson while preserving his race
result. Review the roster and source exception before any future publication.

The existing public snapshot was deliberately left unchanged. This directory has
no publication receipt, and its contents must not be presented as a frozen or
confirmed historical prediction. See `docs/feature1-restoration-2026-11-02.md`
for restoration scope, verification limitations, and backtest methodology.
