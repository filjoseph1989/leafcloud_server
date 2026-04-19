import os
import shutil
import anyio
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
import models
import image_filtering
from schemas.images import PreFilterRequest, RestoreRequest, TrashItemResponse

# Router for image administrative actions
images_router = APIRouter(prefix="/api/v1/images", tags=["Images Admin"])

@images_router.get("/trash", response_model=list[TrashItemResponse])
def get_trashed_images(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Returns a list of images that were moved to trash by automated processes.
    Sorted by timestamp (newest first).
    """
    # Enforce maximum limit
    if limit > 100:
        limit = 100
        
    query = db.query(models.AutomatedActionLog)\
        .filter(models.AutomatedActionLog.action_type == "move_to_trash")\
        .order_by(models.AutomatedActionLog.timestamp.desc())
        
    items = query.offset(skip).limit(limit).all()
    return items

@images_router.post("/pre-filter")
async def pre_filter_images(request: PreFilterRequest, db: Session = Depends(get_db)):
    """
    Triggers the automated pre-filtering process for images.
    - Deletes metadata
    - Deletes corrupted files
    - Moves non-green images to temp_trash
    """
    print(f"📡 API REQUEST: Image Pre-Filtering (size={request.size_threshold}, green={request.green_threshold})")
    
    image_dir = "images"
    trash_dir = os.path.join(image_dir, "temp_trash")
    
    # Run heavy processing in a separate thread to avoid blocking FastAPI
    try:
        stats = await anyio.to_thread.run_sync(
            image_filtering.process_image_batch,
            image_dir,
            trash_dir,
            request.size_threshold,
            request.green_threshold,
            db
        )
        print(f"✅ PRE-FILTER COMPLETE: {stats}")
        return {"status": "success", "stats": stats}
    except Exception as e:
        print(f"❌ PRE-FILTER ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@images_router.post("/restore")
async def restore_images(
    request: RestoreRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Restores images from temp_trash to their original location based on log entries.
    """
    # 1. Auth Check
    if authorization != "demo-access-token-xyz-789":
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 2. Fetch all requested logs
    logs = db.query(models.AutomatedActionLog).filter(models.AutomatedActionLog.id.in_(request.log_ids)).all()
    
    if len(logs) != len(request.log_ids):
        found_ids = [l.id for l in logs]
        missing_ids = list(set(request.log_ids) - set(found_ids))
        raise HTTPException(status_code=400, detail=f"Some log IDs not found: {missing_ids}")

    # 3. Pre-flight check: Ensure all files exist in current_path
    for log in logs:
        if not os.path.exists(log.current_path):
            raise HTTPException(status_code=400, detail=f"File {log.filename} (ID {log.id}) not found in trash: {log.current_path}")

    # 4. Perform restoration
    restored_count = 0
    try:
        for log in logs:
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(log.original_path), exist_ok=True)
            
            # Move file back
            shutil.move(log.current_path, log.original_path)
            
            # Delete log entry
            db.delete(log)
            restored_count += 1
            
        db.commit()
        print(f"♻️ Restored {restored_count} images from trash.")
        return {"status": "success", "message": f"Restored {restored_count} images", "restored_count": restored_count}
        
    except Exception as e:
        db.rollback()
        print(f"❌ RESTORE ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Restoration failed: {str(e)}")

@images_router.delete("/{filename:path}")
def delete_image(
    filename: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Deletes an image from the filesystem and removes its metadata from the DB if present.
    """
    # 1. Authentication Check
    if authorization != "demo-access-token-xyz-789":
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 2. Cleanup filename (handle optional 'images/' prefix from URL)
    clean_filename = filename.lstrip("/").replace("images/", "")

    # 3. Path Traversal Protection & Existence Check
    image_dir = "images"
    if "/" in clean_filename or "\\" in clean_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = os.path.join(image_dir, clean_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Image {clean_filename} not found on disk")

    # 4. Database Cleanup (if record exists)
    reading = db.query(models.DailyReading).filter(models.DailyReading.image_path.like(f"%{clean_filename}")).first()

    if reading:
        db.query(models.NPKPrediction).filter(models.NPKPrediction.daily_reading_id == reading.id).delete()
        db.delete(reading)
        db.commit()
        print(f"🗑️ Deleted DB record for reading ID: {reading.id}")

    # 5. Filesystem Deletion
    try:
        os.remove(file_path)
        print(f"🗑️ Deleted file from disk: {file_path}")
    except Exception as e:
        print(f"❌ Failed to delete file: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting file: {str(e)}")

    return {"status": "success", "message": f"Image {clean_filename} and associated data deleted"}
