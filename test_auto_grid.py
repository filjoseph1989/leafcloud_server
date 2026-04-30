
import os
import cv2
import numpy as np
from database import SessionLocal
import models
from controllers.cropping_controller import auto_grid_crop
from schemas.cropping import SkipRequest

# 1. Setup - Create a dummy image (e.g., 500x500)
# 500x500 should produce (2 steps in Y) * (2 steps in X) = 4 crops of 224x224
# Calculation: floor((500-224)/224) + 1 = 1 + 1 = 2
TEST_DIR = "images/test_grid"
os.makedirs(TEST_DIR, exist_ok=True)

img_path = os.path.join(TEST_DIR, "grid_test_image.jpg")
dummy_img = np.zeros((500, 500, 3), np.uint8)
cv2.putText(dummy_img, "TOP LEFT", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
cv2.putText(dummy_img, "BOTTOM RIGHT", (250, 450), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
cv2.imwrite(img_path, dummy_img)

rel_path = os.path.relpath(img_path, "images").replace("\\", "/")

print(f"--- STARTING AUTO-GRID TEST ---")
print(f"Created test image: {rel_path} (500x500)")

db = SessionLocal()

try:
    # 2. Run Auto-Grid
    request = SkipRequest(rel_path=rel_path)
    result = auto_grid_crop(request, db)
    
    print(f"Result: {result}")
    
    # 3. Verify files on disk
    output_subdir = os.path.join("cropped_dataset", "test_grid")
    if os.path.exists(output_subdir):
        files = os.listdir(output_subdir)
        print(f"Files created in {output_subdir}: {len(files)}")
        for f in files:
            print(f" - {f}")
            
        if len(files) == 4:
            print("\n✅ SUCCESS: Correct number of grid crops created!")
        else:
            print(f"\n❌ FAILURE: Expected 4 crops, but got {len(files)}.")
    else:
        print("\n❌ FAILURE: Output directory not found!")

finally:
    # 4. Cleanup
    print("\n--- CLEANING UP ---")
    # Delete database records
    db.query(models.ImageCropProgress).filter(models.ImageCropProgress.rel_path == rel_path).delete()
    db.commit()
    db.close()
    
    # Delete test files
    if os.path.exists(img_path): os.remove(img_path)
    if os.path.exists(TEST_DIR): os.rmdir(TEST_DIR)
    
    # Clean output folder
    import shutil
    if os.path.exists(output_subdir):
        shutil.rmtree(output_subdir)
        
    print("Test data cleaned up.")
