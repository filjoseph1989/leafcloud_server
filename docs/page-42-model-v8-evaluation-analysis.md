[Prev](./page-41-model-v7-evaluation-analysis.md) | [Next](./page-43-model-v9-evaluation-analysis.md)

# LeafCloud Nutrient Classifier — V8 Model Evaluation Analysis & V9 Upgrade Plan

**Date:** 2026-06-01  
**Author:** tin <toraquechristine6@gmail.com>  
**Status:** V8 Evaluated, V9 Design Approved  

---

## 1. V8 Model Evaluation Summary

We evaluated the `leafcloud_multimodal_v8_20260531_1025.keras` model on the stratified 20% validation subset containing **17,641 samples**.

### Classification Metrics
- **Overall Accuracy**: **89.63%** (the highest ever recorded on this dataset, up from V7's 72.73% and V5-run4's 83.62%)
- **NPK Recall**: **0.94** (recovered from 0.37 in V7)
- **F1-Scores**:
  - **Water**: 0.93
  - **NPK**: 0.88
  - **Micro**: 0.84
  - **Mix**: 0.94

### Regression Metrics
- **Overall $R^2$ Score**: **-0.9552**
- **Macro (NPK) $R^2$ Score**: **-0.9918** (collapsed)
- **Micro $R^2$ Score**: **-0.9186** (collapsed)

### Per-Class Regression Predictions

| Class | Macro Pred Avg | Micro Pred Avg | True Macro Avg | True Micro Avg |
|---|---|---|---|---|
| **Water** | **0.0000** | **0.0000** | 0.0000 | 0.0000 |
| **NPK** | **0.0000** | **0.0000** | 0.5509 | 0.0000 |
| **Micro** | **0.0000** | **0.0194** | 0.0000 | 0.5715 |
| **Mix** | **0.2555** | **0.7646** | 0.5165 | 0.5165 |

---

## 2. Root Cause Analysis

We identified a major success and a critical early-stopping bug:

### The Success: Gradient Blocking Layer (`tf.stop_gradient`)
By introducing the custom registered `StopGradient` layer, we successfully blocked the regression gradients from backpropagating into and corrupting the classification weights. 
- The classification accuracy reached an all-time high of **89.63%**.
- The NPK-to-Water confusion collapsed to just 155 samples.

### The Problem: The Joint-Loss Early Stopping Bug
In Phase 2 and Phase 3, the training script compiled the model with early stopping configured to monitor the joint validation loss (`val_loss` = classification loss + $0.2 \times$ regression loss).
- **The Issue**: Classification loss starts very low after Phase 1 warm-up. As joint training began, any tiny fluctuation in classification loss outweighed the improvements in regression loss.
- **The Result**: The lowest joint validation loss occurred at **Epoch 1** of Phase 2. The `EarlyStopping` callback triggered and **restored the weights of Epoch 1**. Consequently, the regression branch was only trained for a single epoch and remained in an un-converged state (hence predicting exactly `0.0000` for Macro).

---

## 3. V9 Training Upgrade Plan

To allow the regression branch to fully train while keeping classification accuracy high, we are implementing **V9** with the following upgrades:

1. **Monitor Regression MAE for Early Stopping**:
   - In Phase 2 & 3, configure early stopping to monitor **`val_reg_output_mae`** (or `val_reg_output_loss`) instead of `val_loss`.
   - This ensures the training continues until the regression head fully converges, while keeping classification accuracy high since gradients are blocked by `tf.stop_gradient`.

2. **Verify custom model loading in API service**:
   - Register the `StopGradient` custom object inside `app/services/ai_service.py` to prevent background task inference deserialization crashes.
