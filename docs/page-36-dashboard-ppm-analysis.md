[Prev](./page-35-account-lifecycle.md) | [Next](./page-37-model-analysis-v3-v5.md)

# Dashboard PPM Analysis — Gemini Feedback Review

**Date:** 2026-05-29  
**Tank:** Reservoir (tank_id=1)  
**Reading at time of review:** EC=1.34 mS/cm, predicted_class=Mix, total_estimated_ppm=1940

---

## Summary

The dashboard response was reviewed against Gemini's agronomic recommendations for hydroponic lettuce. Gemini flagged the nutrient profile as potentially harmful for lettuce due to high total PPM (1940) and a P-dominant NPK ratio.

**Conclusion: No code changes or config changes are needed.** The tank config correctly reflects the actual experiment setup. Gemini's feedback is an agronomic observation about the experiment design, not a software bug.

---

## How PPM Is Calculated

The dashboard computes PPM from the tank config — not from EC directly:

```
macro_weight = target_macro_dosage_mll × water_volume_liters × macro_density
             = 2 mL/L × 6 L × 1 g/mL = 12 grams

micro_weight = 2 mL/L × 6 L × 1 g/mL = 12 grams
```

Applied to the configured NPK percentages:

| Source | N (8%) | P (15%) | K (36%/15%) | Total grams |
|--------|--------|---------|-------------|-------------|
| Macro (12g) | 0.96g | 1.80g | 4.32g | 7.08g |
| Micro (12g) | 0.96g | 1.80g | 1.80g | 4.56g |
| **PPM (÷ 6L)** | **320** | **600** | **1020** | **1940** |

The math is correct and the config accurately reflects the experiment.

---

## Current Tank Config (tank_id=1)

| Parameter | Value | Notes |
|-----------|-------|-------|
| water_volume_liters | 6 L | 6-liter reservoir |
| target_macro_dosage_mll | 2 mL/L | Experiment dosage |
| target_micro_dosage_mll | 2 mL/L | Experiment dosage |
| macro_density / micro_density | 1.0 g/mL | |
| macro N/P/K | 8% / 15% / 36% | From actual fertilizer label |
| micro N/P/K | 8% / 15% / 15% | From actual fertilizer label |
| **Full-scale PPM** | **1940 PPM** | At macro_scale=1, micro_scale=1 |

---

## Gemini's Agronomic Feedback vs. Software Behavior

Gemini's concern is that 1940 PPM at the current NPK ratio is not optimal for lettuce. This is agronomically valid but is **not a software problem**.

| Gemini's Flag | What It Actually Means |
|---------------|------------------------|
| Total PPM = 1940 (too high) | The experiment uses 2 mL/L dosage — this accurately reflects what's in the tank |
| P (600 PPM) > N (320 PPM) | The fertilizer used has a P-dominant ratio — this is the real-world fertilizer composition |
| Advisory says "Optimal" | Dashboard is correct — nutrients ARE at full dosage as configured; the advisory reflects model confidence, not crop suitability |

The dashboard is reporting truthfully. The AI correctly identified Mix, the regression correctly returned macro≈1/micro≈1, and the PPM calculation correctly converted that to 1940 PPM using the configured fertilizer data.

---

## Gemini's Recommended Ranges for Lettuce (For Reference)

| Parameter | Current Experiment | Lettuce Optimal | Status |
|-----------|-------------------|-----------------|--------|
| pH | 6.14 | 5.5 – 6.5 | ✅ Excellent |
| Water Temp | 25.7°C | 18°C – 24°C | ⚠️ Slightly warm (acceptable for tropical) |
| EC | 1.34 mS/cm | 1.0 – 1.4 mS/cm | ✅ Within range |
| Total PPM | 1940 PPM | 560 – 980 PPM | ⚠️ High for lettuce |
| N:P ratio | P > N | N > P (N-heavy for leafy greens) | ⚠️ Inverted for lettuce |

EC is within the lettuce-optimal range — this is the physical sensor measurement and is reliable. The PPM discrepancy exists because PPM is computed from the configured fertilizer dosage, which is higher than the lettuce-optimal range.

---

## Key Distinction: EC vs. PPM

EC (1.34 mS/cm) and total_estimated_ppm (1940) appear contradictory:
- Standard conversion: 1.34 mS/cm × ~700 factor ≈ 938 PPM — within lettuce range
- But the dashboard shows 1940 PPM

They measure different things:
- **EC** is a real-time physical sensor reading of ion concentration in the water
- **total_estimated_ppm** is calculated from the configured fertilizer dosage at full scale — it represents the theoretical PPM if the full configured dose is present

The dashboard PPM is not derived from EC. It assumes `macro_scale` and `micro_scale` represent the fraction of the configured dose remaining, then applies the fertilizer's NPK composition to calculate elemental concentration. This is by design.

If the experiment's actual fertilizer produces EC=1.34 at 2 mL/L dosage, the EC-to-PPM conversion (×700) would give ~938 PPM — closer to what Gemini recommends. The 1940 PPM figure is a theoretical maximum based on the fertilizer label's NPK percentages, not a direct EC measurement.

---

## Conclusion

The software and configuration are working correctly for this experiment. Gemini's feedback highlights a potential agronomic issue with the experiment design (fertilizer choice and dosage for lettuce) rather than a problem with the system.

If a future experiment is designed specifically for lettuce optimization, the tank config's `target_macro_dosage_mll`, `target_micro_dosage_mll`, and NPK percentages should be updated to reflect the lettuce-appropriate fertilizer being used. The code will correctly calculate PPM from whatever values are stored in the config.

---

## Config vs. Experiment — Should We Change Anything?

**No.** The tank config should not be changed because it accurately reflects the actual experiment: 2 mL/L of that specific fertilizer in a 6L reservoir. Changing the config would make the PPM calculations no longer represent reality.

Gemini's recommendation to dilute and adjust the nutrient profile is **agronomic advice for the experiment**, not a software fix. If a future experiment is run with a different fertilizer or dosage, update the config to match whatever is physically being used — the dashboard math will follow automatically.

---

## EC vs. total_estimated_ppm — Why They Appear Contradictory

EC reads 1.34 mS/cm, which using the standard ×700 conversion gives approximately **938 PPM** — within Gemini's recommended lettuce range of 560–980 PPM. But the dashboard reports **1940 PPM**. These are not contradicting each other — they measure different things:

| | EC-derived PPM | Dashboard total_estimated_ppm |
|--|---------------|-------------------------------|
| **Source** | Physical sensor (real-time ion measurement) | Fertilizer label NPK% × configured dosage |
| **Value** | ~938 PPM (1.34 × 700) | 1940 PPM |
| **Represents** | Actual dissolved ion concentration in water right now | Theoretical elemental mass if the full configured dose is present |

The 1940 PPM figure is a theoretical maximum computed from the fertilizer label's stated NPK percentages at full dosage. EC-derived PPM (~938) is what's actually dissolved and measurable in the water.

The gap between them (1940 vs 938) is normal — fertilizer labels state elemental percentages by weight of the dry/liquid concentrate, not by what fully dissolves and remains bioavailable. In practice, not all of the stated NPK content ends up as free ions in solution.

**Implication:** If Gemini's concern is that 1940 PPM would cause osmotic stress on the roots, the EC sensor at 1.34 mS/cm suggests the actual dissolved concentration (~938 PPM by EC conversion) is within the safe lettuce range. The plants are likely experiencing the EC, not the theoretical 1940 PPM figure from the label math.
