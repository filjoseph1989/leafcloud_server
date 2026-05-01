import os
import shutil
import anyio
import uuid
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import Optional

from database import get_db
import models
import image_filtering
from schemas.images import PreFilterRequest, RestoreRequest, TrashItemResponse, ImageInfo

# Router for image administrative actions
images_router = APIRouter(prefix="/api/v1/images", tags=["Images Admin"])

@images_router.get("/", response_model=list[ImageInfo])
def list_images(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Returns a list of images from the images/ directory,
    synced with database metadata from DailyReading.
    """
    image_dir = "images"
    if not os.path.exists(image_dir):
        return []

    # 1. Get all image files from disk recursively
    files = []
    for root, _, filenames in os.walk(image_dir):
        for f in filenames:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')) and "temp_trash" not in root:
                # Store relative path from images/
                rel_path = os.path.relpath(os.path.join(root, f), image_dir)
                files.append(rel_path)
    
    # Sort by filename (which includes timestamp)
    files.sort(reverse=True)

    # Apply pagination to file list
    paginated_files = files[skip : skip + limit]

    # 2. Query DB for these specific files
    readings_map = {}
    
    if paginated_files:
        # Optimization: SQLite has a limit on expression depth (OR/IN clauses)
        # We chunk the files to avoid "Expression tree is too large" error
        CHUNK_SIZE = 100
        all_matching_readings = []
        for i in range(0, len(paginated_files), CHUNK_SIZE):
            chunk = paginated_files[i:i + CHUNK_SIZE]
            filters = [models.DailyReading.image_path.like(f"%{f}%") for f in chunk]
            chunk_readings = db.query(models.DailyReading)\
                .options(joinedload(models.DailyReading.experiment))\
                .filter(or_(*filters))\
                .all()
            all_matching_readings.extend(chunk_readings)

        for r in all_matching_readings:
            for f in paginated_files:
                if f in r.image_path:
                    readings_map[f] = r

    results = []
    for filename in paginated_files:
        reading = readings_map.get(filename)
        if reading:
            results.append(ImageInfo(
                filename=filename,
                reading_id=reading.id,
                timestamp=reading.timestamp,
                image_url=f"/images/{filename}",
                is_orphaned=False,
                bucket_label=reading.experiment.bucket_label if reading.experiment else None
            ))
        else:
            results.append(ImageInfo(
                filename=filename,
                image_url=f"/images/{filename}",
                is_orphaned=True
            ))

    return results

@images_router.get("/trash", response_model=list[TrashItemResponse])
def get_trashed_images(
    skip: int = 0,
    limit: int = 50,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Returns a list of images that were moved to trash by automated processes.
    
    Args:
        skip (int): Number of items to skip for pagination.
        limit (int): Maximum number of items to return (capped at 100).
        authorization (str): Auth token.
        db (Session): Database session.

    Returns:
        List[TrashItemResponse]: List of trashed image metadata.
    """
    # 1. Auth Check
    if authorization != "demo-access-token-xyz-789":
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 2. Enforce maximum limit
    if limit > 100:
        limit = 100
        
    query = db.query(models.AutomatedActionLog)\
        .filter(models.AutomatedActionLog.action_type == "move_to_trash")\
        .order_by(models.AutomatedActionLog.timestamp.desc())
        
    items = query.offset(skip).limit(limit).all()
    
    # Manually populate image_url for each item
    for item in items:
        # Map current_path to a web-accessible URL
        # e.g., 'images/temp_trash/file.jpg' -> '/images/temp_trash/file.jpg'
        if item.current_path:
            item.image_url = f"/{item.current_path.replace('\\', '/')}"
            
    return items

@images_router.post("/pre-filter")
async def pre_filter_images(request: PreFilterRequest, db: Session = Depends(get_db)):
    """
    Triggers the automated pre-filtering process for images.
    
    The process deletes metadata for corrupt files and moves images with low greenness 
    to a temporary trash directory.

    Args:
        request (PreFilterRequest): Filtering thresholds (size and greenness).
        db (Session): Database session.

    Returns:
        dict: Status message and processing statistics.
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

    Args:
        request (RestoreRequest): List of log IDs to restore.
        authorization (str): Auth token.
        db (Session): Database session.

    Returns:
        dict: Status message and count of restored images.
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

    # 4. Define the synchronous blocking task for restoration
    def perform_restore(logs_list):
        restored_count = 0
        for log in logs_list:
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(log.original_path), exist_ok=True)
            
            # Move file back
            shutil.move(log.current_path, log.original_path)
            
            # Delete log entry
            db.delete(log)
            restored_count += 1
        return restored_count

    # 5. Run restoration in a separate thread to avoid blocking
    try:
        restored_count = await anyio.to_thread.run_sync(perform_restore, logs)
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
    Moves an image to temp_trash and marks its DB record as deleted.

    Args:
        filename (str): The filename or path of the image to delete.
        authorization (str): Auth token.
        db (Session): Database session.

    Returns:
        dict: Success message.
    """
    # 1. Authentication Check
    if authorization != "demo-access-token-xyz-789":
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 2. Cleanup filename (handle optional 'images/' prefix from URL)
    clean_filename = filename.lstrip("/").replace("images/", "")

    # 3. Path Traversal Protection & Existence Check
    image_dir = "images"
    trash_dir = os.path.join(image_dir, "temp_trash")

    # Resolve absolute paths to prevent traversal
    abs_image_dir = os.path.abspath(image_dir)
    file_path = os.path.abspath(os.path.join(image_dir, clean_filename))

    if not file_path.startswith(abs_image_dir):
        raise HTTPException(status_code=400, detail="Invalid filename or path traversal attempt")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Image {clean_filename} not found on disk")

    # 4. Database Soft Cleanup (if record exists)
    reading = db.query(models.DailyReading).filter(models.DailyReading.image_path.like(f"%{clean_filename}")).first()

    if reading:
        reading.status = "deleted"
        print(f"♻️ Marked DB record as deleted for reading ID: {reading.id}")

    # 5. Filesystem Move to Trash
    try:
        unique_filename = f"{uuid.uuid4().hex}_{clean_filename}"
        dest_path = os.path.join(trash_dir, unique_filename)
        
        # Ensure the destination directory exists (for subdirectories)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        shutil.move(file_path, dest_path)
        
        # Log the action
        log = models.AutomatedActionLog(
            filename=clean_filename,
            original_path=file_path,
            current_path=dest_path,
            action_type="move_to_trash",
            reason="api_requested_delete"
        )
        db.add(log)
        db.commit()
        print(f"🗑️ Moved file to trash: {dest_path}")
    except Exception as e:
        db.rollback()
        print(f"❌ Failed to move file to trash: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing deletion: {str(e)}")

    return {"status": "success", "message": f"Image {clean_filename} moved to trash and records updated"}
