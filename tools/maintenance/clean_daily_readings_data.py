import pandas as pd
import numpy as np
from database import engine
from sqlalchemy import text

def clean_sensor_data():
    print("Fetching data from daily_readings...")
    # 1. Data Extraction
    query = "SELECT * FROM daily_readings ORDER BY experiment_id, timestamp ASC"
    df = pd.read_sql(query, engine)
    
    if df.empty:
        print("No data found in daily_readings table.")
        return

    print(f"Loaded {len(df)} records. Starting cleaning process...")

    # 2. Data Cleaning & Imputation
    def mark_outliers(row):
        ph = row['ph']
        ec = row['ec']
        
        # --- pH OUTLIER MARKING ---
        # Mark "Impossible" or "Out of Range" values as NaN (placeholder)
        # These will be calculated base sa trend (interpolation)
        if ph <= 4.0 or ph >= 9.0:
            new_ph = np.nan
        else:
            new_ph = ph

        # --- EC OUTLIER MARKING ---
        # Mark Negative or Extremely High EC as NaN
        if ec < 0 or ec > 8.0:
            new_ec = np.nan
        else:
            new_ec = ec
            
        return pd.Series([new_ph, new_ec], index=['ph', 'ec'])

    # Mark outliers to create "holes" for interpolation
    print("Marking sensor errors and outliers as placeholders...")
    df[['ph', 'ec']] = df.apply(mark_outliers, axis=1)

    # Group by experiment_id to ensure interpolation stays within the same batch
    def impute_group(group):
        # Linear Interpolation: Mag-trace og linya tali sa mga good readings
        # Kini ang makawala sa "flat line" kay mosunod siya sa trend
        group['ph'] = group['ph'].interpolate(method='linear')
        group['ec'] = group['ec'].interpolate(method='linear')
        
        # Fallback: Kung ang sugod o tumoy sa batch maoy nag-error,
        # mogamit ta og ffill/bfill para mapun-an ang buslot.
        group['ph'] = group['ph'].ffill().bfill()
        group['ec'] = group['ec'].ffill().bfill()
        return group

    print("Calculating realistic values via trend-based interpolation...")
    df = df.groupby('experiment_id', group_keys=False).apply(impute_group)

    # 3. Final sanitization and rounding
    df['ph'] = df['ph'].fillna(6.5).round(2)
    df['ec'] = df['ec'].fillna(1.2).round(2) 

    # Drop unwanted columns
    df = df.drop(columns=['ph_is_estimated', 'needs_ph_update', 'status'])

    print("Cleaning complete. Writing to cleaned_daily_readings table...")

    # 4. Data Loading
    # if_exists='replace' creates the table if it doesn't exist, or overwrites it
    df.to_sql('cleaned_daily_readings', engine, if_exists='replace', index=False)
    
    # Add index for performance (using raw SQL)
    with engine.connect() as conn:
        print("Adding indexes to the new table...")
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_cleaned_exp_id ON cleaned_daily_readings(experiment_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_cleaned_timestamp ON cleaned_daily_readings(timestamp);"))
        conn.commit()

    print("Successfully created 'cleaned_daily_readings' table with imputed data.")

if __name__ == "__main__":
    clean_sensor_data()
