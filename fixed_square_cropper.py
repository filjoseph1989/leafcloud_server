import os
import cv2
import numpy as np

# --- CONFIGURATION ---
SOURCE_DIR = "images"
OUTPUT_DIR = "cropped_dataset"
CROP_SIZE = 224  # Fixed size, dili na mausab

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

def process_images():
    global crop_confirmed, current_mouse
    
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    cv2.namedWindow("Fixed 224x224 Cropper", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Fixed 224x224 Cropper", 1000, 800)
    cv2.setMouseCallback("Fixed 224x224 Cropper", mouse_handler)

    extensions = ('.jpg', '.jpeg', '.png')
    
    for root, dirs, files in os.walk(SOURCE_DIR):
        if "temp_trash" in root or OUTPUT_DIR in root:
            continue

        for filename in files:
            if not filename.lower().endswith(extensions):
                continue

            img_path = os.path.join(root, filename)
            rel_path = os.path.relpath(root, SOURCE_DIR)
            dest_folder = os.path.join(OUTPUT_DIR, rel_path)
            dest_path = os.path.join(dest_folder, filename)

            if os.path.exists(dest_path):
                continue

            img = cv2.imread(img_path)
            if img is None: continue
            
            h, w = img.shape[:2]
            print(f"🖼️  Processing: {filename}")

            while True:
                display_img = img.copy()
                mx, my = current_mouse
                
                # Kalkulasyon para ang mouse maoy mahimong CENTER sa 224x224 box
                x1 = max(0, mx - CROP_SIZE // 2)
                y1 = max(0, my - CROP_SIZE // 2)
                x2 = x1 + CROP_SIZE
                y2 = y1 + CROP_SIZE
                
                # I-adjust kung mulapas sa image boundary
                if x2 > w:
                    x2 = w
                    x1 = w - CROP_SIZE
                if y2 > h:
                    y2 = h
                    y1 = h - CROP_SIZE

                # I-draw ang preview square
                color = (0, 255, 0) if is_dragging else (0, 255, 255)
                cv2.rectangle(display_img, (x1, y1), (x2, y2), color, 2)
                cv2.putText(display_img, "DRAG & RELEASE TO CUT", (x1, y1-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                cv2.imshow("Fixed 224x224 Cropper", display_img)
                key = cv2.waitKey(1) & 0xFF

                if crop_confirmed:
                    # Pag-cut sa eksaktong 224x224 area
                    crop = img[y1:y2, x1:x2]
                    
                    os.makedirs(dest_folder, exist_ok=True)
                    cv2.imwrite(dest_path, crop)
                    print(f"✅ Cut Saved: {dest_path}")
                    crop_confirmed = False
                    break

                if key == ord('s'): # Skip
                    print("⏩ Skipped.")
                    break
                if key == ord('q'): # Quit
                    print("🛑 Quitting...")
                    return

    cv2.destroyAllWindows()
    print("🏁 All images processed!")

if __name__ == "__main__":
    process_images()
