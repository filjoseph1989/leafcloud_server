[Prev](./page-19-alert-polling.md) | [Next](./page-21-full-stack-ai-integration.md)

# AI Model: **Multi-Task Nutrient Estimation**

This document explains the architecture and logic of the Multi-Task AI model implemented in `scripts/nutrient_classifier_v2.py`.

## 1. Overview
The Multi-Task model is designed to perform two simultaneous predictions from a single input (Crop Image + Sensor Data):
1.  **Classification**: Identifies the *type* of nutrient solution (Water, NPK/Macro, Micro, or Mix).
2.  **Regression**: Estimates the *concentration* of **Macro** (NPK) and **Micro** nutrients remaining in the tank.

## 2. Architecture
The model uses a **Sensor-Boosted Multi-Modal** architecture:

-   **Image Branch**: Uses `MobileNetV2` (pre-trained on ImageNet) to extract features from 224x224 crop images.
-   **Sensor Branch**: A small MLP that processes normalized `pH`, `EC`, and `Water Temperature`.
-   **Fusion Layer**: Concatenates features from both branches into a shared feature vector.
-   **Output Heads**:
    -   `clf_output`: Softmax activation (4 units) for category prediction.
    -   `reg_output`: Linear activation (2 units) for `[Macro, Micro]` scale estimation.

## 3. Data Mapping (Regression)
The regression head predicts values on a scale where **2.0** represents the 100% target dosage defined in the experiment.

| Label | Classification Index | Macro Scale | Micro Scale |
| :--- | :--- | :--- | :--- |
| **Water** | 0 | 0.0 | 0.0 |
| **NPK (Macro)** | 1 | 2.0 | 0.0 |
| **Micro** | 2 | 0.0 | 2.0 |
| **Mix** | 3 | 2.0 | 2.0 |

*Note: As plants consume nutrients (lettuce intake), the model is expected to predict values decreasing from 2.0 towards 0.0.*

## 4. Training Process
The script `scripts/nutrient_classifier_v2.py` follows a two-phase training strategy:

### Phase 1: Custom Head Training
-   Freezes the `MobileNetV2` base.
-   Trains only the fusion and output layers.
-   Learning Rate: `5e-4`.
-   Loss Weights: `1.0` (Clf), `0.5` (Reg).

### Phase 2: Fine-Tuning
-   Unfreezes the top 30 layers of `MobileNetV2`.
-   Trains the entire stack with a very low learning rate (`1e-5`).
-   Optimizer: `Adam`.

## 5. Implementation in API
The results from this model are stored in the `npk_predictions` table. The `reg_output` values (Macro/Micro scales) are used by the `/dashboard` API to calculate the exact grams of nutrients remaining and generate "Nutrient Depletion" alerts.

## 6. Verification
To check the distribution of target values in your current dataset:
```bash
# This logic is handled internally in get_dataset() in the script
python3 scripts/nutrient_classifier_v2.py
```

Based on the scripts/nutrient_classifier_v2.py file, the reason the output includes macro_val and micro_val is because this new version of the script uses Multi-Task Learning.

Instead of just predicting a category, the AI is now being trained to do two tasks at the same time:

Classification (clf_output): Guessing the correct category label (e.g., 'Water', 'NPK', 'Micro', 'Mix').
Regression (reg_output): Guessing the exact continuous numerical values (concentrations) of the nutrients.
What are macro_val and micro_val?
They represent the actual target concentrations for Macro (NPK) and Micro nutrients. According to this mapping in the code:

python
# Mapping for Regression: [Macro (NPK), Micro]
# 2.0 represents target concentration (100% dosage)
CONCENTRATION_MAP = {
    'Water': [0.0, 0.0],
    'NPK':   [2.0, 0.0],
    'Micro': [0.0, 2.0],
    'Mix':   [2.0, 2.0],
}
If a plant is in the 'NPK' bucket, the AI is trained to output [2.0, 0.0], meaning it should detect a 100% dosage of Macro nutrients and a 0% dosage of Micro nutrients.

