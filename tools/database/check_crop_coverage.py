"""
Checks each source image in images/ and reports whether it has been cropped
(i.e. has an ImageCropProgress record and actual crop files in cropped_dataset/).
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database import SessionLocal
import models
from controllers.cropping_controller import get_sorted_images, SOURCE_DIR, OUTPUT_DIR

db = SessionLocal()

print("Loading progress records from DB...")
progress_map = {
    p.rel_path: p
    for p in db.query(models.ImageCropProgress).all()
}

all_images = get_sorted_images()
print(f"Total source images found: {len(all_images)}\n")

no_progress   = []   # no DB record at all
no_crops_disk = []   # has DB record but 0 crop files on disk
missing_src   = []   # DB record exists but source image missing
ok            = []

for rel_path in all_images:
    abs_src = os.path.join(SOURCE_DIR, rel_path)
    src_exists = os.path.exists(abs_src)

    progress = progress_map.get(rel_path)

    if not progress:
        no_progress.append((rel_path, src_exists))
        continue

    if not src_exists:
        missing_src.append(rel_path)

    # Check actual crop files on disk
    dest_folder = os.path.join(OUTPUT_DIR, os.path.dirname(rel_path))
    base_name   = os.path.splitext(os.path.basename(rel_path))[0]

    if os.path.isdir(dest_folder):
        crops = [f for f in os.listdir(dest_folder) if f.startswith(base_name)]
    else:
        crops = []

    if len(crops) == 0:
        no_crops_disk.append(rel_path)
    else:
        ok.append((rel_path, len(crops)))

db.close()

print(f"{'='*60}")
print(f"✅  Has crops on disk       : {len(ok)}")
print(f"❌  No progress record      : {len(no_progress)}")
print(f"⚠️   Progress done but 0 crops on disk: {len(no_crops_disk)}")
print(f"🔍  Source image missing   : {len(missing_src)}")
print(f"{'='*60}\n")

if no_progress:
    print(f"--- No progress record ({len(no_progress)}) ---")
    for rel, src_ok in no_progress[:20]:
        tag = "src OK" if src_ok else "src MISSING"
        print(f"  [{tag}] {rel}")
    if len(no_progress) > 20:
        print(f"  ... and {len(no_progress)-20} more")
    print()

if no_crops_disk:
    print(f"--- Progress marked done but 0 crop files found ({len(no_crops_disk)}) ---")
    for rel in no_crops_disk[:20]:
        print(f"  {rel}")
    if len(no_crops_disk) > 20:
        print(f"  ... and {len(no_crops_disk)-20} more")
    print()

if missing_src:
    print(f"--- Source image gone (stale/deleted) ({len(missing_src)}) ---")
    for rel in missing_src[:20]:
        print(f"  {rel}")
    if len(missing_src) > 20:
        print(f"  ... and {len(missing_src)-20} more")
