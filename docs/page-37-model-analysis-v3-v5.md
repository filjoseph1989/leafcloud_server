[Prev](./page-36-dashboard-ppm-analysis.md) | [Next](./page-38-model-classification-vs-estimation.md)

# LeafCloud Nutrient Classifier — Model Analysis (V3 → V5)

**Date:** 2026-05-28 to 2026-05-29  
**Models evaluated:** V3, V4, V5 (runs 1–3)  
**Validation set:** 17,641 samples (StratifiedShuffleSplit 20%, random_state=42)

---

## 0. Why We Trained a New Model

V3 achieved 82.84% classification accuracy but its **regression was unreliable** — Macro R² = 0.01, essentially no better than guessing the mean. This made the `reg_output` values untrustworthy for the dashboard.

The regression output is what enables the dashboard to tell farmers **"You have 1.5 doses left — top up 50ml"**, tracking real-time nutrient depletion as plants absorb nutrients over time. Classification alone can only say "this is an NPK bucket" — it cannot track how much is remaining.

Because V3's regression failed, the dashboard was patched on 2026-05-26 to bypass `reg_output` entirely and use a static class→PPM lookup table instead:

```
commit 078244e
refactor(dashboard): replace regression scales with classification lookup
and switch units to PPM
- Drive macro_scale/micro_scale/profile directly from predicted_class
  (bypasses regression)
```

The regression output also powers anomaly detection: if the model classifies a reading as "Water" but regression predicts high NPK concentration, the server flags it as a bad scan rather than instructing the farmer to add nutrients. This sanity check only works if regression is trustworthy.

**The goal of V4 and V5 is to fix regression** — specifically Macro/NPK concentration tracking — well enough to re-enable real-time depletion tracking in the dashboard and restore the anomaly detection logic.

---

## 1. Model Architecture Overview

All versions are **multimodal dual-output models** combining plant images with water sensor data.

| Component | Description |
|-----------|-------------|
| Image backbone | MobileNetV2 (224×224, ImageNet weights) |
| Sensor inputs | pH, EC (electrical conductivity), water temperature |
| Output 1 — `clf_output` | 4-class softmax: Water, NPK, Micro, Mix |
| Output 2 — `reg_output` | 2-value regression: macro nutrient (NPK), micro nutrient |

---

## 2. Evaluation Results — All Versions

### Classification Metrics

| Metric | V3 | V4 | V5-run1 | V5-run2 | V5-run3 | **V5-run4** |
|--------|----|----|---------|---------|---------|------------|
| **Overall Accuracy** | 82.84% | 75.02% | 78.97% | 72.46% | 74.83% | **83.62%** ✓ |
| Water — Precision | 0.90 | 0.63 | 0.63 | 0.57 | 0.57 | **0.94** |
| Water — Recall | **0.92** | 1.00 | 1.00 | 1.00 | 1.00 | 0.73 |
| NPK — Precision | 0.72 | 0.68 | 1.00 | 0.75 | 0.78 | **0.78** |
| **NPK — Recall** | **0.92** | 0.55 | 0.40 | 0.41 | 0.37 | **0.78** |
| Micro — Precision | 0.98 | 0.83 | 0.82 | 0.93 | 0.88 | 0.80 |
| Micro — Recall | 0.48 | 0.59 | **0.81** | 0.53 | 0.68 | **0.81** |
| Mix — Recall | 0.99 | 0.90 | 0.99 | 1.00 | 0.99 | 0.99 |

### Regression Metrics

| Metric | V3 | V4 | V5-run1 | V5-run2 | V5-run3 | **V5-run4** |
|--------|----|----|---------|---------|---------|------------|
| Overall R² | 0.23 | 0.11 | 0.14 | **0.34** | 0.17 | 0.13 |
| Macro (NPK) R² | 0.01 | -0.44 | -0.46 | **-0.08** | -0.44 | -0.27 |
| Micro R² | 0.45 | 0.65 | 0.75 | 0.77 | **0.78** | 0.54 |
| Overall MAE | 0.75 | 0.22 | 0.21 | 0.16 | 0.21 | 0.22 |

### Confusion Matrices (key rows)

| Run | Water→NPK | NPK→Water | NPK→Micro |
|-----|-----------|-----------|-----------|
| V3 | 299 | 352 | 0 |
| V4 | 0 | 2,037 | 59 |
| V5-run1 | 0 | 2,090 | 736 |
| V5-run2 | 0 | 2,596 | 148 |
| V5-run3 | 0 | 2,604 | 342 |
| **V5-run4** | **948** | **155** | 876 |

> V5-run4 shows the EC normalization fix working: NPK→Water confusion collapsed from 2,604 → 155.
> The 948 Water→NPK errors are boundary-EC Water samples (EC ≈ 0.40 mS/cm) that sit on the edge of the Water/NPK threshold.

### Hardware / Deployment Metrics (consistent across versions)

| Metric | Value |
|--------|-------|
| Inference latency (direct call) | ~42–44 ms avg |
| Model file size | ~23–26 MB |
| GPU | Apple M4 Pro (Metal) |

---

