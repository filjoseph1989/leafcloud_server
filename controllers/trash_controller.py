import os
import shutil
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, func

from database import get_db
import models
from schemas.trash import TrashScanResponse, TrashedCropResponse

trash_router = APIRouter(prefix="/api/v1/trash", tags=["Trash Review"])

# Note: We assume temp_trash is mounted as /temp_trash static file route in main.py
TRASH_URL_PREFIX = "/temp_trash"

@trash_router.get("/scan", response_model=TrashScanResponse)
def scan_trash(
    request: Request,
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Returns an image from the trash for review.
    Uses offset to allow 'sliding' back and forth.
    """
    base_url = str(request.base_url).rstrip("/")
    query = db.query(models.AutomatedActionLog).filter(
        models.AutomatedActionLog.reason == "low_greenness_crop",
        models.AutomatedActionLog.action_type == "move_to_trash"
    ).order_by(asc(models.AutomatedActionLog.id))

    total_count = query.count()
    log = query.offset(offset).first()
    
    if not log:
        return TrashScanResponse(image=None, total_count=total_count, current_index=offset)

    return TrashScanResponse(
        image=TrashedCropResponse(
            id=log.id,
            filename=log.filename,
            image_url=f"{base_url}{TRASH_URL_PREFIX}/{os.path.basename(log.current_path)}",
            metric_value=log.metric_value or 0.0,
            timestamp=log.timestamp,
            is_viewed=log.is_viewed,
            action_type=log.action_type
        ),
        total_count=total_count,
        current_index=offset
    )

@trash_router.get("/next", response_model=TrashScanResponse)
def get_next_unviewed(request: Request, db: Session = Depends(get_db)):
    """
    Finds the first image that hasn't been viewed yet and returns it with its index.
    This allows the app to 'resume' where it left off.
    """
    base_url = str(request.base_url).rstrip("/")
    
    # 1. Find all relevant IDs in order
    all_ids = db.query(models.AutomatedActionLog.id).filter(
        models.AutomatedActionLog.reason == "low_greenness_crop",
        models.AutomatedActionLog.action_type == "move_to_trash"
    ).order_by(asc(models.AutomatedActionLog.id)).all()
    
    id_list = [i[0] for i in all_ids]
    
    # 2. Find the first ID where is_viewed is False
    next_log = db.query(models.AutomatedActionLog).filter(
        models.AutomatedActionLog.reason == "low_greenness_crop",
        models.AutomatedActionLog.action_type == "move_to_trash",
        models.AutomatedActionLog.is_viewed == False
    ).order_by(asc(models.AutomatedActionLog.id)).first()
    
    if not next_log:
        return TrashScanResponse(image=None, total_count=len(id_list), current_index=0)
    
    # 3. Calculate the index (offset) of this ID
    try:
        current_index = id_list.index(next_log.id)
    except ValueError:
        current_index = 0

    return TrashScanResponse(
        image=TrashedCropResponse(
            id=next_log.id,
            filename=next_log.filename,
            image_url=f"{base_url}{TRASH_URL_PREFIX}/{os.path.basename(next_log.current_path)}",
            metric_value=next_log.metric_value or 0.0,
            timestamp=next_log.timestamp,
            is_viewed=next_log.is_viewed,
            action_type=next_log.action_type
        ),
        total_count=len(id_list),
        current_index=current_index
    )

@trash_router.post("/{log_id}/viewed")
def mark_as_viewed(log_id: int, db: Session = Depends(get_db)):
    log = db.query(models.AutomatedActionLog).filter(models.AutomatedActionLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    log.is_viewed = True
    db.commit()
    return {"status": "success"}

@trash_router.post("/{log_id}/restore")
def restore_trash_item(log_id: int, db: Session = Depends(get_db)):
    log = db.query(models.AutomatedActionLog).filter(models.AutomatedActionLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    
    if log.action_type == "restored":
        return {"status": "already_restored"}

    # Get project root (parent of controllers folder)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    current_abs = os.path.join(base_dir, log.current_path)
    original_abs = os.path.join(base_dir, log.original_path)

    if not os.path.exists(current_abs):
        raise HTTPException(status_code=404, detail=f"File missing: {log.current_path}")

    try:
        os.makedirs(os.path.dirname(original_abs), exist_ok=True)
        shutil.move(current_abs, original_abs)
        log.action_type = "restored"
        db.commit()
        return {"status": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
