import os
import cv2
import uuid
import shutil
import random
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
from controllers.cropping_controller import (
    get_sorted_images, 
    get_unavailable_images, 
    save_progress,
    SOURCE_DIR,
    OUTPUT_DIR,
    CROP_SIZE
)
from image_filtering import calculate_greenness, delete_macos_metadata

# Threshold for greenness filtering
GREEN_THRESHOLD = 5.0
TRASH_DIR = os.path.join(OUTPUT_DIR, "temp_trash")

def get_additional_crop_coords(w, h, size):
    """
    Calculates coordinates for:
    - Right-aligned edge crops
    - Bottom-aligned edge crops
    - Corner (Bottom-Right)
    - Random crops
    """
    coords = []
    
    # Right-aligned edge (slides vertically)
    if w > size:
        for y in range(0, h - size + 1, size):
            coords.append((w - size, y, "right_aligned"))
            
    # Bottom-aligned edge (slides horizontally)
    if h > size:
        for x in range(0, w - size + 1, size):
            coords.append((x, h - size, "bottom_aligned"))
            
    # Corner (Bottom-Right)
    if w > size and h > size:
        coords.append((w - size, h - size, "corner_aligned"))
        
    # Random crops (3 per image)
    for _ in range(3):
        rx = random.randint(0, w - size)
        ry = random.randint(0, h - size)
        coords.append((rx, ry, "random"))
        
    return coords

def batch_process():
    db = SessionLocal()
    try:
        print("--- STARTING BATCH AUTO-GRID + ADDITIONAL CROPS ---")
        
        # Delete AppleDouble files first
        print(f"Cleaning up macOS metadata files in {SOURCE_DIR}...")
        deleted = delete_macos_metadata(SOURCE_DIR)
        if deleted > 0:
            print(f"Deleted {deleted} metadata files.")
        
        if not os.path.isdir(TRASH_DIR):
            os.makedirs(TRASH_DIR, exist_ok=True)

        all_images = get_sorted_images()
        # We pass include_additional=True to find images that haven't had additional crops yet
        unavailable = get_unavailable_images(db, include_additional=True)
        
        to_process = [img for img in all_images if img not in unavailable]
        
        total = len(to_process)
        print(f"Found {len(all_images)} total images.")
        print(f"Skipping {len(unavailable)} already fully processed images.")
        print(f"Processing {total} images...\n")
        
        for idx, rel_path in enumerate(to_process):
            print(f"[{idx+1}/{total}] Processing: {rel_path}...", end=" ", flush=True)
            
            abs_source_path = os.path.join(SOURCE_DIR, rel_path)
            if not os.path.exists(abs_source_path):
                print("FAILED: File not found.")
                continue

            img = cv2.imread(abs_source_path)
            if img is None:
                print("FAILED: Could not read image.")
                continue

            h, w = img.shape[:2]
            
            # Check if standard grid is already done for this image
            progress = db.query(models.ImageCropProgress).filter(models.ImageCropProgress.rel_path == rel_path).first()
            is_grid_done = progress.is_processed if progress else False
            
            strategies = []
            if not is_grid_done:
                # Add Grid Strategy
                for y in range(0, h - CROP_SIZE + 1, CROP_SIZE):
                    for x in range(0, w - CROP_SIZE + 1, CROP_SIZE):
                        strategies.append((x, y, "grid"))
            
            # Always add additional strategies if we are in this loop 
            # (since to_process only includes images that need either grid or additional)
            if not (progress and progress.additional_processed):
                additional = get_additional_crop_coords(w, h, CROP_SIZE)
                strategies.extend(additional)

            if not strategies:
                print("SKIPPED: No new crops to generate.")
                continue

            crops_saved = 0
            crops_trashed = 0
            
            dest_folder = os.path.join(OUTPUT_DIR, os.path.dirname(rel_path))
            if not os.path.isdir(dest_folder):
                try:
                    os.makedirs(dest_folder, exist_ok=True)
                except FileExistsError:
                    if not os.path.isdir(dest_folder):
                        raise
            
            base_name = os.path.splitext(os.path.basename(rel_path))[0]
            
            # Find DailyReading
            search_path = f"images/{rel_path}"
            reading = db.query(models.DailyReading).filter(
                (models.DailyReading.image_path == search_path) | 
                (models.DailyReading.image_path == rel_path)
            ).first()

            # Process all selected strategies
            for x, y, crop_type in strategies:
                crop = img[y:y + CROP_SIZE, x:x + CROP_SIZE]
                
                # Temporary file to check greenness
                unique_id = uuid.uuid4().hex[:6]
                temp_filename = f"temp_{unique_id}.jpg"
                temp_path = os.path.join(OUTPUT_DIR, temp_filename)
                cv2.imwrite(temp_path, crop)
                
                greenness = calculate_greenness(temp_path)
                
                if greenness >= GREEN_THRESHOLD:
                    dest_filename = f"{base_name}_{crop_type}_{y}_{x}_{unique_id}.jpg"
                    dest_path = os.path.join(dest_folder, dest_filename)
                    shutil.move(temp_path, dest_path)
                    crops_saved += 1
                    
                    if reading:
                        new_crop = models.ImageCrop(
                            daily_reading_id=reading.id,
                            crop_path=dest_path.replace("\\", "/"),
                            crop_type=crop_type
                        )
                        db.add(new_crop)
                else:
                    # Move to trash
                    trash_filename = f"{base_name}_{crop_type}_low_green_{y}_{x}_{unique_id}.jpg"
                    trash_path = os.path.join(TRASH_DIR, trash_filename)
                    shutil.move(temp_path, trash_path)
                    crops_trashed += 1
                    
                    # Log trash action
                    log = models.AutomatedActionLog(
                        filename=trash_filename,
                        original_path=f"{rel_path} [{crop_type} {y},{x}]",
                        current_path=trash_path.replace("\\", "/"),
                        action_type="move_to_trash",
                        reason="low_greenness_crop",
                        metric_value=greenness
                    )
                    db.add(log)

            if reading:
                db.commit()
            
            # Mark both as done
            save_progress(rel_path, db, additional=True)
            print(f"DONE ({crops_saved} saved, {crops_trashed} trashed)")

        print("\n--- BATCH PROCESSING COMPLETE ---")
        
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    batch_process()
