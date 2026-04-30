import os
import shutil
import uuid
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from image_filtering import calculate_greenness

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CROPPED_DIR = os.path.join(BASE_DIR, "cropped_dataset")
TRASH_DIR = os.path.join(CROPPED_DIR, "temp_trash")
GREEN_THRESHOLD = 5.0  # Percentage of green pixels required

def filter_crops():
    db = SessionLocal()
    try:
        print(f"--- STARTING CROP FILTERING (Threshold: {GREEN_THRESHOLD}%) ---")
        
        if not os.path.exists(TRASH_DIR):
            os.makedirs(TRASH_DIR, exist_ok=True)
            print(f"Created trash directory: {TRASH_DIR}")

        processed_count = 0
        moved_count = 0
        error_count = 0

        # Walk through cropped_dataset
        for root, dirs, files in os.walk(CROPPED_DIR):
            # Skip the trash directory itself
            if os.path.abspath(root) == os.path.abspath(TRASH_DIR):
                continue
            
            for filename in files:
                if not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    continue
                
                processed_count += 1
                file_path = os.path.join(root, filename)
                
                try:
                    greenness = calculate_greenness(file_path)
                    
                    if greenness < GREEN_THRESHOLD:
                        # Move to trash
                        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
                        dest_path = os.path.join(TRASH_DIR, unique_filename)
                        
                        shutil.move(file_path, dest_path)
                        moved_count += 1
                        
                        # Log to database
                        log = models.AutomatedActionLog(
                            filename=filename,
                            original_path=os.path.relpath(file_path, BASE_DIR).replace("\\", "/"),
                            current_path=os.path.relpath(dest_path, BASE_DIR).replace("\\", "/"),
                            action_type="move_to_trash",
                            reason="low_greenness_crop",
                            metric_value=greenness
                        )
                        db.add(log)
                        
                        if moved_count % 50 == 0:
                            print(f"Progress: {processed_count} processed, {moved_count} moved...")
                            db.commit()
                            
                except Exception as e:
                    # Don't print every EIO error if the drive is still flaky, but log it
                    error_count += 1
                    continue

        db.commit()
        print(f"\n--- FILTERING COMPLETE ---")
        print(f"Total processed: {processed_count}")
        print(f"Moved to trash:  {moved_count}")
        print(f"Errors:          {error_count}")

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    filter_crops()
