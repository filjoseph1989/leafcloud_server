import os
import cv2
import numpy as np

# --- CONFIGURATION ---
SOURCE_DIR = "images"
OUTPUT_DIR = "cropped_dataset"
CROP_SIZE = 224
PROGRESS_FILE = "crop_progress.txt"

# Global variables
current_mouse = (0, 0)
is_dragging = False
crop_confirmed = False

def mouse_handler(event, x, y, flags, param):
    global current_mouse, is_dragging, crop_confirmed
    if event == cv2.EVENT_LBUTTONDOWN:
        is_dragging = True
        current_mouse = (x, y)
    elif event == cv2.EVENT_MOUSEMOVE:
        current_mouse = (x, y)
    elif event == cv2.EVENT_LBUTTONUP:
        is_dragging = False
        current_mouse = (x, y)
        crop_confirmed = True

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            return f.read().strip().replace("\\", "/")
    return None

def save_progress(rel_path):
    with open(PROGRESS_FILE, "w") as f:
        f.write(rel_path.replace("\\", "/"))

def process_images():
    global crop_confirmed, current_mouse
    
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    last_processed_path = load_progress()
    found_last = False if last_processed_path else True

    window_name = "Multi-Crop 224x224"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1000, 800)
    cv2.setMouseCallback(window_name, mouse_handler)

    extensions = ('.jpg', '.jpeg', '.png')
    
    # 1. Collect all files with their relative paths
    all_files = []
    for root, dirs, files in os.walk(SOURCE_DIR):
        if "temp_trash" in root or OUTPUT_DIR in root: continue
        for f in files:
            if f.lower().endswith(extensions):
                full_path = os.path.join(root, f)
                # Create a normalized relative path for sorting and tracking
                rel_path = os.path.relpath(full_path, SOURCE_DIR).replace("\\", "/")
                all_files.append((root, f, rel_path))

    # 2. SORT the list to ensure chronological order (YYYY-MM-DD/Type/File)
    all_files.sort(key=lambda x: x[2]) 

    if not all_files:
        print("❌ No images found in the 'images' folder.")
        return

    if last_processed_path:
        print(f"🔄 Resuming after last processed: {last_processed_path}")
    else:
        print("🚀 Starting from the first image in chronological order.")

    for i, (root, filename, rel_path) in enumerate(all_files):
        # 3. RESUME LOGIC using the relative path
        if not found_last:
            if rel_path == last_processed_path:
                found_last = True
                continue
            else:
                continue

        img_path = os.path.join(root, filename)
        img = cv2.imread(img_path)
        if img is None: continue
        
        h, w = img.shape[:2]
        crop_count = 0
        print(f"\n🖼️  [{i+1}/{len(all_files)}] Path: {rel_path}")
        print("   [INSTRUCTIONS]")
        print("   - DRAG & RELEASE mouse to crop")
        print("   - Press 'N' for NEXT image (saves progress)")
        print("   - Press 'Q' to QUIT")

        while True:
            try:
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    return
            except: return

            display_img = img.copy()
            mx, my = current_mouse
            
            x1 = max(0, mx - CROP_SIZE // 2)
            y1 = max(0, my - CROP_SIZE // 2)
            x2 = x1 + CROP_SIZE
            y2 = y1 + CROP_SIZE
            
            if x2 > w: x2 = w; x1 = w - CROP_SIZE
            if y2 > h: y2 = h; y1 = h - CROP_SIZE

            color = (0, 255, 0) if is_dragging else (0, 0, 255)
            cv2.rectangle(display_img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(display_img, f"Crops: {crop_count} | {rel_path}", (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            cv2.imshow(window_name, display_img)
            key = cv2.waitKey(30) & 0xFF

            if crop_confirmed:
                crop = img[y1:y2, x1:x2]
                crop_count += 1
                base_name = os.path.splitext(filename)[0]
                ext = os.path.splitext(filename)[1]
                new_filename = f"{base_name}_crop{crop_count}{ext}"
                
                # Maintain the same folder structure in the output
                dest_folder = os.path.join(OUTPUT_DIR, os.path.dirname(rel_path))
                dest_path = os.path.join(dest_folder, new_filename)
                
                os.makedirs(dest_folder, exist_ok=True)
                cv2.imwrite(dest_path, crop)
                print(f"   ✅ Saved Crop #{crop_count}: {new_filename}")
                crop_confirmed = False

            if key == ord('n') or key == ord('N'): 
                save_progress(rel_path)
                break
            if key == ord('q') or key == ord('Q'): 
                print("🛑 Quitting...")
                cv2.destroyAllWindows()
                return

    cv2.destroyAllWindows()
    print("🏁 Finished all images!")

if __name__ == "__main__":
    process_images()
