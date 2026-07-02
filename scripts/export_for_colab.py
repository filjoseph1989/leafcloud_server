"""
Run this locally BEFORE uploading to Colab.

Outputs:
  - exports/colab_training_data.csv   (the query results with relative image paths)
  - exports/colab_crops.zip           (all crop images referenced in the CSV)

Then upload both files to your Google Drive.
"""
import os
import sys
import zipfile
import pandas as pd
from sqlalchemy import create_engine
from tqdm import tqdm

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.config import settings

EXPORT_DIR = 'exports'
CSV_PATH   = os.path.join(EXPORT_DIR, 'colab_training_data.csv')
ZIP_PATH   = os.path.join(EXPORT_DIR, 'colab_crops.zip')

os.makedirs(EXPORT_DIR, exist_ok=True)

print('🔌 Connecting to database...')
engine = create_engine(settings.DATABASE_URL)

query = """
SELECT
    ic.crop_path  AS image_path,
    cdr.ph,
    cdr.ec,
    cdr.water_temp,
    e.bucket_label
FROM image_crops ic
JOIN cleaned_daily_readings cdr ON ic.daily_reading_id = cdr.id
JOIN experiments e ON cdr.experiment_id = e.id
WHERE e.bucket_label IN ('NPK', 'Micro', 'Mix', 'Water')
"""
df = pd.read_sql(query, engine)
print(f'  Fetched {len(df)} crop records')
print(df['bucket_label'].value_counts())

# Verify files exist and keep relative paths for portability
print('\n🔍 Verifying image files...')
valid_rows = []
missing = 0
for _, row in tqdm(df.iterrows(), total=len(df)):
    if os.path.exists(row['image_path']):
        valid_rows.append(row)
    else:
        missing += 1

if missing:
    print(f'⚠️  {missing} missing files skipped.')

df_valid = pd.DataFrame(valid_rows).reset_index(drop=True)

# Store relative paths — Colab script will prepend the Drive mount point
df_valid.to_csv(CSV_PATH, index=False)
print(f'\n✅ CSV saved to {CSV_PATH} ({len(df_valid)} rows)')

# Zip all referenced crop images
print(f'\n📦 Zipping {len(df_valid)} images to {ZIP_PATH}...')
with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zf:
    for path in tqdm(df_valid['image_path'], desc='Zipping'):
        zf.write(path, arcname=path)

size_mb = os.path.getsize(ZIP_PATH) / (1024 * 1024)
print(f'✅ Zip saved to {ZIP_PATH} ({size_mb:.1f} MB)')

print('\n--- Next steps ---')
print(f'1. Upload {CSV_PATH} to Google Drive')
print(f'2. Upload {ZIP_PATH} to Google Drive')
print(f'3. Open scripts/nutrient_classifier_v4_colab.py in Google Colab')
