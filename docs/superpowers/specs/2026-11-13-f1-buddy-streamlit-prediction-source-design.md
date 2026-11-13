# F1 Buddy Streamlit Prediction Source Design

## Goal

For prediction questions, F1 Buddy must read forecasts published for the
Streamlit ML Prediction dashboard. A generic “next race prediction” request
must show the latest confirmed forecast for the upcoming event even when that
forecast was generated on an earlier calendar date.

## Source boundary

- Streamlit's deployed dashboard reads the confirmed
  `main/web/public/data/prediction_feed.json` from the repository's raw GitHub
  URL. F1 Buddy will fetch that same fixed URL on its Next.js server. It will
  never scrape Streamlit HTML or invoke the Streamlit or ML process.
- Only a validated `feed.current` selection with a confirmed publication
  receipt may provide the generic next-race forecast. The `feed.event` identity
  and `current_event_id` must match the selected prediction and publication.
- Named race predictions use forecast artifacts that the Streamlit dashboard
  exposes through its archive index and confirmed event feeds. The chatbot's
  separate `predictions.json` historical estimate fallback is removed from
  prediction answers. Actual results may still be shown under a separate
  “actual result” label when a requested prediction is unavailable.
- Jolpica supplies schedules and actual results only. It never supplies
  qualifying picks, podium probabilities, or any other forecast values.
- Model accuracy remains a distinct metrics answer using the already
  published `metrics.json`; it is not a race prediction.

## Current-race selection and display

1. Parse a generic request such as “next race prediction” as a prediction
   request with no named race.
2. Fetch the confirmed feed on the server. Validate its schema, revision,
   event identity, selected prediction, and confirmed publication receipt
   before reading forecast rows. Reject malformed or mismatched data.
3. Require the selected event's `race_start_at` to be later than the request
   time. If the feed has not rolled over after a race starts, do not call that
   completed event the “next race.”
4. Select `current.prediction`, which is the latest confirmed forecast for
   this event. A `feed_updated_at` status change does not itself imply a new
   forecast. Use the prediction's `generated_at` and the receipt's
   `published_at` as the displayed provenance.
5. For `predicted_qualifying`, show the published predicted qualifying and
   pre-qualifying podium rows. For `actual_qualifying`, show the published
   actual qualifying and updated podium rows with an explicit post-qualifying
   label. Restore presentation order from row position/rank before taking the
   top three, as Streamlit does.
6. Keep the link to the full Streamlit prediction dashboard. Do not rerun,
   retrain, or synthesize a prediction in chat.

The current feed identifies Las Vegas 2026 as the active event. Its confirmed
prediction was generated on November 9, 2026, while the race is scheduled for
November 22. The November 9 date must not cause a generic request on
November 13 to return “Prediction unavailable.”

## Fetching and failure behavior

- Use the fixed raw GitHub feed URL, a five-second request timeout, and a
  short server-side cache of about 60 seconds. Conditional ETag requests may
  reduce repeated transfer. Cache only validated data. Cache state is local
  to a server instance; correctness must not depend on a shared cache.
- When a refresh fails, a previously validated cached selection may be used
  for the same event while its race start remains in the future. Clearly mark
  the response as a cached published forecast and retain its publication time.
- With no usable confirmed feed or cached selection, respond that the
  prediction is unavailable. Do not fall back to the bundled
  `next_race_prediction.json`, a generated estimate, another race, or Jolpica
  for forecast values.
- A missing `current` selection, invalid receipt, race-identity mismatch,
  invalid forecast, or event that has started is unavailable. A later valid
  feed for the next event replaces the cached event.

## Implementation boundaries

- Add a focused server-only feed reader and validator under
  `web/lib/chatbot/`. Its fetch transport and clock are injectable for tests.
- Keep the existing F1 Buddy UI and API response contract. The prediction
  responder becomes asynchronous so it can obtain the published feed.
- Keep non-prediction intents and existing race, standings, driver, and team
  data paths unchanged.
- Do not edit prediction artifacts, ML model or publisher code, Streamlit
  rendering, or automation workflows for this change.

## Verification

Test the generic request against a confirmed forecast whose publication date
precedes the request date; a newer confirmed post-qualifying forecast; a race
rollover; missing `current`; invalid revision or receipt; mismatched event;
upstream outage with and without a validated cached selection; and a race
that has already started. Test named archived predictions and confirm that
`predictions.json` is never used as a forecast fallback. Run chatbot tests,
TypeScript, scoped ESLint, and a production Next.js build. Review the diff to
confirm prediction data and ML files are unchanged.
