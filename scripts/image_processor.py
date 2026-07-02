import os
import cv2
import uuid
import shutil
import logging
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import CleanedDailyReading, ImageCrop, ImageCropProgress, AutomatedActionLog
from app.services.image_processing import (
    calculate_greenness, 
    delete_macos_metadata,
    get_crop_coordinates,
    get_sorted_images,
    get_unavailable_images,
    save_progress
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

TRASH_DIR = os.path.join(settings.OUTPUT_DIR, "temp_trash")

def process_single_image(db, rel_path, source_dir, output_dir):
    """
    Processes a single image: generates crops, filters by greenness, 
    and saves to database.
    """
    abs_source_path = os.path.join(source_dir, rel_path)
    img = cv2.imread(abs_source_path)
    if img is None:
        logger.error(f"Could not read image: {rel_path}")
        return False

    h, w = img.shape[:2]
    progress = db.query(ImageCropProgress).filter(ImageCropProgress.rel_path == rel_path).first()
    
    strategies = []
    # 1. Check if we need standard grid
    if not (progress and progress.is_processed):
        # We'll just generate all and filter by type later if needed, 
        # but the original logic had a specific split.
        all_coords = get_crop_coordinates(w, h, settings.CROP_SIZE)
        strategies = [c for c in all_coords if c[2] == "grid"]

    # 2. Check if we need additional crops
    if not (progress and progress.additional_processed):
        all_coords = get_crop_coordinates(w, h, settings.CROP_SIZE)
        strategies.extend([c for c in all_coords if c[2] != "grid"])

    if not strategies:
        return True # Nothing to do, consider it success

    # Find CleanedDailyReading to link the crops
    # Match the search logic from the original script
    search_path_long = f"images/{rel_path}"
    reading = db.query(CleanedDailyReading).filter(
        (CleanedDailyReading.image_path == search_path_long) | 
        (CleanedDailyReading.image_path == rel_path)
    ).first()

    base_name = os.path.splitext(os.path.basename(rel_path))[0]
    dest_folder = os.path.join(output_dir, os.path.dirname(rel_path))
    os.makedirs(dest_folder, exist_ok=True)
    os.makedirs(TRASH_DIR, exist_ok=True)

    crops_saved = 0
    crops_trashed = 0

    for x, y, crop_type in strategies:
        crop = img[y:y + settings.CROP_SIZE, x:x + settings.CROP_SIZE]
        unique_id = uuid.uuid4().hex[:6]
        temp_path = os.path.join(output_dir, f"temp_{unique_id}.jpg")
        cv2.imwrite(temp_path, crop)
        
        greenness = calculate_greenness(temp_path)
        
        if greenness >= settings.GREEN_THRESHOLD:
            dest_filename = f"{base_name}_{crop_type}_{y}_{x}_{unique_id}.jpg"
            dest_path = os.path.join(dest_folder, dest_filename)
            shutil.move(temp_path, dest_path)
            crops_saved += 1
            
            if reading:
                new_crop = ImageCrop(
                    daily_reading_id=reading.id,
                    crop_path=dest_path.replace("\\", "/"),
                    crop_type=crop_type
                )
                db.add(new_crop)
        else:
            trash_filename = f"{base_name}_{crop_type}_low_green_{y}_{x}_{unique_id}.jpg"
            trash_path = os.path.join(TRASH_DIR, trash_filename)
            shutil.move(temp_path, trash_path)
            crops_trashed += 1
            
            log = AutomatedActionLog(
                filename=trash_filename,
                original_path=f"{rel_path} [{crop_type} {y},{x}]",
                current_path=trash_path.replace("\\", "/"),
                action_type="move_to_trash",
                reason="low_greenness_crop",
                metric_value=greenness
            )
            db.add(log)

    db.commit()
    save_progress(rel_path, db, additional=True)
    logger.info(f"Done: {rel_path} ({crops_saved} saved, {crops_trashed} trashed)")
    return True

def run_batch_processing():
    """
    Main entry point for batch processing.
    """
    db = SessionLocal()
    try:
        logger.info("--- STARTING IMAGE PROCESSOR ---")
        
        # 1. Cleanup
        logger.info(f"Cleaning up metadata in {settings.SOURCE_DIR}...")
        delete_macos_metadata(settings.SOURCE_DIR)
        
        # 2. Identify images to process
        all_images = get_sorted_images(settings.SOURCE_DIR)
        unavailable = get_unavailable_images(db, include_additional=True)
        to_process = [img for img in all_images if img not in unavailable]
        
        logger.info(f"Found {len(all_images)} total images.")
        logger.info(f"Skipping {len(unavailable)} already processed images.")
        logger.info(f"Processing {len(to_process)} images...\n")
        
        for idx, rel_path in enumerate(to_process):
            logger.info(f"[{idx+1}/{len(to_process)}] Processing: {rel_path}")
            process_single_image(db, rel_path, settings.SOURCE_DIR, settings.OUTPUT_DIR)

        logger.info("\n--- BATCH PROCESSING COMPLETE ---")
        
    except Exception as e:
        logger.error(f"Fatal error during batch processing: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_batch_processing()
