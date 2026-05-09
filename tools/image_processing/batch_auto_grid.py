import os
import cv2
import uuid
import random
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from controllers.cropping_controller import (
    get_sorted_images,
    get_unavailable_images,
    SOURCE_DIR,
    OUTPUT_DIR,
    CROP_SIZE
)
from image_filtering import delete_macos_metadata

GREEN_THRESHOLD = 30.0
TRASH_DIR = os.path.join(OUTPUT_DIR, "temp_trash")
BATCH_COMMIT_SIZE = 10
MAX_WORKERS = 4

_LOWER_GREEN = np.array([35, 40, 40])
_UPPER_GREEN = np.array([85, 255, 255])


def _greenness_from_array(bgr_crop: np.ndarray) -> float:
    """Calculate greenness in-memory — no temp file needed."""
    hsv = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, _LOWER_GREEN, _UPPER_GREEN)
    total = bgr_crop.shape[0] * bgr_crop.shape[1]
    return (cv2.countNonZero(mask) / total) * 100.0 if total > 0 else 0.0


def get_additional_crop_coords(w, h, size):
    coords = []
    if w > size:
        for y in range(0, h - size + 1, size):
            coords.append((w - size, y, "right_aligned"))
    if h > size:
        for x in range(0, w - size + 1, size):
            coords.append((x, h - size, "bottom_aligned"))
    if w > size and h > size:
        coords.append((w - size, h - size, "corner_aligned"))
    for _ in range(3):
        rx = random.randint(0, w - size)
        ry = random.randint(0, h - size)
        coords.append((rx, ry, "random"))
    return coords


def _process_image(rel_path, abs_source_path, is_grid_done, additional_done, base_name, dest_folder):
    """
    Thread worker: reads the image once, extracts all crops, checks greenness
    in-memory (no temp files). Returns (saved_list, trashed_list).
    """
    img = cv2.imread(abs_source_path)
    if img is None:
        raise RuntimeError("Could not read image")

    h, w = img.shape[:2]

    strategies = []
    if not is_grid_done:
        for y in range(0, h - CROP_SIZE + 1, CROP_SIZE):
            for x in range(0, w - CROP_SIZE + 1, CROP_SIZE):
                strategies.append((x, y, "grid"))
    if not additional_done:
        strategies.extend(get_additional_crop_coords(w, h, CROP_SIZE))

    if not strategies:
        return [], []

    saved = []
    trashed = []

    for x, y, crop_type in strategies:
        crop = img[y:y + CROP_SIZE, x:x + CROP_SIZE]
        greenness = _greenness_from_array(crop)
        unique_id = uuid.uuid4().hex[:6]

        if greenness >= GREEN_THRESHOLD:
            filename = f"{base_name}_{crop_type}_{y}_{x}_{unique_id}.jpg"
            path = os.path.join(dest_folder, filename)
            cv2.imwrite(path, crop)
            saved.append({'path': path.replace("\\", "/"), 'crop_type': crop_type})
        else:
            filename = f"{base_name}_{crop_type}_low_green_{y}_{x}_{unique_id}.jpg"
            path = os.path.join(TRASH_DIR, filename)
            cv2.imwrite(path, crop)
            trashed.append({
                'path': path.replace("\\", "/"),
                'filename': filename,
                'crop_type': crop_type,
                'greenness': greenness,
                'original_ref': f"{rel_path} [{crop_type} {y},{x}]",
            })

    return saved, trashed


