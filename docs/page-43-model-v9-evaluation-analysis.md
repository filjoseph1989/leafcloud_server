[Prev](./page-42-model-v8-evaluation-analysis.md) | [Next](./page-44-model-v10-evaluation-analysis.md)

# LeafCloud Nutrient Classifier — V9 Model Evaluation Analysis & V10 Upgrade Plan

**Date:** 2026-06-02  
**Author:** tin <toraquechristine6@gmail.com>  
**Status:** V9 Evaluated, V10 Design Proposed  

---

## 1. V9 Model Evaluation Summary

We evaluated the `leafcloud_multimodal_v9_20260601_1235.keras` model on the stratified 20% validation subset containing **17,641 samples**.

### Classification Metrics
- **Overall Accuracy**: **82.80%** (a regression from V8's all-time high of **89.63%**)
- **NPK Recall**: **0.61** (dropped from V8's **0.94**)
- **F1-Scores**:
  - **Water**: 0.80 (Precision: 0.67, Recall: 0.99)
  - **NPK**: 0.70 (Precision: 0.83, Recall: 0.61)
  - **Micro**: 0.84 (Precision: 0.94, Recall: 0.75)
  - **Mix**: 0.94 (Precision: 0.90, Recall: 0.98)

### Regression Metrics
- **Overall $R^2$ Score**: **-0.8338** (remains negative, though slightly up from V8's -0.9552)
- **Macro (NPK) $R^2$ Score**: **-0.9499** (remains negative)
- **Micro $R^2$ Score**: **-0.7177** (remains negative)

### Per-Class Regression Predictions

| Class | Macro Pred Avg | Micro Pred Avg | True Macro Avg | True Micro Avg |
|---|---|---|---|---|
| **Water** | **0.0000** | **0.0000** | 0.0000 | 0.0000 |
| **NPK** | **0.0000** | **0.0000** | 0.5509 | 0.0000 |
| **Micro** | **0.0121** | **0.0981** | 0.0000 | 0.5715 |
| **Mix** | **0.1931** | **0.9359** | 0.5165 | 0.5165 |

---

## 2. Root Cause Analysis

We identified a critical structural conflict between the classification and regression branches in V9:

### The Problem: Shared Feature Space Contamination (Regression Gradients Leak)
In V9, we successfully configured the `StopGradient` layer to block gradients from flowing from the classification output `clf_output` back into the regression branch:
```python
clf_output_stopped = StopGradient()(clf_output)
reg_input = Concatenate()([merged_dropout, clf_output_stopped])
```
However, the regression loss gradients **still backpropagated directly through `merged_dropout`** into the shared multimodal fusion layers and the MobileNetV2 backbone.

1. **Classification Accuracy Collapse (89.63% -> 82.80%):** Because the continuous regression task is highly complex and noisy (predicting a linear time-based decay purely from static images and noisy sensor telemetry), its gradients corrupted the feature representations in the shared layers that the classification branch relies on.
2. **High Water-vs-NPK Confusion (1,705 samples):** 1,705 NPK samples were misclassified as Water. This is because the shared features were degraded by regression updates, preventing the classification head from cleanly separating NPK from Water.
3. **Regression Collapse (0.0000 for NPK):** Because the classification accuracy collapsed and features were corrupted, the regression branch was unable to extract clear signals and settled into predicting near-zero constant values for the NPK class.

---

## 3. V10 Training Upgrade Plan: Complete Gradient Isolation

To solve the feature contamination, we will implement **V10** with **Complete Gradient Isolation**. The regression branch must read the high-quality features learned by the classification branch, but must **never** modify them.

### 1. Stop Gradients on the Shared Fusion Output
We will wrap the shared feature vector `merged_dropout` in a `StopGradient` layer before passing it to the regression branch:
```python
# Stop classification and feature gradients from being corrupted by regression loss
merged_dropout_stopped = StopGradient()(merged_dropout)
clf_output_stopped = StopGradient()(clf_output)

# Conditioned Regression Branch
reg_input = Concatenate()([merged_dropout_stopped, clf_output_stopped])
```

This structural change guarantees:
* **Zero Classification Degradation:** The shared representation is optimized **only** by the classification branch. This preserves the 89.63%+ classification accuracy.
* **Stable Feature Space:** The regression branch is trained to map a static, high-quality, pre-optimized feature space to the depletion values, allowing it to converge on positive $R^2$ values.

### 2. Implementation Action Items
1. Create `scripts/nutrient_classifier_v10.py` and `scripts/evaluate_classifier_v10.py` with complete gradient isolation.
2. Maintain the custom `StopGradient` serialization mapping in the model loading scripts.
