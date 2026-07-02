[Prev](./page-28-upload-interval-configuration.md) | [Next](./page-30-evaluation.md)

Here is the line-by-line explanation of the code inside the `@router.get("/dashboard/{tank_id}", response_model=DashboardResponse)` endpoint.

### 1. Function Definition and Initial Database Queries

```python
@router.get("/dashboard/{tank_id}", response_model=DashboardResponse)
def get_tank_dashboard(tank_id: int, request: Request, db: Session = Depends(get_db)):

```

* Defines a GET endpoint at the URL path `/dashboard/{tank_id}`.
* Specifies that the returned data will automatically be validated against the `DashboardResponse` Pydantic model.
* Accepts `tank_id` from the URL path, the incoming HTTP `request` object (used later to build full image URLs), and injects the database session dependency (`db`).

```python
    # 1. Fetch Config
    tank = db.query(TankConfig).filter(TankConfig.id == tank_id).first()
    if not tank:
        raise HTTPException(status_code=404, detail="Tank configuration not found")

```

* Queries the `TankConfig` table to find the specific tank configuration matching the provided `tank_id`.
* If no matching tank configuration is found, it immediately halts execution and returns an HTTP 404 error back to the user.

```python
    # 2. Fetch Latest Reading
    latest_reading = db.query(DailyReading).filter(
        DailyReading.tank_id == tank_id
    ).order_by(DailyReading.timestamp.desc()).first()

    if not latest_reading:
        raise HTTPException(status_code=404, detail="No readings found for this tank")

```

* Queries the `DailyReading` table to get the historical data points for this specific tank.
* Orders the results by the `timestamp` field in descending order (`.desc()`) and grabs the `.first()` record, which effectively targets the newest sensor reading available.
* If the tank has zero recorded readings, it returns an HTTP 404 error.

```python
    # 3. Fetch AI Prediction for that reading
    prediction = db.query(NPKPrediction).filter(
        NPKPrediction.daily_reading_id == latest_reading.id
    ).first()

    predicted_class = prediction.predicted_class if prediction and prediction.predicted_class else "Unknown"

```

* Queries the `NPKPrediction` table to find the machine learning classification associated with the `latest_reading.id` obtained in the previous step.
* Saves the string value of the prediction class (e.g., "Mix", "Water") to `predicted_class`. If no entry exists or the field is blank, it defaults the string to `"Unknown"`.

---

### 2. Classification Mapping Logic

```python
    # IMPLEMENT CLASSIFICATION LOOKUP LOGIC (Bypass Regression)
    if predicted_class == "Mix":
        macro_scale, micro_scale = 1.0, 1.0
        profile = "Balanced Mix"
    elif predicted_class == "NPK":
        macro_scale, micro_scale = 1.0, 0.0
        profile = "Macro-Leaning Blend"
    elif predicted_class == "Micro":
        macro_scale, micro_scale = 0.0, 1.0
        profile = "Micro-Leaning Blend"
    elif predicted_class == "Water":
        macro_scale, micro_scale = 0.0, 0.0
        profile = "Water Only (No Nutrients)"
    else:
        macro_scale, micro_scale = 1.0, 1.0
        profile = "Balanced"

```

* Maps the AI's discrete classification string to scaling factors for Macronutrients (`macro_scale`) and Micronutrients (`micro_scale`).
* **"Mix"**: Assumes 100% presence of both macro and micro components.
* **"NPK"**: Assumes 100% macronutrients and 0% micronutrients.
* **"Micro"**: Assumes 0% macronutrients and 100% micronutrients.
* **"Water"**: Assumes 0% of both nutrient groupings.
* **Else/Unknown**: Resets to fallback scale values of 1.0 and a profile label of "Balanced".

---

### 3. Dynamic Mass and Concentration Mathematics

```python
    # 4. PERFORM DYNAMIC MATH
    # Grams = (Scaling Index * Target Dosage mL/L * Tank Volume L * Density g/mL) * (NPK % / 100)
    
    # Calculate Macro Contribution
    macro_weight_total = tank.target_macro_dosage_mll * tank.water_volume_liters * tank.macro_density
    n_from_macro = (macro_scale * macro_weight_total) * (tank.macro_n_pct / 100)
    p_from_macro = (macro_scale * macro_weight_total) * (tank.macro_p_pct / 100)
    k_from_macro = (macro_scale * macro_weight_total) * (tank.macro_k_pct / 100)

```

* Calculates the theoretical total weight (in grams) of the macronutrient solution using the tank's configuration parameters:

$$\text{Target Dosage (mL/L)} \times \text{Water Volume (L)} \times \text{Density (g/mL)}$$


* Applies the `macro_scale` factor derived from the AI prediction and extracts the individual mass contributions of Nitrogen (N), Phosphorus (P), and Potassium (K) based on the target percentage configuration values.

```python
    # Calculate Micro Contribution
    micro_weight_total = tank.target_micro_dosage_mll * tank.water_volume_liters * tank.micro_density
    n_from_micro = (micro_scale * micro_weight_total) * (tank.micro_n_pct / 100)
    p_from_micro = (micro_scale * micro_weight_total) * (tank.micro_p_pct / 100)
    k_from_micro = (micro_scale * micro_weight_total) * (tank.micro_k_pct / 100)

```

* Repeats the identical calculation process for the micronutrient liquid solution, computing how much additional mass of N, P, and K comes from the micro solution.

```python
    # 5. Convert Physical Mass (Grams) to Concentration (PPM)
    total_grams = n_from_macro + p_from_macro + k_from_macro + n_from_micro + p_from_micro + k_from_micro

```

* Sums up every individual mass component (both macro and micro sources) to find the combined total weight of all NPK components in grams.

