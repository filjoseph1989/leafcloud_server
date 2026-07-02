import os
import cv2
import numpy as np
import random
from typing import List, Tuple

def calculate_greenness(image_path: str) -> float:
    """
    Calculates the percentage of 'green' pixels in an image.
    Used to filter out crops that contain only water or background.
    """
    img = cv2.imread(image_path)
    if img is None:
        return 0.0
    
    # Convert to HSV color space
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Define green color range
    lower_green = np.array([35, 40, 40])
    upper_green = np.array([85, 255, 255])
    
    # Create mask and calculate percentage
    mask = cv2.inRange(hsv, lower_green, upper_green)
    green_pixels = np.count_nonzero(mask)
    total_pixels = img.shape[0] * img.shape[1]
    
    return (green_pixels / total_pixels) * 100

def get_crop_coordinates(w: int, h: int, size: int) -> List[Tuple[int, int, str]]:
    """
    Generates a list of (x, y, type) coordinates for cropping.
    Includes grid, edges, corners, and random samples.
    """
    coords = []
    
    # 1. Standard Grid
    for y in range(0, h - size + 1, size):
        for x in range(0, w - size + 1, size):
            coords.append((x, y, "grid"))
            
    # 2. Right-aligned edge
    if w > size:
        for y in range(0, h - size + 1, size):
            coords.append((w - size, y, "right_aligned"))
            
    # 3. Bottom-aligned edge
    if h > size:
        for x in range(0, w - size + 1, size):
            coords.append((x, h - size, "bottom_aligned"))
            
    # 4. Corner (Bottom-Right)
    if w > size and h > size:
        coords.append((w - size, h - size, "corner_aligned"))
        
    # 5. Random samples (3 per image)
    for _ in range(3):
        if w > size and h > size:
            rx = random.randint(0, w - size)
            ry = random.randint(0, h - size)
            coords.append((rx, ry, "random"))
        
    return coords

def delete_macos_metadata(directory: str) -> int:
    """
    Removes ._ (AppleDouble) files that cause issues with image processing.
    """
    deleted_count = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if file.startswith("._"):
                try:
                    os.remove(os.path.join(root, file))
                    deleted_count += 1
                except Exception:
                    pass
    return deleted_count

def get_sorted_images(source_dir: str) -> List[str]:
    """
    Returns a sorted list of relative paths to images in the source directory.
    """
    all_images = []
    for root, _, files in os.walk(source_dir):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                rel_path = os.path.relpath(os.path.join(root, file), source_dir)
                all_images.append(rel_path)
    return sorted(all_images)

def get_unavailable_images(db, include_additional: bool = False) -> List[str]:
    """
    Returns a list of image paths that are already fully processed in the database.
    """
    from app.models.crop_progress import ImageCropProgress
    query = db.query(ImageCropProgress.rel_path)
    if include_additional:
        query = query.filter(ImageCropProgress.is_processed == True, ImageCropProgress.additional_processed == True)
    else:
        query = query.filter(ImageCropProgress.is_processed == True)
    
    return [row[0] for row in query.all()]

def save_progress(rel_path: str, db, additional: bool = False):
    """
    Updates or creates a progress record for a physical image file.
    """
    from app.models.crop_progress import ImageCropProgress
    from sqlalchemy import func
    
    progress = db.query(ImageCropProgress).filter(ImageCropProgress.rel_path == rel_path).first()
    if not progress:
        progress = ImageCropProgress(rel_path=rel_path, is_processed=True)
        db.add(progress)
    else:
        progress.is_processed = True
        progress.last_updated = func.now()
        
    if additional:
        progress.additional_processed = True
        
    db.commit()
