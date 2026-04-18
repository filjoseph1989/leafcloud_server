import os
import cv2
import numpy as np
import shutil

def is_macos_metadata(filename: str) -> bool:
    """Checks if a file is a macOS metadata file (starts with ._)."""
    return filename.startswith("._")

def delete_macos_metadata(directory: str) -> int:
    """
    Finds and deletes macOS metadata files (._*) in the specified directory.
    Returns the count of deleted files.
    """
    deleted_count = 0
    if not os.path.exists(directory):
        return 0
        
    for filename in os.listdir(directory):
        if is_macos_metadata(filename):
            file_path = os.path.join(directory, filename)
            try:
                os.remove(file_path)
                deleted_count += 1
            except OSError:
                pass
    return deleted_count

def is_corrupted_file(file_path: str, threshold: int) -> bool:
    """Checks if a file is corrupted (size smaller than threshold)."""
    try:
        return os.path.getsize(file_path) < threshold
    except OSError:
        return True

def delete_corrupted_files(directory: str, threshold: int) -> int:
    """
    Finds and deletes files smaller than the threshold in the specified directory.
    Returns the count of deleted files.
    """
    deleted_count = 0
    if not os.path.exists(directory):
        return 0
        
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path) and not is_macos_metadata(filename):
            if is_corrupted_file(file_path, threshold):
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except OSError:
                    pass
    return deleted_count

def calculate_greenness(image_path: str) -> float:
    """
    Calculates the percentage of green pixels in an image using HSV thresholding.
    Returns a value between 0.0 and 100.0.
    """
    img = cv2.imread(image_path)
    if img is None:
        return 0.0
    
    # Convert to HSV color space
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Define range for green color in HSV
    # These thresholds are typical for green plants
    lower_green = np.array([35, 40, 40])
    upper_green = np.array([85, 255, 255])
    
    # Threshold the HSV image to get only green colors
    mask = cv2.inRange(hsv, lower_green, upper_green)
    
    # Calculate percentage of green pixels
    green_pixels = cv2.countNonZero(mask)
    total_pixels = img.shape[0] * img.shape[1]
    
    if total_pixels == 0:
        return 0.0
        
    return (green_pixels / total_pixels) * 100.0

def is_mostly_green(image_path: str, threshold: float) -> bool:
    """Checks if an image has more green than the threshold percentage."""
    return calculate_greenness(image_path) >= threshold

def process_image_batch(directory: str, trash_dir: str, size_threshold: int, green_threshold: float) -> dict:
    """
    Processes a batch of images:
    - Deletes macOS metadata (._*)
    - Deletes corrupted files (size < threshold)
    - Moves non-green images to trash_dir
    - Keeps mostly green images
    Returns a dictionary of statistics.
    """
    stats = {
        "deleted_metadata": 0,
        "deleted_corrupted": 0,
        "moved_to_trash": 0,
        "kept": 0,
        "total_processed": 0
    }
    
    if not os.path.exists(directory):
        return stats
        
    if not os.path.exists(trash_dir):
        os.makedirs(trash_dir, exist_ok=True)
        
    for dirpath, _dirnames, filenames in os.walk(directory):
        # Skip the trash directory itself to avoid recursive processing
        if os.path.abspath(dirpath) == os.path.abspath(trash_dir):
            continue
            
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            
            stats["total_processed"] += 1
                
            # 1. macOS Metadata
            if is_macos_metadata(filename):
                try:
                    os.remove(file_path)
                    stats["deleted_metadata"] += 1
                except OSError:
                    pass
                continue
                
            # 2. Corrupted File
            if is_corrupted_file(file_path, size_threshold):
                try:
                    os.remove(file_path)
                    stats["deleted_corrupted"] += 1
                except OSError:
                    pass
                continue
                
            # 3. Greenness Test
            if is_mostly_green(file_path, green_threshold):
                stats["kept"] += 1
            else:
                try:
                    # Move to trash instead of permanent deletion
                    shutil.move(file_path, os.path.join(trash_dir, filename))
                    stats["moved_to_trash"] += 1
                except (OSError, shutil.Error):
                    pass
                
    return stats
