"""
Forward-fill zero/null sensor values in cleaned_daily_readings.
Fills ph, ec, water_temp per experiment_id using the previous non-zero value.
Only updates rows that actually changed.
"""

import pandas as pd
from sqlalchemy import create_engine, text
import os

pd.set_option('future.no_silent_downcasting', True)

DB_URL = os.getenv("DATABASE_URL", "postgresql://fil:@localhost/leafcloud2")
SENSOR_COLS = ['ph', 'ec', 'water_temp']

engine = create_engine(DB_URL)

print("Loading cleaned_daily_readings...")
df = pd.read_sql(
    "SELECT id, experiment_id, ph, ec, water_temp FROM cleaned_daily_readings ORDER BY id ASC",
    engine
)
print(f"  Loaded {len(df)} records\n")

# Snapshot before
for col in SENSOR_COLS:
    zero_count = ((df[col] == 0) | df[col].isna()).sum()
    print(f"  Before — {col}: {zero_count} zero/null")

original = df[SENSOR_COLS].copy()

# Replace 0 with NaN so ffill works
for col in SENSOR_COLS:
    df[col] = df[col].replace(0, pd.NA)

# Forward fill per experiment_id (use previous non-zero value)
df[SENSOR_COLS] = (
    df.groupby('experiment_id')[SENSOR_COLS]
    .transform(lambda g: g.ffill())
)

# Backward fill any remaining NaN at start of a group
df[SENSOR_COLS] = (
    df.groupby('experiment_id')[SENSOR_COLS]
    .transform(lambda g: g.bfill())
)

print()
for col in SENSOR_COLS:
    zero_count = ((df[col] == 0) | df[col].isna()).sum()
    print(f"  After  — {col}: {zero_count} zero/null")

# Only update rows where at least one value changed
changed_mask = (df[SENSOR_COLS] != original).any(axis=1)
changed = df[changed_mask]
print(f"\n  Rows to update: {len(changed)}")

if len(changed) == 0:
    print("  Nothing to update.")
else:
    print("  Writing to DB...")
    records = changed[['id'] + SENSOR_COLS].to_dict('records')

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TEMP TABLE _sensor_updates (
                id INTEGER,
                ph DOUBLE PRECISION,
                ec DOUBLE PRECISION,
                water_temp DOUBLE PRECISION
            )
        """))
        conn.execute(text("""
            INSERT INTO _sensor_updates (id, ph, ec, water_temp)
            VALUES (:id, :ph, :ec, :water_temp)
        """), records)
        result = conn.execute(text("""
            UPDATE cleaned_daily_readings cdr
            SET ph = u.ph, ec = u.ec, water_temp = u.water_temp
            FROM _sensor_updates u
            WHERE cdr.id = u.id
        """))
        print(f"  Updated {result.rowcount} rows")

print("\nDone.")
