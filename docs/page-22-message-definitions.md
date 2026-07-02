[Prev](./page-21-full-stack-ai-integration.md) | [Next](./page-23-sensor-calibration.md)

# Reference: **System Message Definitions**

This document tracks where different text messages, alerts, and dashboard labels are defined in the codebase.

## 1. Dashboard Advisory Messages
These are the primary status descriptions shown to the farmer in the "Advisory" card.
- **Location**: `app/api/v1/endpoints/iot.py`
- **Fields**: `advisory_sum`, `advisory_exp`, `advisory_act`

| Logic Condition | Summary |
| :--- | :--- |
| **Anomaly Detected** | "AI Sensor Anomaly Detected" |
| **Levels > 90%** | "Optimal Nutrient Balance" |
| **Levels < 70%** | "Nutrient Depletion Detected" |
| **Levels 70% - 90%** | "Moderate Concentration" |

## 2. Actionable Alert Message
This is the red/orange alert message that triggers top-up instructions.
- **Location**: `app/api/v1/endpoints/iot.py`
- **Key Line**: `message=f"Nutrient levels have dropped to {int(min(macro_scale, micro_scale)*100)}% of recommended dosage."`

## 3. Profile Detected Labels
The visual status of what is currently in the tank.
- **Location**: `app/api/v1/endpoints/iot.py`
- **Mapping**:
    - `Water` → "Water Only (No Nutrients)"
    - `NPK` → "Macro-Leaning Blend"
    - `Micro` → "Micro-Leaning Blend"
    - `Mix` → "Balanced Mix"

## 4. Background System Logs
Warnings printed to the server terminal during AI processing.
- **Location**: `app/services/ai_service.py`
- **Example**: `logger.warning(f"Anomaly Detected! AI sees 'Water' but regression predicted high nutrients...")`
