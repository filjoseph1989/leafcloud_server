"""
Replace extreme/impossible sensor values in cleaned_daily_readings
with forward-fill per experiment. Records and images are preserved.

Replacement thresholds (values outside = sensor error, not real):
  ph:         valid range 3.0 – 10.0
  ec:         valid range 0.0 – 10.0
  water_temp: valid range 15.0 – 35.0
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import os

pd.set_option('future.no_silent_downcasting', True)

DB_URL = os.getenv("DATABASE_URL", "postgresql://fil:@localhost/leafcloud2")

# Values outside these are treated as sensor errors and replaced
VALID = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 10.0),
    'water_temp': (15.0, 35.0),
}

engine = create_engine(DB_URL)

print("Loading cleaned_daily_readings...")
df = pd.read_sql("""
    SELECT cdr.id, cdr.experiment_id, cdr.ph, cdr.ec, cdr.water_temp,
           e.bucket_label
    FROM cleaned_daily_readings cdr
    JOIN experiments e ON e.id = cdr.experiment_id
    ORDER BY cdr.experiment_id, cdr.id
""", engine)
print(f"  {len(df)} records loaded\n")

sep = "=" * 55

# Show what will be replaced
print(sep)
print("VALUES TO BE REPLACED (outside valid range)")
print(sep)
for col, (lo, hi) in VALID.items():
    mask = (df[col] < lo) | (df[col] > hi)
    bad = df[mask]
    print(f"\n  {col} (valid {lo}–{hi}): {len(bad)} extreme values")
    if len(bad):
        summary = bad.groupby('bucket_label')[col].agg(['count','min','max'])
        print(summary.to_string())

original = df[['ph','ec','water_temp']].copy()

# Mark extreme values as NaN
for col, (lo, hi) in VALID.items():
    mask = (df[col] < lo) | (df[col] > hi)
    df.loc[mask, col] = pd.NA

# Forward fill per experiment
df[['ph','ec','water_temp']] = (
    df.groupby('experiment_id')[['ph','ec','water_temp']]
    .transform(lambda g: g.ffill())
)

# Backward fill for any remaining NaN at start of group
df[['ph','ec','water_temp']] = (
    df.groupby('experiment_id')[['ph','ec','water_temp']]
    .transform(lambda g: g.bfill())
)

# Check remaining NaN after fill
remaining_nan = df[['ph','ec','water_temp']].isna().sum()
if remaining_nan.any():
    print(f"\n⚠️  Could not fill some values (entire experiment had bad data):")
    print(remaining_nan[remaining_nan > 0])

# Only update rows that changed
changed_mask = (df[['ph','ec','water_temp']].round(6) != original.round(6)).any(axis=1)
changed = df[changed_mask]

print(f"\n{sep}")
print("RESULTS")
print(sep)
for col, (lo, hi) in VALID.items():
    still_bad = ((df[col] < lo) | (df[col] > hi)).sum()
    print(f"  {col}: {still_bad} remaining extreme values")

print(f"\n  Rows to update: {len(changed)}")

if len(changed) == 0:
    print("  Nothing to update.")
else:
    records = changed[['id','ph','ec','water_temp']].to_dict('records')
    print("  Writing to DB...")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TEMP TABLE _fix_extremes (
                id INTEGER,
                ph DOUBLE PRECISION,
                ec DOUBLE PRECISION,
                water_temp DOUBLE PRECISION
            )
        """))
        conn.execute(text("""
            INSERT INTO _fix_extremes (id, ph, ec, water_temp)
            VALUES (:id, :ph, :ec, :water_temp)
        """), records)
        result = conn.execute(text("""
            UPDATE cleaned_daily_readings cdr
            SET ph = u.ph, ec = u.ec, water_temp = u.water_temp
            FROM _fix_extremes u
            WHERE cdr.id = u.id
        """))
        print(f"  Updated {result.rowcount} rows ✅")

print("\nDone.")
