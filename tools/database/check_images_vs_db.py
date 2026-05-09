"""
Temporary script: Cross-check images in a date folder vs daily_readings table.
Also checks temp_trash folders for missing files.
Usage: python tools/database/check_images_vs_db.py [date]
Default date: 2026-04-16
"""

import os
import re
import sys
from sqlalchemy import create_engine, text

DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-04-16"

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_backup = os.path.join(_root, ".images_c", DATE)
_primary = os.path.join(_root, "images", DATE)
BASE_DIR = _backup if os.path.exists(_backup) else _primary

TRASH_DIRS = [
    os.path.join(_root, ".images_d", "temp_trash"),
    os.path.join(_root, "images", "temp_trash"),
]

DB_URL = os.getenv("DATABASE_URL", "postgresql://fil:@localhost/leafcloud2")

# Hash prefix pattern: 32 hex chars + underscore
_HASH_PREFIX = re.compile(r'^[0-9a-f]{32}_')

print(f"\n{'='*60}")
print(f"Checking: {BASE_DIR}")
print(f"{'='*60}\n")

# --- 0. Delete Apple Double files (._filename, .DS_Store) ---
apple_double_deleted = 0
if os.path.exists(BASE_DIR):
    for root, dirs, files in os.walk(BASE_DIR):
        for f in files:
            if f.startswith('._') or f == '.DS_Store':
                os.remove(os.path.join(root, f))
                apple_double_deleted += 1
    if apple_double_deleted:
        print(f"🧹 Deleted {apple_double_deleted} Apple Double / .DS_Store file(s)\n")
    else:
        print("✅ No Apple Double files found\n")

# --- 1. Collect images on disk (main folder) ---
# Normalize to DB path format (images/DATE/...) regardless of actual folder location
disk_images = set()
if os.path.exists(BASE_DIR):
    for root, dirs, files in os.walk(BASE_DIR):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                # Get sub-path relative to BASE_DIR (e.g. Micro/reading_Micro_....jpg)
                sub_path = os.path.relpath(os.path.join(root, f), BASE_DIR)
                # Always map to canonical DB format: images/DATE/sub_path
                db_equiv = os.path.join("images", DATE, sub_path)
                disk_images.add(db_equiv)
else:
    print(f"⚠️  Folder does not exist: {BASE_DIR}\n")

print(f"📁 Images found on disk: {len(disk_images)}")

# --- 2. Build trash index: original_basename -> full_path ---
# Trash files have {32hex}_{original_name} format
trash_index = {}
for trash_dir in TRASH_DIRS:
    if not os.path.exists(trash_dir):
        continue
    for root, dirs, files in os.walk(trash_dir):
        for f in files:
            if not f.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            original_name = _HASH_PREFIX.sub('', f)
            full_path = os.path.join(root, f)
            if original_name not in trash_index:
                trash_index[original_name] = []
            trash_index[original_name].append(full_path)

print(f"🗑️  Trash index built: {len(trash_index)} unique filenames across trash folders")

# --- 3. Collect DB records for the date ---
engine = create_engine(DB_URL)
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT id, timestamp, image_path
        FROM daily_readings
        WHERE DATE(timestamp AT TIME ZONE 'Asia/Manila') = :date
        ORDER BY id ASC
    """), {"date": DATE})
    rows = result.fetchall()

db_total = len(rows)
db_with_image = [(r.id, r.timestamp, r.image_path) for r in rows if r.image_path and r.image_path.strip()]
db_without_image = [(r.id, r.timestamp) for r in rows if not r.image_path or not r.image_path.strip()]
db_paths = {r.image_path.strip() for r in rows if r.image_path and r.image_path.strip()}

print(f"🗄️  DB records for {DATE}: {db_total}")
print(f"   ✅ With image_path: {len(db_with_image)}")
print(f"   ❌ Without image_path: {len(db_without_image)}")

# --- 4. Cross-check ---
print(f"\n{'='*60}")
print("CROSS-CHECK RESULTS")
print(f"{'='*60}")

orphan_images = disk_images - db_paths
missing_files = db_paths - disk_images

# For missing files, check if they exist in trash
found_in_trash = {}    # db_path -> [trash locations]
truly_missing = set()

for db_path in missing_files:
    basename = os.path.basename(db_path)
    if basename in trash_index:
        found_in_trash[db_path] = trash_index[basename]
    else:
        truly_missing.add(db_path)

print(f"\n📂 Images on disk NOT in DB ({len(orphan_images)}):")
if orphan_images:
    for p in sorted(orphan_images):
        print(f"   {p}")
else:
    print("   (none)")

print(f"\n🗑️  DB image_paths MISSING on disk but FOUND IN TRASH ({len(found_in_trash)}):")
if found_in_trash:
    for db_path, locations in sorted(found_in_trash.items()):
        print(f"   DB : {db_path}")
        for loc in locations:
            print(f"        → {os.path.relpath(loc, _root)}")
else:
    print("   (none)")

print(f"\n❌ DB image_paths TRULY MISSING (not on disk, not in trash) ({len(truly_missing)}):")
if truly_missing:
    for p in sorted(truly_missing):
        print(f"   {p}")
else:
    print("   (none)")

print(f"\n🚫 DB records with NO image_path ({len(db_without_image)}):")
if db_without_image:
    for rid, ts in db_without_image[:20]:
        print(f"   id={rid}  ts={ts}")
    if len(db_without_image) > 20:
        print(f"   ... and {len(db_without_image) - 20} more")
else:
    print("   (none)")

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
print(f"  Apple doubles deleted  : {apple_double_deleted}")
print(f"  Disk images            : {len(disk_images)}")
print(f"  DB total records       : {db_total}")
print(f"  DB w/ image_path       : {len(db_with_image)}")
print(f"  DB w/o image_path      : {len(db_without_image)}")
print(f"  Orphan on disk         : {len(orphan_images)}")
print(f"  Missing (in trash)     : {len(found_in_trash)}")
print(f"  Missing (truly gone)   : {len(truly_missing)}")
print()
