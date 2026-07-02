import os
import subprocess
import json
import fcntl
import time
from typing import Optional

DEFAULT_OUTPUT_PATH = "plant_snapshot.jpg"
PAYLOAD_FILE = "payload.json"

class CameraCapture:
    """
    A class to capture still images from a Raspberry Pi Camera.
    Handles compatibility between modern rpicam-apps (libcamera) and legacy raspistill.
    """
    def __init__(self, output_path: str = DEFAULT_OUTPUT_PATH):
        self.output_path = output_path

    def capture_image(self, width: int = 1280, height: int = 960) -> bool:
        """
        Captures a still image and saves it to the output path.
        Automatically detects and uses the available camera command.
        """
        # Define command suites in order of preference (modern to legacy)
        commands = [
            # 1. Modern Raspberry Pi OS (Bookworm/Bullseye with libcamera)
            f"rpicam-still -t 1000 -o {self.output_path} --width {width} --height {height}",
            # 2. Alternative libcamera command
            f"libcamera-still -t 1000 -o {self.output_path} --width {width} --height {height}",
            # 3. Legacy Raspberry Pi OS command
            f"raspistill -t 1000 -o {self.output_path} -w {width} -h {height}"
        ]

        print(f"📸 Initiating camera capture (Target: {self.output_path})...")
        
        for cmd in commands:
            cmd_name = cmd.split()[0]
            # Check if command is available in system PATH
            if subprocess.call(f"type {cmd_name}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                try:
                    print(f"⚙️ Running command: {cmd}")
                    # Run capture command with a 10-second timeout
                    result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10.0)
                    if os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
                        print(f"✅ Image successfully captured and saved to {self.output_path}")
                        return True
                except subprocess.TimeoutExpired:
                    print(f"⚠️ Command '{cmd_name}' timed out.")
                except subprocess.CalledProcessError as e:
                    print(f"⚠️ Command '{cmd_name}' failed with error: {e.stderr.strip()}")
                except Exception as e:
                    print(f"⚠️ Unexpected error with '{cmd_name}': {e}")
            else:
                print(f"🔍 Command '{cmd_name}' not available on this system.")

        print("❌ Failed to capture image. No compatible camera tools found.")
        return False

if __name__ == "__main__":
    print("📸 Starting Continuous Camera Still Capture...")
    capture = CameraCapture()
    
    try:
        while True:
            # Check if "image_path" is already in payload.json
            image_path_present = False
            
            try:
                with open(PAYLOAD_FILE, "a+") as f:
                    fcntl.flock(f, fcntl.LOCK_EX)
                    f.seek(0)
                    content = f.read()
                    payload = {}
                    if content.strip():
                        try:
                            payload = json.loads(content)
                        except Exception as e:
                            print(f"⚠️ Error parsing {PAYLOAD_FILE}: {e}")
                    
                    if "image_path" in payload:
                        image_path_present = True
                    fcntl.flock(f, fcntl.LOCK_UN)
            except Exception as e:
                print(f"❌ Error checking {PAYLOAD_FILE}: {e}")

            if not image_path_present:
                print("📸 'image_path' is missing in payload. Capturing new image...")
                # Capture the image (lock is released so it won't block other scripts)
                success = capture.capture_image()
                
                if success:
                    # Safely save the image path in payload.json
                    try:
                        with open(PAYLOAD_FILE, "a+") as f:
                            # Acquire exclusive lock
                            fcntl.flock(f, fcntl.LOCK_EX)
                            
                            f.seek(0)
                            content = f.read()
                            payload = {}
                            if content.strip():
                                try:
                                    payload = json.loads(content)
                                except Exception as e:
                                    print(f"⚠️ Error parsing {PAYLOAD_FILE}: {e}")
                                    
                            if "image_path" not in payload:
                                payload["image_path"] = os.path.abspath(capture.output_path)
                                f.seek(0)
                                f.truncate()
                                json.dump(payload, f, indent=4)
                                print(f"💾 Saved image path '{payload['image_path']}' to {PAYLOAD_FILE}")
                                
                            # Release lock
                            fcntl.flock(f, fcntl.LOCK_UN)
                    except Exception as e:
                        print(f"❌ Failed to safely update {PAYLOAD_FILE}: {e}")
                else:
                    print("❌ Could not capture image. Retrying next cycle.")
            
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("\n👋 Exiting Camera Still Capture loop.")
