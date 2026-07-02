[Prev](./page-29-dashboard-code-explanation.md) | [Next](./page-31-database-schema.md)

# AI Model Evaluation: **V3 vs V4 Performance Analysis**

This document provides a detailed breakdown of the **V3 Model (82.84% accuracy)** classification and regression performance, followed by a comparative analysis of what changed in **V4** and why it resulted in lower overall performance.

---

## 📊 V3 Model Performance Breakdown

### 1. Classification Metrics (82.84% Total Accuracy)

| Class | Precision | Recall | Key Issues / Performance Notes |
| :--- | :---: | :---: | :--- |
| **Water** | `0.90` | `0.92` | **Strong** on both precision and recall. |
| **NPK** | `0.72` | `0.92` | Good recall, but suffers from some false positives. |
| **Micro** | `0.98` | `0.48` | **Worst performing class**. Misses half of the Micro readings, mostly misclassifying them as NPK (1,348 wrong predictions). |
| **Mix** | `0.83` | `0.99` | **Nearly perfect recall**. |

> [!WARNING]
> **Micro Class Bottleneck:** While the precision for `Micro` is high (when it predicts Micro, it is almost always right), the model is under-sensitive (recall of `0.48`) and frequently defaults to predicting `NPK` instead.

### 2. Regression Metrics
Regression performance in V3 remains poor overall:
*   **Macro $R^2$**: `0.01` (barely better than guessing the mean)
*   **Micro $R^2$**: `0.45`

---

## 🔄 V3 vs V4 Comparison: Why V4 Performance Dropped

V4 attempted to resolve the regression issues by changing several hyperparameters and model logic, but these changes unfortunately degraded classification accuracy to **75%** and worsened Macro regression metrics.

### 1. Regression Loss Weights (The Main Culprit)

V4 significantly increased the regression loss weight across training phases, introducing a new regression-heavy Phase 4:

| Phase | V3 Reg. Weight | V4 Reg. Weight | Impact & Notes |
| :--- | :---: | :---: | :--- |
| **Phase 1** | `0.0` | `0.0` | Shared base pre-training. |
| **Phase 2** | `0.05` | `0.3` | Increased regression focus in V4. |
| **Phase 3** | `0.05` | `0.3` | Increased regression focus in V4. |
| **Phase 4** | *(None)* | `0.8` | **New phase** introduced to prioritize regression. |

> [!CAUTION]
> **Shared Representation Corruption:** Pushing the regression loss weight to `0.8` in Phase 4 heavily pulled the shared features toward regression optimization. The model sacrificed critical classification signals.
> Despite this, V4's Macro regression ended up at **$R^2 = -0.44$** (worse than V3's `0.01`), meaning the change corrupted classification accuracy without fixing regression.

---

### 2. Regression Head Architecture

*   **V3 Model**:
    ```
    Dense(2, activation='linear')
    ```
    *A single direct layer outputting unbounded continuous values.*
*   **V4 Model**:
    ```
    Dense(64) ──> Dropout ──> Dense(32) ──> Dense(2, activation='sigmoid')
    ```
    *A dedicated, deeper neural branch bounded to the range $[0, 1]$.*

While using a sigmoid activation and a dedicated deep branch is theoretically more robust, the heavy Phase 4 regression loss weight disrupted the shared features before this deeper regression branch could generalize properly.

---

### 3. Concentration Target Scaling

*   **V3 Model**: Scales targets to `[2.0, 0.0]`, `[0.0, 2.0]`, etc. ($0-2$ scale) using a linear activation.
*   **V4 Model**: Normalizes targets to `[1.0, 0.0]`, `[0.0, 1.0]`, etc. ($0-1$ scale) using a sigmoid activation.

The V4 scaling design is more principled, but it failed to yield benefits due to the shared feature corruption caused by the high loss weight.

---

### 4. Data Splitting Methodology

*   **V3 Model**: `df.sample(frac=1).iloc[:split]` (Plain random shuffle; no guarantee of class balance in validation set).
*   **V4 Model**: `StratifiedShuffleSplit` (Guarantees proportional class distributions in the validation set).

The V4 split is strictly better. However, it also means validation sets differed slightly between V3 and V4 evaluations, altering the random composition of evaluation data.

---

### 5. More Aggressive Data Augmentation

V4 added **vertical flip, saturation, and hue** augmentations on top of V3's baseline (horizontal flip, brightness, and contrast).
*   *Effect:* While more aggressive augmentation can improve long-term generalization, it can also slow down initial model convergence if it does not train on enough clean baseline examples first.

---

### 6. Reduce Learning Rate on Plateau (`ReduceLROnPlateau`)

V4 added a learning rate scheduler to Phases 2–4.
*   *Effect:* While generally a best practice, if the high regression loss weight (`0.8`) in Phase 4 caused the validation loss to drop for the wrong reasons (i.e. over-fitting regression while ignoring classification), the scheduler locked the model into a sub-optimal classification state.

---

## 🎯 Summary of Root Causes

> [!IMPORTANT]
> **Why V4 Failed:**
> 1. **Representation Drift:** The high regression loss weight in Phase 4 (`0.8`) corrupted the shared feature representation that both the classification and regression heads depend on.
> 2. **Result:** Classification dropped from **82.8%** to **75%**, while Macro regression worsened from an $R^2$ of `0.01` to `-0.44`.
> 3. **V3's Success:** V3's conservative regression weight (`0.05`) prevented regression training from interfering with classification, allowing the model to perform much better overall.