[Prev](./page-15-iot-pi-integration.md) | [Next](./page-17-static-image-serving.md)

# Monitoring Dashboard: **Farmer's Interface**

This guide explains how the mobile app retrieves the real-time monitoring data for the farmer's dashboard.

## 1. Dashboard Endpoint
**URL**: `http://<server-ip>:8000/api/v1/iot/dashboard/{tank_id}`
**Method**: `GET`

---

## 2. Full Sample Response
```json
{
  "tank_id": 1,
  "tank_name": "Reservoir",
  "last_updated": "2026-05-18T14:30:22",
  "image_url": "http://192.168.1.20:8000/images/2026-05-18/Reservoir/reading_20260518_143022_a3f9c1.jpg",
  "health_status": "HEALTHY",
  "profile_detected": "Balanced",
  "telemetry": {
    "ph": 6.2,
    "ec": 1.4,
    "water_temp": 26.5,
    "status": "Safe Range"
  },
  "estimated_nutrients": {
    "n_grams": 4.32,
    "p_grams": 1.78,
    "k_grams": 3.10,
    "total_estimated_grams": 9.20,
    "unit": "grams"
  },
  "advisory": {
    "summary": "Optimal Nutrient Balance",
    "explanation": "Your Reservoir has a stable concentration of approximately 9.2g of total NPK.",
    "farmer_action": "No immediate action required. Maintain current environmental conditions."
  },
  "alert": null
}
```

---

## 3. Response Fields

### A. Raw Sensor Telemetry
Direct readings from the Raspberry Pi sensors.
*   `ph`, `ec`, `water_temp`, `status`

### B. Estimated Nutrient Content (Physical Grams)
The backend multiplies the AI's **Scaling Index** against the **Tank Configuration** (Volume and NPK %).
*   `n_grams`, `p_grams`, `k_grams`, `total_estimated_grams`

### C. Visual Diagnostics
*   `image_url`: Full HTTP URL to the latest plant image. Load directly as an `<img>` src in the mobile app.
    - Format: `http://<server-ip>:8000/images/<date>/<tank_name>/<filename>.jpg`
*   `health_status`: `HEALTHY` or `NUTRIENT DEFICIENT`
*   `profile_detected`: `Balanced`, `Macro-Leaning Blend`, or `Micro-Leaning Blend`

### D. Actionable Alerts
Only present when nutrient levels drop below 70%. `null` otherwise.
```json
"alert": {
  "level": "WARNING",
  "message": "Nutrient levels have dropped to 45% of recommended dosage.",
  "action_required": true,
  "topup_macro_ml": 3.0,
  "topup_micro_ml": 3.0
}
```

---

## 4. How the Math Works
The backend performs the following calculation on-the-fly:
1.  **AI Output**: Gets `macro_scale` (e.g., 0.5) and `micro_scale` from the latest `npk_predictions` row.
2.  **Config**: Gets `target_macro_dosage_mll` (e.g., 2.0 mL/L) and `water_volume_liters` (e.g., 6.0 L) from `tank_configs`.
3.  **Physical Amount**:
    - `Grams = (Scale * Dosage * Volume * Density) * (NPK % / 100)`
    - `Top-up mL = (1.0 - Scale) * Dosage * Volume`

---

## 5. Mobile Implementation Example
```javascript
const refreshDashboard = async (tankId) => {
  const response = await fetch(`http://192.168.1.20:8000/api/v1/iot/dashboard/${tankId}`);
  const data = await response.json();

  // Use image_url directly as an image source
  document.getElementById('plant-image').src = data.image_url;

  updateUI(data);
};
```

