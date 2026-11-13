# Main Prediction Data Compatibility Design

## Goal

Restore the Vercel production build while treating the prediction files already
committed on `main` as the only authoritative data. The chatbot must read the
current Las Vegas snapshot without replacing, regenerating, or copying data from
`feature2`.

## Scope boundary

- Do not modify `web/public/data/`, `ml/`, `.github/workflows/`, or the prediction
  pipeline.
- Do not overwrite `main` data with the older Brazil snapshot from `feature2`.
- Limit production changes to the chatbot data adapter and expectations in its
  tests.
- Preserve read-only access to historical prediction artifacts that already
  exist on `main`.

## Design

`web/lib/chatbot/data.ts` will accept the imported current snapshot through the
existing `PredictionInput` boundary instead of asserting that it is always a
schema-v2 file. The existing normalizer remains responsible for converting a
schema-v2 snapshot; a legacy snapshot passes through using its legacy field
names. This matches `main`, where the current Las Vegas file uses the legacy
shape while archived prediction files use schema v2.

The adapter will not select data from another branch or perform network writes.
Jolpica remains a read-only fallback under the existing chatbot rules.

## Error handling

Malformed or unavailable predictions continue to produce the existing
"Prediction unavailable" response. The fix must not synthesize a prediction,
silently replace the selected race, or weaken runtime race/date validation.

## Verification

1. Reproduce the current failure with `npx tsc --noEmit` or `npm run build` on
   commit `104b3c7`.
2. Apply the smallest adapter typing correction.
3. Update chatbot expectations to the Las Vegas snapshot committed on `main`.
4. Run the chatbot suite, TypeScript, scoped ESLint, and `npm run build`.
5. Confirm the final diff contains no prediction data, ML, or workflow files.

## Release

Commit the verified fix directly to `main` and push normally without force.
Vercel's Git integration should create a new production deployment from that
commit. Inspect the new deployment status and build log before reporting success.