Why is this necessary or better?
More Precision: In the real world, nutrient levels aren't just "all or nothing" categories. A tank might have half the required NPK (which would be a 1.0 value). Training a regression head allows the AI to eventually predict partial dosages and specific amounts, rather than just simple labels.
Better Learning (Regularization): By forcing the AI's "brain" to understand the actual numerical quantities of the nutrients alongside the categorical labels, it learns deeper, more accurate patterns from the images and sensors.
In short, macro_val and micro_val are the numeric targets teaching the AI how to measure the exact amount of nutrients, while the classification targets teach it how to name the overall state.

That is a great question! The short answer is: No, the model's output is not restricted to just exactly 0.0 or 2.0. It will absolutely output intermediate decimal values like 1.5, 1.4, 0.8, etc.

Here is why:

1. CONCENTRATION_MAP is only for the "Ideal Targets" (Training)
The map you see in the code is used strictly for training. It provides the "ground truth" or perfect answer. When you take a picture of a freshly mixed "NPK" bucket, you are telling the AI: "For this specific image, the perfect answer I want you to learn is 2.0."

2. The AI's Output is Continuous (Regression)
Because the second task is a Regression task, the AI uses a specific type of layer at the end of its network:

python
reg_output = Dense(2, activation='linear', name='reg_output')(merged)
The activation='linear' part means the AI is free to guess any number on a continuous scale.

3. How it Behaves in the Real World
When you deploy this model to monitor a real tank, here is what will happen over time:

Day 1: You fill the tank with a fresh 100% NPK mix. The AI looks at the sensor data and the healthy plant and predicts 1.98 (very close to the 2.0 target).
Day 7: The plants have consumed some of the nutrients. The AI notices slight changes in the water chemistry (sensors) and the plant's visual health. It predicts 1.45 (meaning the nutrients are depleting).
Day 14: The tank is running very low on nutrients. The AI predicts 0.60. This is the exact moment your server can send an alert to the mobile app saying, "Nutrients are low, please top up!"
If the model could only output exactly 0.0 or 2.0, there would be no reason to use regression at all—that would just be standard classification. The entire purpose of adding that regression head is to allow the AI to guess those "in-between" values like 1.5 so you can track how fast the plants are eating the nutrients!

That is an excellent question! If the ultimate goal is just to get the exact numerical values (Regression), why do we still keep the Classification part?

In modern machine learning, combining both is a technique called Multi-Task Learning (MTL). We keep the classification head alongside the regression head for three very important reasons:

1. It Makes the AI's "Brain" Smarter (Shared Learning)
When the AI looks at a leaf, it has to extract visual features (colors, shapes, spots) using the MobileNetV2 base.

If you only ask it to predict a number (Regression), the AI might struggle to figure out exactly what to look for.
By forcing it to also guess the category (Classification: "Is this Water, NPK, Micro, or a Mix?"), you are forcing the AI to learn very distinct, high-quality visual patterns.
Once the AI learns the fundamental difference between an "NPK" leaf and a "Micro" leaf (Classification), it becomes much easier for it to accurately estimate the exact concentration (Regression). The classification task acts as an "anchor" or "guide" that helps the regression task perform better.

2. Dashboard Visibility (What vs. How Much)
Your application (the Farmer's Dashboard) actually needs both pieces of information to give a complete report to the user:

Classification answers "What is it?": It powers dashboard features like profile_detected (e.g., telling the farmer "This tank currently has a Micro-Leaning Blend").
Regression answers "How much is there?": It powers the actual math for the topup_macro_ml and the remaining physical grams of nutrients.
3. Sanity Checking and Anomaly Detection
Having both outputs gives your backend server a way to double-check the AI's logic. Imagine a scenario where the AI is confused by a weird image:

Classification Output: Water (99% confidence)
Regression Output: Macro 1.85, Micro 1.90
Because the classification says "Water" but the regression says the tank is almost completely full of nutrients, your backend logic can flag this as an anomaly or a low-confidence reading and ignore it, rather than blindly triggering a false alert to the farmer.

In summary, the Classification head teaches the model context (what it is looking at), which allows the Regression head to be highly accurate with its numbers (how much is there).


