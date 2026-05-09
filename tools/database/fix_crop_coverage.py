"""
Fix two crop coverage issues:
1. Delete Apple Double files (._filename) found by get_sorted_images()
2. Reset ImageCropProgress + ImageCrop records for images marked done but with 0 crops on disk
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database import SessionLocal
import models
from controllers.cropping_controller import get_sorted_images, SOURCE_DIR, OUTPUT_DIR

db = SessionLocal()

print("Loading records...")
progress_map = {
    p.rel_path: p
    for p in db.query(models.ImageCropProgress).all()
}
all_images = get_sorted_images()

apple_doubles = []
reset_needed  = []

for rel_path in all_images:
    basename = os.path.basename(rel_path)

    # Issue 1: Apple Double files
    if basename.startswith("._"):
        apple_doubles.append(rel_path)
        continue

    progress = progress_map.get(rel_path)
    if not progress:
        continue

    # Issue 2: marked done but 0 crop files on disk
    dest_folder = os.path.join(OUTPUT_DIR, os.path.dirname(rel_path))
    base_name   = os.path.splitext(basename)[0]
    if os.path.isdir(dest_folder):
        crops = [f for f in os.listdir(dest_folder) if f.startswith(base_name)]
    else:
        crops = []

    if len(crops) == 0:
        reset_needed.append(rel_path)

print(f"Apple Double files to delete : {len(apple_doubles)}")
print(f"Progress records to reset    : {len(reset_needed)}")

# --- Fix 1: Delete Apple Double files ---
deleted = 0
for rel_path in apple_doubles:
    abs_path = os.path.join(SOURCE_DIR, rel_path)
    try:
        os.remove(abs_path)
        deleted += 1
    except Exception as e:
        print(f"  Could not delete {rel_path}: {e}")
print(f"\n✅ Deleted {deleted} Apple Double files.")

# --- Fix 2: Reset progress + ImageCrop records ---
reset_count  = 0
crop_deleted = 0

for rel_path in reset_needed:
    # Delete ImageCrop records linked to the DailyReading for this image
    search_path = f"images/{rel_path}"
    reading = db.query(models.DailyReading).filter(
        (models.DailyReading.image_path == search_path) |
        (models.DailyReading.image_path == rel_path)
    ).first()

    if reading:
        deleted_crops = db.query(models.ImageCrop).filter(
            models.ImageCrop.daily_reading_id == reading.id
        ).delete()
        crop_deleted += deleted_crops

    # Delete the ImageCropProgress record
    progress = progress_map.get(rel_path)
    if progress:
        db.delete(progress)
        reset_count += 1

db.commit()
print(f"✅ Reset {reset_count} ImageCropProgress records.")
print(f"✅ Deleted {crop_deleted} orphan ImageCrop records.")
print(f"\nDone. Run batch_auto_grid.py to re-crop the {len(reset_needed)} images.")

db.close()