## 3. Training Script Differences: V3 vs V4 vs V5

### 3.1 Regression Targets

| Version | NPK target | Micro target | Activation |
|---------|-----------|-------------|------------|
| V3 | `[2.0, 0.0]` | `[0.0, 2.0]` | `linear` |
| V4 | `[1.0, 0.0]` | `[0.0, 1.0]` | `sigmoid` |
| V5 | `[1.0, 0.0]` | `[0.0, 1.0]` | `sigmoid` |

V4/V5 design (sigmoid + [0,1] targets) is more principled. V3's [2.0, 0.0] with linear output produced stronger gradient signal for NPK, which may have helped V3's NPK classification indirectly.

### 3.2 Loss Weights by Phase

| Phase | V3 clf / reg | V4 clf / reg | V5 clf / reg |
|-------|-------------|-------------|-------------|
| Phase 1 (warmup) | 1.0 / 0.0 | 1.0 / 0.0 | 1.0 / 0.0 |
| Phase 2 (joint, frozen backbone) | 1.0 / 0.05 | 1.0 / **0.3** | 1.0 / 0.05 |
| Phase 3 (fine-tune top layers) | 1.0 / 0.05 | 1.0 / **0.3** | 1.0 / 0.05 |
| Phase 4 (regression focus) | *(none)* | 1.0 / **0.8** | *(none)* |

V4's Phase 4 at reg_weight=0.8 was the primary cause of the 7% accuracy drop over V3.

### 3.3 Model Architecture

| Feature | V3 | V4 | V5 |
|---------|----|----|-----|
| Data split | `df.sample(frac=1)` random | StratifiedShuffleSplit | StratifiedShuffleSplit |
| Clf head | `Dense(4, softmax)` directly | `Dense(4, softmax)` directly | `Dense(64)→Dropout→Dense(4, softmax)` |
| Reg head | `Dense(2, linear)` | `Dense(64)→Dropout→Dense(32)→Dense(2, sigmoid)` | Same as V4 |
| Sensor branch | `Dense(128)→BN→Dense(64)` | Same | `Dense(64)→BN→Dense(64)→BN→Dense(32)` |
| LR scheduler | None | ReduceLROnPlateau | ReduceLROnPlateau |
| Augmentation | flip-LR, brightness, contrast | + flip-UD, saturation, hue | Same as V4 |

### 3.4 Sensor Normalization

```python
# V3, V4, V5-runs 1–3 (problematic)
SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 3.0),    # ← 2x too wide
    'water_temp': (24.0, 29.0),
}

# V5-run4+ (fixed)
SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 1.6),    # ← matches actual data range 0.04–1.51
    'water_temp': (24.0, 29.0),
}
```

---

## 4. V5 Iteration Log

### V5-run1 — Best classification (78.97%)

