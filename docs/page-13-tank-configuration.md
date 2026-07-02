[Prev](./page-12-image-processing-logic.md) | [Next](./page-14-mobile-api-integration.md)

# Database Model: **Tank Configuration**

This document explains the schema and purpose of the `tank_configs` table, which stores dynamic application settings.

## 1. Overview
The `tank_configs` table stores all physical and chemical parameters needed for the system to perform real-time NPK calculations. It allows the LeafCloud app to be dynamic, adapting to different tank sizes and fertilizer brands without code changes.

## 2. Table Schema

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | Unique identifier (Primary Key). |
| `tank_name` | String(50) | Human-readable name (e.g., "Lettuce Bed A"). |
| `water_volume_liters` | Float | Total capacity of the reservoir in Liters. |
| `macro_brand_name` | String(100) | Brand of the NPK fertilizer. |
| `macro_n_pct` | Float | Nitrogen % in the Macro fertilizer. |
| `macro_p_pct` | Float | Phosphate % in the Macro fertilizer. |
| `macro_k_pct` | Float | Potash % in the Macro fertilizer. |
| `macro_density` | Float | Density of the Macro fertilizer (g/mL, default 1.0). |
| `micro_brand_name` | String(100) | Brand of the Micro fertilizer. |
| `micro_n_pct` | Float | Nitrogen % in the Micro fertilizer. |
| `micro_p_pct` | Float | Phosphate % in the Micro fertilizer. |
| `micro_k_pct` | Float | Potash % in the Micro fertilizer. |
| `micro_density` | Float | Density of the Micro fertilizer (g/mL, default 1.0). |
| `target_macro_dosage_mll` | Float | Baseline dosage for Macro (mL per Liter). |
| `target_micro_dosage_mll` | Float | Baseline dosage for Micro (mL per Liter). |
| `is_active` | Boolean | Whether this configuration is currently active. |

## 3. Business Logic
- **Dynamic Math**: The backend uses the `water_volume_liters` and the `target_dosage` fields to calculate the total physical weight/volume of nutrients required for a full cycle.
- **Fertilizer Profiles**: The N-P-K percentages allow for accurate concentration estimation regardless of the brand used.
- **Concurrency**: Only one configuration should typically be `is_active` per tank.

## 4. Verification
Check currently active configurations:
```bash
./scripts/run-query.sh "SELECT tank_name, water_volume_liters, is_active FROM tank_configs WHERE is_active = true;"
```

---

[Prev](./page-12-image-processing-logic.md) | [Next](./page-14-mobile-api-integration.md)
