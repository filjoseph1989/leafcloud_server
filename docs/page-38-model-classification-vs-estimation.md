[Prev](./page-37-model-analysis-v3-v5.md) | [Next](./page-39-model-regression-limitations.md)

# Classification vs. Estimation — What the App Can and Cannot Do

**Date:** 2026-05-29  
**Context:** Post V5-run4 evaluation, after observing incorrect dashboard PPM and anomaly triggers from regression output

---

## The Core Problem

The regression head (`reg_output`) in all V3–V5 models was trained with **discrete targets only**:

```python
CONCENTRATION_MAP = {
    'Water': [0.0, 0.0],
    'NPK':   [1.0, 0.0],  # V5 (was [2.0, 0.0] in V3)
    'Micro': [0.0, 1.0],  # V5 (was [0.0, 2.0] in V3)
    'Mix':   [1.0, 1.0],  # V5 (was [2.0, 2.0] in V3)
}
```

Every training sample has a regression target of either `0.0` or `1.0` — never anything in between. The model has never seen a target of `0.7` or `0.4`, so it cannot reliably output those values to represent actual depletion.

**No amount of architecture tuning or loss weight adjustment will fix this.** The problem is the data, not the model.

---

## Why V3 Used `[2.0]` and V4/V5 Changed to `[1.0]`

| | V3 — `[2.0, 0.0]` + `linear` | V4/V5 — `[1.0, 0.0]` + `sigmoid` |
|--|--|--|
| Scale | 0 to 2.0 ("full dosage") | 0 to 1.0 (normalized) |
| Activation | Linear — unbounded output | Sigmoid — bounded to [0, 1] |
| Reasoning | Original design | "More principled, no unbounded outputs" |
| NPK recall | **0.92** | 0.37–0.78 |
| Macro R² | 0.01 | -0.27 to -0.46 |

The V4/V5 change was theoretically sound (sigmoid + [0,1] is cleaner) but in practice it hurt classification. V3's larger `[2.0]` target created a **stronger gradient signal** during training — when the model predicted 0.5 for NPK (true=2.0), the error was 1.5 and the correction was strong. With [1.0] + sigmoid, gradients near saturation are small, and the shared representation got a weaker signal to distinguish NPK from other classes.

Neither approach solved regression because **discrete targets are the root problem**, regardless of scale or activation.

---

## What the Regression Output Currently Produces (V5-run4)

Per-class regression breakdown from evaluation:

| Class | Macro pred (avg) | Macro true | Micro pred (avg) | Micro true |
|-------|-----------------|-----------|-----------------|-----------|
| Water | 0.29 | 0.0 | 0.00 | 0.0 |
| NPK | 0.72 | 1.0 | 0.43 | 0.0 |
| **Micro** | **0.59** | **0.0** | 1.00 | 1.0 |
| Mix | 0.88 | 1.0 | 1.00 | 1.0 |

Key failures:
- **Micro predicts macro≈0.59** (true=0.0) — triggers false anomaly detection since threshold is >0.5
- **NPK predicts macro≈0.72** (true=1.0) — under-predicts
- **Water predicts macro≈0.29** (true=0.0) — over-predicts
- Overall Macro R² = **-0.27** — worse than predicting the mean

---

## What Actually IS Useful

### 1. Classification (83.62% accurate) — works well

The model correctly identifies *what type* of nutrient solution is in the tank. This drives:
- Profile display ("Balanced Mix", "Micro-Leaning Blend", etc.)
- Which nutrients need topping up
- Anomaly detection between visual and sensor data

### 2. Class transitions as depletion tracking

As plants consume nutrients, EC drops naturally. The class transitions over days ARE a form of depletion tracking — discrete steps rather than a smooth curve:

```
Fresh tank:   EC ≈ 0.99  →  Mix   →  ~1,940 PPM
Depleting:    EC ≈ 0.75  →  Micro →  ~760 PPM
Nearly gone:  EC ≈ 0.50  →  NPK   →  ~1,180 PPM
Depleted:     EC ≈ 0.20  →  Water →  ~0 PPM
```

The farmer sees the class change over time and knows to act. This is real, usable information.

### 3. The EC sensor is the best real-time depletion proxy

EC drops as nutrients are consumed. The classification layer translates EC transitions into human-readable labels and top-up instructions — which is more useful than just showing a raw EC number.

---

## What Is NOT Working

**Smooth in-between estimates** — "you have 67% nutrients remaining" or "macro is at 0.4."

This requires training data with **measured intermediate concentrations** at different depletion states across the experiment lifecycle. That data does not currently exist. The training data only has a `bucket_label` per experiment (Water/NPK/Micro/Mix), not per-day concentration measurements.

This is a **V6 requirement** — see [model-regression-limitations.md](model-regression-limitations.md).

---

## Recommended Fix: Classification Lookup in ai_service.py

Instead of using the regression output (`reg_output`) to drive `macro_scale` and `micro_scale`, derive them from `predicted_class` via a fixed lookup table:

```python
SCALE_LOOKUP = {
    'Water': (0.0, 0.0),
    'NPK':   (1.0, 0.0),
    'Micro': (0.0, 1.0),
    'Mix':   (1.0, 1.0),
}
macro_scale, micro_scale = SCALE_LOOKUP[predicted_class]
```

**Benefits:**
- No false anomalies — Micro will always have macro=0.0, not 0.59 from broken regression
- Correct PPM per class — predictable, consistent
- No retraining required — pure backend change
- Regression output can still be saved to DB for future analysis

**Expected PPM per class with lookup:**

| Class | macro_scale | micro_scale | Total PPM |
|-------|------------|------------|-----------|
| Water | 0.0 | 0.0 | 0 |
| NPK | 1.0 | 0.0 | ~1,180 |
| Micro | 0.0 | 1.0 | ~760 |
| Mix | 1.0 | 1.0 | ~1,940 |

---

## Honest Summary

| Capability | Status | Notes |
|-----------|--------|-------|
| Identify nutrient class (Water/NPK/Micro/Mix) | ✅ Working — 83.62% | Main value of the system |
| Show class-based PPM estimate | ✅ With lookup fix | Discrete steps, not continuous |
| Track class transitions over days | ✅ Working via EC drop | Usable depletion indicator |
| Smooth real-time depletion % (e.g. 67%) | ❌ Not working | Requires V6 training data |
| Anomaly detection (visual vs sensor) | ⚠️ Partially — false positives on Micro | Fixable with lookup |

The app is a **class-based monitoring system** — it tells the farmer *what* is in the tank and *when to act*. It is not yet a precise depletion meter that tracks percentages in real time. The estimation formula in `iot.py` is mathematically correct — it just needs reliable input, which means the classification lookup rather than the broken regression output.
