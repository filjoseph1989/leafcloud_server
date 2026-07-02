[Prev](./page-40-model-v6-evaluation-analysis.md) | [Next](./page-42-model-v8-evaluation-analysis.md)

# LeafCloud Nutrient Classifier — V7 Model Evaluation Analysis & V8 Upgrade Plan

**Date:** 2026-05-30  
**Author:** tin <toraquechristine6@gmail.com>  
**Status:** V7 Evaluated, V8 Design Approved  

---

## 1. V7 Model Evaluation Summary

We evaluated the `leafcloud_multimodal_v7_20260530_0911.keras` model on the stratified 20% validation subset containing **17,641 samples**.

### Classification Metrics
- **Overall Accuracy**: **72.73%** (dropped from V6's 79.29% and V5-run4's 83.62%)
- **NPK Recall**: **0.37** (severe collapse)
- **Confusion Matrix Highlights**:
  - **2,563 NPK samples** were misclassified as **Water** (more than 54% of NPK samples).
  - **1,379 Micro samples** were misclassified as **Mix**.

### Regression Metrics
- **Overall $R^2$ Score**: **-0.6563**
- **Macro (NPK) $R^2$ Score**: **-0.6814** (completely collapsed)
- **Micro $R^2$ Score**: **-0.6312** (completely collapsed)

### Per-Class Regression Predictions

| Class | Macro Pred Avg | Micro Pred Avg | True Macro Avg | True Micro Avg |
|---|---|---|---|---|
| **Water** | **0.0000** | **0.0000** | 0.0000 | 0.0000 |
| **NPK** | **0.0000** | **0.0957** | 0.5509 | 0.0000 |
| **Micro** | **0.0000** | **0.8247** | 0.0000 | 0.5715 |
| **Mix** | **0.0000** | **1.0000** | 0.5165 | 0.5165 |

* **Observation**: The Macro output is exactly `0.0000` across the entire validation dataset (`min: 0.0000, max: 0.0000`), while the Micro output behaves in a highly binary fashion (`0.0` or `1.0`).

---

## 2. Root Cause Analysis

We identified two major issues causing this performance degradation in V7:

### Issue A: Regression Gradient Corruption (Backprop Leak)
By directly feeding `clf_output` into `reg_input = Concatenate()([merged, clf_output])`, the regression loss backpropagated through the classification softmax layer.
* **The Conflict**: During depletion, NPK targets drop toward `0.0`. The regression branch realized that the easiest way to minimize regression loss for depleted NPK samples was to force the classification branch to predict `Water` (which outputs `[0.0, 0.0]`).
* **The Result**: The regression loss actively corrupted the classification branch, forcing it to misclassify NPK as Water, causing classification accuracy to collapse to `72.73%`.

### Issue B: Monolithic Scale Mismatch & Early Stopping
* **Scale Mismatch**: `merged` is an unbounded ReLU-activated feature map (outputs from 0 to 10+), whereas `clf_output` is a strictly bounded Softmax probability vector `[0, 1]`. Without normalization, the regression branch was dominated by `merged`, making it ignore classification signals.
* **Early Stopping**: The shared `early_stop_clf` callback monitored `val_clf_output_accuracy`. Because classification warmed up first in Phase 1 and was already at its peak, Phase 2 (joint training) stopped after only 10 epochs. 10 epochs is not enough time for the regression branch to learn.

---

## 3. V8 Training Upgrade Plan

We are implementing **V8** with the following upgrades:

1. **Gradient Blocking (`tf.stop_gradient`)**:
   We will pass `clf_output` through a gradient-stop layer before concatenating it with the regression inputs:
   ```python
   clf_output_stopped = Lambda(lambda x: tf.stop_gradient(x))(clf_output)
   reg_input = Concatenate()([merged_normalized, clf_output_stopped])
   ```
   This allows the regression branch to use classification predictions as features, but prevents the regression loss from updating or corrupting the classification weights.

2. **Feature Scale Normalization**:
   Apply `BatchNormalization` to the `merged` fusion layer before concatenating it with the stopped classification outputs. This normalizes the feature scales to have zero mean and unit variance, matching the scale of the `[0, 1]` softmax outputs.

3. **Separate Early Stopping Callbacks**:
   - Phase 1 (warmup): Use `early_stop_clf` monitoring `val_clf_output_accuracy`.
   - Phase 2 & 3 (joint training): Use `early_stop_joint` monitoring `val_loss` (joint MSE + crossentropy) with higher patience (15 epochs) to allow the regression branch to fully converge.
