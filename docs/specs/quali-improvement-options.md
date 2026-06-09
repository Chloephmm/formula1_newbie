# Qualifying-Model Improvement Options (tested)

Three options were tested to reduce the **mean grid error** of the Stage-1 qualifying
model (the predicted-grid accuracy used in the pre-qualifying mode). Each was run as a real
experiment on the test seasons (2024–2026).

**Baseline (current model):** calibrated LightGBM regressor → **3.45** positions mean grid error.

## Results at a glance

| Option | Tested result | vs baseline | Decision |
|---|---|---|---|
| 1. Driver/team identity features | 3.84 | ❌ worse | **Rejected** |
| 2. Rank objective (LambdaRank) | 3.31 | ✅ −0.14 (~4%) | **Not adopted** (marginal + side effects) |
| 3. FastF1 practice pace | 3.07 *(alone)* · ~2.6–2.9 *(est. in model)* | ✅ best signal | **Deferred to future** → `fastf1-plan.md` |

---

## Option 1 — Driver / team identity features
Add `driver_id` and `constructor_id` as categorical features so the model can learn
persistent skill ("this driver always qualifies well").

**Tested:** 3.84 positions — **worse** than the 3.45 baseline.

**Advantages**
- Captures persistent driver/team qualifying skill.
- Free — no new data, easy to add.

**Disadvantages**
- **Made it worse in practice.**
- **Cold-start:** 2024–26 rookies / new teams (Antonelli, Bortoleto, Cadillac, Audi) aren't
  in the ≤2022 training data → their identity is noise.
- **2026 regulation reset:** historical "who qualifies well" is less relevant when the cars change.
- Overfits to past identities.

**Verdict: Rejected** — hurts accuracy.

---

## Option 2 — Rank objective (LambdaRank)
Switch Stage-1 from regression ("predict each driver's lap-time gap, then sort") to
**learning-to-rank** ("learn the grid order directly"). LambdaRank optimizes the ordering
itself, focusing on getting the front of the grid right.

**Tested:** 3.31 positions — **slightly better** (−0.14, ~4%).

**Advantages**
- Free — same data/features, just a different training objective.
- Optimizes ordering directly (which *is* what grid error measures).
- Emphasizes front-of-grid accuracy (the part that decides the podium).
- No extra runtime cost.

**Disadvantages**
- Gain is **tiny (~0.14 position)** — within noise on a ~48-race test set.
- **Critical side effect:** a ranker outputs an *ordering score*, **not a gap in seconds** —
  but `quali_time_gap_to_pole` (the gap) is the **podium model's #1 feature**. Adopting it
  cleanly would require either *two* Stage-1 models (ranker for order + regressor for gap)
  or a faked gap → more complexity, uncertain net effect on the final podium.

**Verdict: Not adopted** — marginal gain, and it removes/complicates Stage 2's most
important input. Documented as "tested, didn't beat it cleanly."

---

## Option 3 — FastF1 practice pace (future)
Add a `practice_pace` feature (each driver's best practice lap → gap-to-fastest) from
**FastF1** practice sessions. Practice pace is the strongest pre-qualifying signal.

**Tested (spike):** ranking by **practice pace alone** gave **3.07** positions (Spearman
0.71 with actual qualifying) — better than the 3.45 baseline *even with no model*. Blended
into the model, estimated **~2.6–2.9**.

**Advantages**
- **Strongest signal tested** — a real, meaningful improvement.
- Genuine "I integrated telemetry/practice data" showcase for the portfolio.
- Helps exactly in the pre-qualifying weekend window (after practice, before quali).

**Disadvantages**
- Real **engineering cost** — FastF1 integration, GBs of downloads, data only back to 2018.
- **~2× RUN latency** (downloads the target race's practice; ~45–90s first time).
- **Heavier deployment** — FastF1's cache doesn't fit Streamlit Cloud well (live downloads
  per request).
- Benefit only in a **narrow window** (after practice, before qualifying); before practice
  it falls back to form-only, and after qualifying the real grid takes over.

**Verdict: Deferred — future enhancement.** Full design in
[`fastf1-plan.md`](fastf1-plan.md). Worth building as a FastF1 showcase; not essential for
accuracy since the real-grid mode already gives the exact grid once qualifying runs.

---

## Final decision
**Keep the current calibrated LightGBM regressor** (3.45). Identity features hurt; the rank
objective's gain was within noise and broke the gap feature; FastF1 practice is the only
option with a real upside and is **documented for future implementation** (`fastf1-plan.md`).

> Portfolio framing: *"I benchmarked three ways to improve the qualifying model — driver/team
> identity (worse), a LambdaRank objective (within noise + removed the podium model's key
> feature), and FastF1 practice pace (best signal, ~3.07 alone). I kept the calibrated
> regressor and scoped the FastF1 upgrade for the future."*
