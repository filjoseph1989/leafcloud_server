import os
import cv2
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
from schemas.cropping import CropRequest, SkipRequest, CropNextResponse
from database import get_db
import models

cropping_router = APIRouter(prefix="/api/v1/images/crop", tags=["Image Cropping"])

SOURCE_DIR = "images"
OUTPUT_DIR = "cropped_dataset"
CROP_SIZE = 224

def get_sorted_images() -> List[str]:
    """Returns a chronologically sorted list of relative image paths."""
    all_files = []
    extensions = ('.jpg', '.jpeg', '.png')
    for root, _, files in os.walk(SOURCE_DIR):
        if "temp_trash" in root or OUTPUT_DIR in root:
            continue
        for f in files:
            if f.lower().endswith(extensions):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, SOURCE_DIR).replace("\\", "/")
                all_files.append(rel_path)
    all_files.sort()
    return all_files

def get_unavailable_images(db: Session) -> List[str]:
    """Returns a list of image paths that are either processed or currently locked."""
    now = datetime.now()
    unavailable = db.query(models.ImageCropProgress.rel_path).filter(
        or_(
            models.ImageCropProgress.is_processed == True,
            models.ImageCropProgress.locked_until > now
        )
    ).all()
    return [u.rel_path for u in unavailable]

def lock_image(rel_path: str, db: Session, minutes: int = 5):
    """Locks an image for a specific duration to prevent concurrent access."""
    now = datetime.now()
    until = now + timedelta(minutes=minutes)
    
    progress = db.query(models.ImageCropProgress).filter(models.ImageCropProgress.rel_path == rel_path).first()
    if not progress:
        progress = models.ImageCropProgress(rel_path=rel_path, is_processed=False, locked_until=until)
        db.add(progress)
    else:
        progress.locked_until = until
    db.commit()

def save_progress(rel_path: str, db: Session):
    progress = db.query(models.ImageCropProgress).filter(models.ImageCropProgress.rel_path == rel_path).first()
    if not progress:
        progress = models.ImageCropProgress(rel_path=rel_path, is_processed=True, locked_until=None)
        db.add(progress)
    else:
        progress.is_processed = True
        progress.locked_until = None
    db.commit()

@cropping_router.get("/next", response_model=CropNextResponse)
def get_next_crop_image(db: Session = Depends(get_db)):
    """Returns the next image that needs to be cropped and locks it for 5 minutes."""
    images = get_sorted_images()
    if not images:
        raise HTTPException(status_code=404, detail="No images found in source directory.")

    unavailable = get_unavailable_images(db)
    
    # Find the first image that is not unavailable
    next_image = None
    for img in images:
        if img not in unavailable:
            next_image = img
            break

    if not next_image:
        raise HTTPException(status_code=404, detail="All images have been processed or are currently locked.")

    # Lock it for 5 minutes
    lock_image(next_image, db, minutes=5)

    return {
        "rel_path": next_image,
        "image_url": f"/images/{next_image}"
    }

@cropping_router.post("/submit")
def submit_crop(request: CropRequest, db: Session = Depends(get_db)):
    """Processes the crop coordinates from mobile and saves the result."""
    abs_source_path = os.path.join(SOURCE_DIR, request.rel_path)
    if not os.path.exists(abs_source_path):
        raise HTTPException(status_code=404, detail="Original image not found.")

    img = cv2.imread(abs_source_path)
    if img is None:
        raise HTTPException(status_code=400, detail="Failed to load image.")

    h_orig, w_orig = img.shape[:2]

    # Calculate scale factor based on mobile display size
    scale_x = w_orig / request.display_width
    scale_y = h_orig / request.display_height

    # Convert mobile coordinates to original image coordinates
    real_cx = int(request.center_x * scale_x)
    real_cy = int(request.center_y * scale_y)

    # Calculate 224x224 bounding box
    half = CROP_SIZE // 2
    x1 = max(0, real_cx - half)
    y1 = max(0, real_cy - half)
    x2 = x1 + CROP_SIZE
    y2 = y1 + CROP_SIZE

    # Boundary adjustment
    if x2 > w_orig:
        x2 = w_orig
        x1 = w_orig - CROP_SIZE
    if y2 > h_orig:
        y2 = h_orig
        y1 = h_orig - CROP_SIZE

    # Perform Crop
    crop = img[y1:y2, x1:x2]
    
    # Save to cropped_dataset maintaining folder structure
    dest_folder = os.path.join(OUTPUT_DIR, os.path.dirname(request.rel_path))
    os.makedirs(dest_folder, exist_ok=True)
    
    # Generate unique filename to allow multiple crops per image
    base_name = os.path.splitext(os.path.basename(request.rel_path))[0]
    unique_id = uuid.uuid4().hex[:6]
    dest_filename = f"{base_name}_crop_{unique_id}.jpg"
    dest_path = os.path.join(dest_folder, dest_filename)

    cv2.imwrite(dest_path, crop)
    
    # --- LINKING LOGIC ---
    # Find the corresponding DailyReading record
    # We look for a path that contains the rel_path. 
    # Usually image_path is "images/YYYY-MM-DD/Type/File.jpg"
    # request.rel_path is "YYYY-MM-DD/Type/File.jpg"
    search_path = f"images/{request.rel_path}"
    reading = db.query(models.DailyReading).filter(
        (models.DailyReading.image_path == search_path) | 
        (models.DailyReading.image_path == request.rel_path)
    ).first()

    if reading:
        # Save the crop link
        new_crop = models.ImageCrop(
            daily_reading_id=reading.id,
            crop_path=dest_path.replace("\\", "/") # Normalize for web/database
        )
        db.add(new_crop)
        db.commit()
    
    # Mark the original image as processed so the progress moves forward
    save_progress(request.rel_path, db)
    
    return {"status": "success", "saved_path": dest_path, "linked_reading_id": reading.id if reading else None}

@cropping_router.post("/skip")
def skip_image(request: SkipRequest, db: Session = Depends(get_db)):
    """Marks an image as processed without cropping it."""
    save_progress(request.rel_path, db)
    return {"status": "success", "message": f"Skipped {request.rel_path}"}

@cropping_router.post("/mark-done")
def mark_done(request: SkipRequest, db: Session = Depends(get_db)):
    """Explicitly move the progress pointer to this image."""
    save_progress(request.rel_path, db)
    return {"status": "success", "message": f"Progress updated to {request.rel_path}"}
