[Prev](./page-38-model-classification-vs-estimation.md) | [Next](./page-41-model-v7-evaluation-analysis.md)

# LeafCloud Nutrient Classifier — V6 Model Evaluation Analysis & V7 Upgrade Plan

**Date:** 2026-05-30  
**Author:** tin <toraquechristine6@gmail.com>  
**Status:** Evaluation Completed, V7 Design Approved  

---

## 1. V6 Model Evaluation Summary

We evaluated the `leafcloud_multimodal_v6_20260529_2001.keras` model on a stratified 20% validation subset containing **17,641 samples**.

### Classification Metrics
- **Overall Accuracy**: **79.29%** (down from V5-run4's 83.62%)
- **NPK Recall**: **0.57** (collapsed from 0.78 in V5-run4)
- **Confusion Matrix Highlights**:
  - **1,861 NPK samples** were misclassified as **Water**.
  - **1,018 Micro samples** were misclassified as **Mix**.

### Regression Metrics
- **Overall $R^2$ Score**: **0.1126**
- **Macro (NPK) $R^2$ Score**: **-0.4911** (Highly negative, worse than mean guess)
- **Micro $R^2$ Score**: **0.7164** (Strong tracking)

---

## 2. Root Cause Analysis

We identified two major issues that caused the V6 regression branch to fail on NPK/Macro prediction and degraded classification performance.

### Issue A: The EC Monotonic Mapping Trap
Because the regression loss weight was very low (`reg_weight=0.05`) compared to classification (`1.0`), the shared layers were optimized purely for classification. The regression head learned to predict both Macro and Micro concentrations as a simple monotonic function of the raw EC value:

| Class | Average EC (mS/cm) | Macro Pred Avg | Micro Pred Avg | True Macro Avg | True Micro Avg |
|---|---|---|---|---|---|
| **Water** | 0.34 | **0.0000** | **0.0000** | 0.0000 | 0.0000 |
| **NPK** | 0.50 | **0.0335** | **0.0563** | 0.8850 | 0.0000 |
| **Micro** | 0.76 | **0.5281** | **0.7723** | 0.0000 | 1.0000 |
| **Mix** | 0.99 | **0.9933** | **1.0000** | 1.0000 | 1.0000 |

* **The Problem**: Since the regression branch has no way of knowing which class is present (it is parallel to the classification branch), it mapped lower EC (NPK range) to near-zero values, and higher EC (Micro range) to high values for *both* branches. This is why Micro's Macro prediction is `0.5281` (should be `0.0`) and NPK's Macro prediction is `0.0335` (should be `0.8850`).

### Issue B: The Experiment EC Paradox
Our analysis of the database readings over the 19 days of the experiment revealed that **EC increases over time** in all active buckets:
* **NPK (Exp 1)**: `0.41` $\rightarrow$ `0.65` mS/cm
* **Micro (Exp 2)**: `0.66` $\rightarrow$ `0.85` mS/cm
* **Mix (Exp 3)**: `0.86` $\rightarrow$ `1.01` mS/cm

As plants transpire water, the remaining solution becomes more concentrated, driving the physical EC reading up.
* **The Target Failure**: The V6 target formula was:
  $$\text{Target} = \frac{\text{Current EC} - \text{Water Base EC}}{\text{Initial EC} - \text{Water Base EC}}$$
  Since `current_ec` is almost always greater than `initial_ec`, the ratio is $\ge 1.0$ and is clipped. Consequently, the continuous regression targets collapsed back to static `1.0` values for the entire duration of the experiments, rendering the continuous learning objective useless.

---

## 3. V7 Training Upgrade Plan

To resolve both issues and establish stable classification and regression performance, we are implementing **V7** with the following upgrades:

### 1. Time-Based Depletion Targets
Since the experiments started at full strength (day 1) and ended at full depletion (day 19), we define the depletion ratio based on time elapsed:
$$\text{elapsed\_seconds} = \text{timestamp} - \text{start\_timestamp}$$
$$\text{time\_ratio} = \frac{\text{elapsed\_seconds}}{\text{total\_experiment\_duration\_seconds}}$$
$$\text{depletion\_ratio} = 1.0 - \text{time\_ratio}$$
This provides a smooth, continuous target gradient spanning `[0.0, 1.0]` that matches the physical progress of plant nutrient absorption.

### 2. Classification-Conditioned Regression
We will feed the classification predictions (softmax output layer) directly into the regression branch inputs. 
```
Merged Features (Image + Sensor) ───► Clf Branch ───► Softmax [4] ──┐
                  │                                                 ▼
                  └──────────────────────────────────────────► Concatenate [Merged + Softmax]
                                                                    │
                                                                    ▼
                                                               Reg Branch [2]
```
This forces the regression branch to route its predictions based on the predicted class: if classification predicts NPK, the regression branch can easily scale Macro output while setting Micro to exactly zero.

### 3. Elevated Regression Loss Weight
We will bump the Phase 2 & 3 regression loss weight from `0.05` to `0.20` to prevent the model from ignoring the regression task in favor of classification.