def batch_process():
    db = SessionLocal()
    try:
        print("--- STARTING BATCH AUTO-GRID + ADDITIONAL CROPS ---")

        print(f"Cleaning up macOS metadata files in {SOURCE_DIR}...")
        deleted = delete_macos_metadata(SOURCE_DIR)
        if deleted > 0:
            print(f"Deleted {deleted} metadata files.")

        try:
            os.makedirs(TRASH_DIR, exist_ok=True)
        except FileExistsError:
            if not os.path.isdir(TRASH_DIR):
                raise

        all_images = get_sorted_images()
        unavailable = get_unavailable_images(db, include_additional=True)
        to_process = [img for img in all_images if img not in unavailable]

        total = len(to_process)
        print(f"Found {len(all_images)} total images.")
        print(f"Skipping {len(unavailable)} already fully processed images.")
        print(f"Processing {total} images with {MAX_WORKERS} workers...\n")

        # Bulk pre-load DB records — eliminates per-image queries
        print("Pre-loading DB records...")
        progress_map = {
            p.rel_path: p
            for p in db.query(models.ImageCropProgress).all()
        }
        reading_id_map = {}
        for r in db.query(models.DailyReading).all():
            if r.image_path:
                reading_id_map[r.image_path] = r.id
                if r.image_path.startswith("images/"):
                    reading_id_map[r.image_path[len("images/"):]] = r.id
        print(f"Loaded {len(progress_map)} progress records, {len(reading_id_map)//2} readings.\n")

        # Build work items
        work_items = []
        for rel_path in to_process:
            abs_source_path = os.path.join(SOURCE_DIR, rel_path)
            if not os.path.exists(abs_source_path):
                print(f"SKIPPED (not found): {rel_path}")
                continue

            progress = progress_map.get(rel_path)
            is_grid_done = progress.is_processed if progress else False
            additional_done = progress.additional_processed if progress else False

            # Quick check: if both already done, skip
            if is_grid_done and additional_done:
                continue

            dest_folder = os.path.join(OUTPUT_DIR, os.path.dirname(rel_path))
            try:
                os.makedirs(dest_folder, exist_ok=True)
            except FileExistsError:
                if not os.path.isdir(dest_folder):
                    raise
            base_name = os.path.splitext(os.path.basename(rel_path))[0]

            search_path = f"images/{rel_path}"
            reading_id = reading_id_map.get(search_path) or reading_id_map.get(rel_path)

            work_items.append((rel_path, abs_source_path, is_grid_done, additional_done,
                               base_name, dest_folder, reading_id))

        if not work_items:
            print("Nothing to process.")
            return

        # Submit all work to thread pool; collect results and handle DB in main thread
        future_to_item = {}
        commits_pending = 0
        completed = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for rel_path, abs_path, is_grid_done, additional_done, base_name, dest_folder, reading_id in work_items:
                future = executor.submit(
                    _process_image, rel_path, abs_path, is_grid_done, additional_done, base_name, dest_folder
                )
                future_to_item[future] = (rel_path, reading_id)

            for future in as_completed(future_to_item):
                rel_path, reading_id = future_to_item[future]
                completed += 1

                try:
                    saved, trashed = future.result()
                except Exception as e:
                    print(f"[{completed}/{len(work_items)}] FAILED {rel_path}: {e}")
                    continue

                # Insert ImageCrop records
                if reading_id and saved:
                    for item in saved:
                        db.add(models.ImageCrop(
                            daily_reading_id=reading_id,
                            crop_path=item['path'],
                            crop_type=item['crop_type'],
                        ))

                # Insert AutomatedActionLog records for trashed crops
                for item in trashed:
                    db.add(models.AutomatedActionLog(
                        filename=item['filename'],
                        original_path=item['original_ref'],
                        current_path=item['path'],
                        action_type="move_to_trash",
                        reason="low_greenness_crop",
                        metric_value=item['greenness'],
                    ))

                # Update progress record using pre-loaded map (avoids extra DB query)
                progress = progress_map.get(rel_path)
                if not progress:
                    progress = models.ImageCropProgress(
                        rel_path=rel_path, is_processed=True,
                        additional_processed=True, locked_until=None
                    )
                    db.add(progress)
                    progress_map[rel_path] = progress
                else:
                    progress.is_processed = True
                    progress.additional_processed = True
                    progress.locked_until = None

                commits_pending += 1
                if commits_pending >= BATCH_COMMIT_SIZE:
                    db.commit()
                    commits_pending = 0

                print(f"[{completed}/{len(work_items)}] {rel_path}: "
                      f"{len(saved)} saved, {len(trashed)} trashed")

        if commits_pending > 0:
            db.commit()

        print("\n--- BATCH PROCESSING COMPLETE ---")

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    batch_process()
