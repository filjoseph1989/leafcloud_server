"""
Evaluate cleaned_daily_readings for data quality issues:
- Out-of-range values (hydroponics expected ranges)
- Statistical outliers (z-score per experiment)
- Sudden spikes (consecutive reading diff)
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import os

pd.set_option('future.no_silent_downcasting', True)

DB_URL = os.getenv("DATABASE_URL", "postgresql://fil:@localhost/leafcloud2")

# Expected hydroponics ranges
RANGES = {
    'ph':         (5.0, 7.5),
    'ec':         (0.1, 3.5),
    'water_temp': (15.0, 35.0),
}

# Spike thresholds (max allowable jump between consecutive readings per experiment)
SPIKE = {
    'ph':         1.5,
    'ec':         1.0,
    'water_temp': 5.0,
}

Z_THRESHOLD = 3.0  # standard deviations

engine = create_engine(DB_URL)

print("Loading data...")
df = pd.read_sql("""
    SELECT cdr.id, cdr.timestamp, cdr.ph, cdr.ec, cdr.water_temp,
           cdr.experiment_id, e.bucket_label
    FROM cleaned_daily_readings cdr
    JOIN experiments e ON e.id = cdr.experiment_id
    ORDER BY cdr.experiment_id, cdr.id
""", engine)
print(f"  {len(df)} records, {df['experiment_id'].nunique()} experiments\n")

sep = "=" * 65

# ── 1. Basic statistics per experiment ──────────────────────────
print(sep)
print("1. BASIC STATISTICS PER EXPERIMENT")
print(sep)
for exp_id, grp in df.groupby('experiment_id'):
    label = grp['bucket_label'].iloc[0]
    print(f"\n  Experiment {exp_id} ({label}) — {len(grp)} records")
    print(grp[['ph','ec','water_temp']].describe().round(3).to_string())

# ── 2. Out-of-range values ───────────────────────────────────────
print(f"\n{sep}")
print("2. OUT-OF-RANGE VALUES")
print(sep)
oor_total = 0
for col, (lo, hi) in RANGES.items():
    mask = (df[col] < lo) | (df[col] > hi)
    oor = df[mask][['id','timestamp','experiment_id','bucket_label', col]]
    oor_total += len(oor)
    print(f"\n  {col} (expected {lo}–{hi}): {len(oor)} violations")
    if len(oor):
        print(oor.to_string(index=False))
print(f"\n  Total out-of-range: {oor_total}")

# ── 3. Statistical outliers (z-score per experiment per column) ──
print(f"\n{sep}")
print(f"3. STATISTICAL OUTLIERS (z-score > {Z_THRESHOLD} per experiment)")
print(sep)
outlier_ids = set()
for col in ['ph', 'ec', 'water_temp']:
    col_outliers = []
    for exp_id, grp in df.groupby('experiment_id'):
        mean = grp[col].mean()
        std  = grp[col].std()
        if std == 0:
            continue
        z = (grp[col] - mean) / std
        out = grp[np.abs(z) > Z_THRESHOLD][['id','timestamp','bucket_label', col]].copy()
        out['z_score'] = z[np.abs(z) > Z_THRESHOLD].round(2)
        col_outliers.append(out)
    if col_outliers:
        result = pd.concat(col_outliers)
        outlier_ids.update(result['id'].tolist())
        print(f"\n  {col}: {len(result)} outliers")
        print(result.to_string(index=False))
    else:
        print(f"\n  {col}: 0 outliers")

# ── 4. Sudden spikes (consecutive diff per experiment) ───────────
print(f"\n{sep}")
print("4. SUDDEN SPIKES (consecutive reading jump)")
print(sep)
spike_ids = set()
for col, threshold in SPIKE.items():
    col_spikes = []
    for exp_id, grp in df.groupby('experiment_id'):
        grp = grp.sort_values('id')
        diff = grp[col].diff().abs()
        spikes = grp[diff > threshold][['id','timestamp','bucket_label', col]].copy()
        spikes['jump'] = diff[diff > threshold].round(3)
        col_spikes.append(spikes)
    if col_spikes:
        result = pd.concat(col_spikes)
        result = result[result['jump'].notna()]
        spike_ids.update(result['id'].tolist())
        print(f"\n  {col} (threshold ±{threshold}): {len(result)} spikes")
        if len(result):
            print(result.to_string(index=False))
    else:
        print(f"\n  {col}: 0 spikes")

# ── 5. Summary ───────────────────────────────────────────────────
all_flagged = outlier_ids | spike_ids
print(f"\n{sep}")
print("SUMMARY")
print(sep)
print(f"  Total records          : {len(df)}")
print(f"  Out-of-range           : {oor_total}")
print(f"  Statistical outliers   : {len(outlier_ids)}")
print(f"  Sudden spikes          : {len(spike_ids)}")
print(f"  Unique flagged rows    : {len(all_flagged)}")
print(f"  Clean rows             : {len(df) - len(all_flagged)}")
print()