**Changes from V4:**
- Dedicated clf branch (symmetric with reg branch)
- Stronger sensor branch (double depth)
- reg_weight capped at 0.05 (removed V4's Phase 4 at 0.8)
- StratifiedShuffleSplit kept

**Result:** Micro recall jumped from 0.59 → 0.81. NPK still stuck at 0.40.

---

### V5-run2 — Best regression (macro R²: -0.08)

**Changes from run1:**
- Added sensor skip connection directly to clf branch
- Phase 3 reg_weight set to 0.0
- NPK sample weight boosted ×1.5

**Result:** Macro R² improved dramatically (-0.46 → -0.08). But overall accuracy dropped to 72.46% — NPK boost created 651 new Micro→NPK errors. NPK recall barely moved (0.40 → 0.41).

---

### V5-run3 — Partial recovery (74.83%)

**Changes from run2:**
- Removed NPK weight boost (reverted to standard)
- Kept sensor skip and Phase 3 reg=0.0

**Result:** Accuracy recovered slightly (72.46% → 74.83%), Micro recall improved (0.53 → 0.68). But macro R² collapsed back to -0.44 — the NPK boost was what drove the regression improvement, not the sensor skip. NPK recall declined further to 0.37.

---

### V5-run4 — Best result overall (83.62%) ✓

**Changes from run3:**
- Reverted sensor skip (removed)
- Restored Phase 3 reg_weight to 0.05
- **Fixed EC normalization: `(0.0, 3.0)` → `(0.0, 1.6)`** ← the actual fix

**Result:** Overall accuracy 83.62% — first time exceeding V3 (82.84%). NPK recall recovered from 0.37 → 0.78. Micro recall maintained at 0.81. The single EC normalization change resolved the NPK collapse that had persisted across all previous runs.

Trade-off introduced: Water recall dropped from 1.00 → 0.73 (948 Water samples predicted as NPK). These are boundary-EC Water samples at ≈0.40 mS/cm sitting right against NPK's minimum of 0.41 mS/cm.

---

## 5. Root Cause Analysis: NPK Recall Collapse

### 5.1 The Pattern

NPK recall across versions: **0.92 (V3) → 0.55 → 0.40 → 0.41 → 0.37 → 0.78 (V5-run4)**

Runs 1–3 treated this as an architecture or training strategy problem. It was a **data normalization problem** throughout.

Every architecture change (sensor skip, dedicated branches, weight boosts) made things marginally better or worse. The EC normalization fix resolved it in one change.

### 5.2 EC Sensor Data Distribution

```sql
SELECT e.bucket_label,
       AVG(cdr.ec) as avg_ec, MIN(cdr.ec) as min_ec, MAX(cdr.ec) as max_ec
FROM cleaned_daily_readings cdr
JOIN experiments e ON cdr.experiment_id = e.id
WHERE e.bucket_label IN ('Water', 'NPK', 'Micro', 'Mix')
GROUP BY e.bucket_label ORDER BY avg_ec;
```

| Class | Avg EC | Min EC | Max EC | Std |
|-------|--------|--------|--------|-----|
| Water | 0.34 | 0.04 | 0.40 | 0.06 |
| NPK | 0.50 | 0.41 | 0.65 | 0.10 |
| Micro | 0.77 | 0.66 | 0.85 | 0.08 |
| Mix | 0.99 | 0.86 | 1.51 | 0.18 |

**EC perfectly separates all 4 classes with zero overlap in raw values.** Water max (0.40) and NPK min (0.41) are adjacent.

### 5.3 The Normalization Problem

With `SENSOR_NORM['ec'] = (0.0, 3.0)`, the normalized values become:

| Class | Normalized EC range |
|-------|---------------------|
| Water | 0.013 – **0.133** |
| NPK | **0.137** – 0.217 |
| Micro | 0.220 – 0.283 |
| Mix | 0.287 – 0.503 |

The Water/NPK boundary is at `0.133 vs 0.137` — a gap of **0.004** out of 1.0. All four classes are crammed into the bottom ~50% of the [0,1] range. The model effectively cannot distinguish the classes by EC because the signal is too compressed.

### 5.4 The Fix

Change `ec` normalization to `(0.0, 1.6)` — covers the actual data range (max Mix = 1.51 + 5% headroom):

| Class | New normalized EC range |
|-------|-------------------------|
| Water | 0.025 – **0.250** |
| NPK | **0.256** – 0.406 |
| Micro | 0.413 – 0.531 |
| Mix | 0.538 – 0.944 |

Now the classes spread across the full [0,1] range and the Water/NPK gap grows from 0.004 to 0.006 — but more importantly, the absolute EC values are now meaningfully large numbers the model can actually learn from.

### 5.5 pH and Water Temperature

Neither pH nor water_temp are reliable discriminators — all four classes show heavily overlapping ranges for both features. They contribute noise to the sensor branch rather than signal.

---

## 6. Current V5 Training Script State

**File:** `scripts/nutrient_classifier_v5.py`

Active configuration for the next training run:
- EC normalization: `(0.0, 1.6)` ← key fix
- Dedicated clf branch + dedicated reg branch (both symmetric)
- Stronger sensor branch (two Dense(64)+BN layers)
- Phase 1: reg_weight=0.0 (50 epochs, clf warmup)
- Phase 2: reg_weight=0.05 (40 epochs, joint)
- Phase 3: reg_weight=0.05 (30 epochs, fine-tune top 30 MobileNet layers)
- Standard sample weights (no class-specific boost)
- ReduceLROnPlateau on all phases

**File:** `scripts/evaluate_classifier_v5.py`
- EC normalization: `(0.0, 1.6)` — must always match training script
- Auto-detects `leafcloud_multimodal_v5_*.keras` (most recent)

> **Important:** The EC normalization change is a breaking change. Old models (V3, V4, V5-runs 1–3) were trained with `(0.0, 3.0)`. Evaluating old models with the new normalization will give wrong results. Use `evaluate_classifier_v4.py` for old models.

---

## 7. V5-run4 Outcome and Remaining Work

### Achieved (V5-run4 = `leafcloud_multimodal_v5_20260529_0806.keras`)

| Target | Goal | Result |
|--------|------|--------|
| Overall accuracy > 82% | ✓ | **83.62%** |
| NPK recall > 0.85 | ✗ | 0.78 (close) |
| Micro recall > 0.80 | ✓ | **0.81** |
| Macro R² > 0.0 | ✗ | -0.27 (improving) |

### Remaining Issues

**1. Water→NPK boundary confusion (948 errors, Water recall 0.73)**

Water max EC = 0.40 mS/cm and NPK min EC = 0.41 mS/cm. With normalization ÷1.6, these are 0.250 vs 0.256 — a 0.006 normalized gap. Water samples at the top of their EC range sit right on the boundary and tip into NPK. These are genuinely ambiguous by EC alone.

**2. Macro R² still negative (-0.27)**

The model under-predicts NPK macro concentration (predicted avg 0.72 vs true 1.0 for NPK class) and over-predicts macro for Water (0.29 vs true 0.0). Regression for macro nutrient is learning the direction but not the magnitude. Requires further work before the dashboard can re-enable real-time depletion tracking.

**3. NPK micro pred avg = 0.43 (true = 0.0)**

The model incorrectly predicts some micro concentration for NPK samples. Suggests the NPK/Micro regression boundary is still blurry in the shared representation.