```python
    # 1 mg/L = 1 PPM. Multiply grams by 1000 to get mg, then divide by Liters safely.
    vol = tank.water_volume_liters
    n_ppm = ((n_from_macro + n_from_micro) * 1000) / vol if vol > 0 else 0
    p_ppm = ((p_from_macro + p_from_micro) * 1000) / vol if vol > 0 else 0
    k_ppm = ((k_from_macro + k_from_micro) * 1000) / vol if vol > 0 else 0
    total_ppm = (total_grams * 1000) / vol if vol > 0 else 0

```

* Converts individual grams to milligrams (by multiplying by 1000) and divides by the total volume of water in the tank to calculate Parts Per Million (PPM).
* Includes inline ternary check conditions (`if vol > 0 else 0`) to safeguard against ZeroDivisionError runtime exceptions if a tank volume happens to be unconfigured or set to 0.

---

### 4. Generation of Advisory Texts and Alerts

```python
    if prediction and getattr(prediction, 'is_anomaly', False):
        advisory_sum = "AI Sensor Anomaly Detected"
        advisory_exp = f"Conflicting data! The AI classified this tank visually as '{predicted_class}' but physical sensors read 0."
        advisory_act = "Please manually inspect the tank, check the nutrient solution, and recalibrate your pH/EC sensors."

```

* Checks if the prediction metadata model has an active boolean flag called `is_anomaly`. If true, it overrides the output variables with error warnings alerting the farmer of discrepancies between physical sensor telemetry and AI inference readings.

```python
    elif macro_scale >= 0.9 and micro_scale >= 0.9:
        advisory_sum = "Optimal Nutrient Balance"
        advisory_exp = f"Your {tank.tank_name} has a stable concentration of approximately {round(total_ppm)} PPM (Total NPK). The plants are currently in a high-nutrition environment."
        advisory_act = "No immediate action required. Maintain current environmental conditions."

```

* Triggers if nutrient levels are safe and near capacity ($\ge 90\%$). Sets success-oriented text variables informing the user that everything is stable.

```python
    elif macro_scale < 0.7 or micro_scale < 0.7:
        advisory_sum = "Nutrient Depletion Detected"
        advisory_exp = f"Nutrient levels have dropped significantly. There is only {round(total_ppm)} PPM of total nutrients remaining."
        advisory_act = "Follow the Top-up instructions below to restore the optimal nutrient balance."

```

* Triggers if either nutrient scale dips below $70\%$, populating descriptive warning fields indicating depletion.

```python
    else:
        advisory_sum = "Moderate Concentration"
        advisory_exp = f"Nutrients are at stable but declining levels. Total NPK concentration is {round(total_ppm)} PPM."
        advisory_act = "Monitor closely. Top-up may be required within the next 24-48 hours."

```

* Acts as a fallback condition for intermediate state parameters (between $70\%$ and $90\%$), generating moderate advice warnings.

```python
    alert = None
    if macro_scale < 0.7 or micro_scale < 0.7:
        topup_macro = max(0, (1.0 - macro_scale) * tank.target_macro_dosage_mll * tank.water_volume_liters)
        topup_micro = max(0, (1.0 - micro_scale) * tank.target_micro_dosage_mll * tank.water_volume_liters)
        
        alert = ActionableAlert(
            level="WARNING",
            message=f"Nutrient levels have dropped to {int(min(macro_scale, micro_scale)*100)}% of recommended dosage.",
            action_required=True,
            topup_macro_ml=round(topup_macro, 1),
            topup_micro_ml=round(topup_micro, 1)
        )

```

* Initializes an empty `alert` object.
* If nutrients are low ($< 70\%$), it calculates how many milliliters of macro and micro fertilizers are missing from the target dosage threshold.
* Instantiates and assigns an `ActionableAlert` schema object containing explicit instruction volumes to remediate the system deficiency.

---

### 5. Final Response Construction

```python
    # 7. Construct Response
    return DashboardResponse(
        tank_id=tank.id,
        tank_name=tank.tank_name,
        last_updated=latest_reading.timestamp,
        image_url=str(request.base_url).rstrip("/") + "/" + latest_reading.image_path.replace("\\", "/"),
        health_status="HEALTHY" if macro_scale > 0.8 else "NUTRIENT DEFICIENT",
        profile_detected=profile,
        telemetry=TelemetryData(
            ph=latest_reading.ph,
            ec=latest_reading.ec,
            water_temp=latest_reading.water_temp,
            status="Safe Range" if 5.5 <= latest_reading.ph <= 6.5 else "Action Needed"
        ),
        estimated_nutrients=NutrientEstimation(
            n_ppm=round(n_ppm, 1),
            p_ppm=round(p_ppm, 1),
            k_ppm=round(k_ppm, 1),
            total_estimated_ppm=round(total_ppm, 1)
        ),
        advisory=AdvisoryInsight(
            summary=advisory_sum,
            explanation=advisory_exp,
            farmer_action=advisory_act
        ),
        alert=alert
    )

```

* Combines all prepared calculations, raw database values, nested schema items (`TelemetryData`, `NutrientEstimation`, `AdvisoryInsight`), and the dynamic `alert` into the final `DashboardResponse` format.
* **`image_url`**: Normalizes local file path backslashes and prefixes it with the root host path (`request.base_url`) to deliver a fully qualified absolute URL link accessible via a browser client.
* **`health_status`**: Employs an inline conditional check declaring the tank `"HEALTHY"` if the macronutrient scale stays above $80\%$, otherwise categorizing it as `"NUTRIENT DEFICIENT"`.
* **`telemetry.status`**: Runs an inline evaluation marking the status as `"Safe Range"` if pH falls securely within the $5.5$ to $6.5$ hydroponic target bounds.
