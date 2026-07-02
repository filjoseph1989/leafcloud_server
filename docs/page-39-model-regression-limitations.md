[Prev](./page-38-model-classification-vs-estimation.md) | [Next](./page-40-model-v6-evaluation-analysis.md)

# Regression Output Limitations and V6 Roadmap

**Date:** 2026-05-29  
**Applies to:** `leafcloud_multimodal_v5_*.keras` and all prior versions

---

## Current Behavior

The dashboard reads `macro_scale` and `micro_scale` from the `npk_predictions` table, which are the raw regression outputs from `reg_output` in the AI model ([ai_service.py:124-125](../app/services/ai_service.py)).

These values are used to:
- Calculate estimated PPM (`n_ppm`, `p_ppm`, `k_ppm`)
- Trigger `HEALTHY` vs `NUTRIENT DEFICIENT` health status
- Generate top-up advisories and alerts
- Drive anomaly detection (e.g. predicted_class=Water but macro_scale > 0.5)

---

## The Discrete Target Problem

All versions (V3–V5) trained the regression head using a discrete concentration map:

```python
CONCENTRATION_MAP = {
    'Water': [0.0, 0.0],
    'NPK':   [1.0, 0.0],
    'Micro': [0.0, 1.0],
    'Mix':   [1.0, 1.0],
}
```

Every training sample has a target of either `0.0` or `1.0` — nothing in between. The model has **never seen a training example with macro=0.7 or macro=0.4**, so it cannot reliably output those values to represent actual depletion.

---

## What the Scale Values Actually Represent

| Value range | Meaning in practice |
|-------------|---------------------|
| ≈ 1.0 | Model is confident nutrients are present (EC in expected class range) |
| ≈ 0.0 | Model sees no nutrients (Water class or wrong EC) |
| 0.4 – 0.9 | Model is uncertain — EC near a class boundary, or ensemble of crops gives mixed signals |

Values like `0.9` or `0.7` appear when:
1. EC is near a class boundary (e.g. Mix EC dropping toward 0.86 mS/cm minimum)
2. The 5-crop ensemble produces mixed predictions across image crops

They do **not** represent a smooth, trustworthy "70% nutrients remaining" reading.

---

## Actual Depletion Pattern

Instead of a smooth gradient, the model produces a **step function** as nutrients deplete and EC drops:

```
EC 0.86–1.51  →  Mix   → macro≈1.0, micro≈1.0
EC 0.66–0.85  →  Micro → macro≈0.0, micro≈1.0
EC 0.41–0.65  →  NPK   → macro≈1.0, micro≈0.0
EC < 0.40     →  Water → macro≈0.0, micro≈0.0
```

The transition between steps (where intermediate values like 0.7 appear) corresponds to the EC boundary zone between classes, not actual measured nutrient concentration.

---

## Original Design Intent vs. Reality

The original design goal (documented in [page-25-how-estimation-works.md](page-25-how-estimation-works.md)) was to track readings like:

> `Macro: 1.98 → 1.45 → 0.60` as plants absorb nutrients over time

This requires training data with **continuous, measured depletion** — sensor readings taken across multiple days per experiment with targets derived from actual nutrient concentration at each point, not just a single bucket label.

That data does not currently exist in the training set. The training data has `bucket_label` (Water/NPK/Micro/Mix) per experiment, not per-day concentration measurements.

---

## Known Regression Metrics (V5-run4)

| Metric | Value | Status |
|--------|-------|--------|
| Macro (NPK) R² | -0.27 | Still negative — not yet usable for depletion tracking |
| Micro R² | 0.54 | Moderate — micro predictions more reliable than macro |
| Overall R² | 0.13 | Low overall regression quality |

Macro R² is negative, meaning the regression for macro concentration is **worse than simply predicting the mean**. The model is not yet reliable enough to drive depletion advisories directly.

---

## Why the Dashboard Still Works

Despite poor regression, the dashboard produces correct `HEALTHY` / `NUTRIENT DEFICIENT` status because:
- A freshly-mixed tank has EC in the correct class range → model predicts macro≈1.0
- A depleted tank has dropping EC → model transitions to Water class → macro→0.0
- The anomaly detection catches cases where classification and regression disagree

The step-function behavior is sufficient for binary "needs top-up / doesn't need top-up" decisions, even though it cannot track gradual depletion.

---

## V6 Requirement: Continuous Depletion Targets

To enable true smooth depletion tracking, V6 training data needs:

1. **Per-day EC readings** for each experiment bucket, from day 1 (fresh solution) through depletion
2. **Normalized depletion target** derived from EC relative to the initial fill:
   ```
   macro_remaining = current_ec / initial_ec   (for NPK/Mix buckets)
   micro_remaining = current_ec / initial_ec   (for Micro/Mix buckets)
   ```
3. Training samples at intermediate depletion states (e.g. 0.3, 0.5, 0.7, 0.9) so the model can learn the visual and sensor signatures of partial depletion

Without this, regression will remain a step function regardless of architecture improvements.
