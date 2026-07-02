import os
import sys
import time
import json
import fcntl
import subprocess
import threading
import signal
import requests
from typing import Dict
from discovery_client import discover_server

PAYLOAD_FILE = "payload.json"
# Dictionary of long-running background daemon scripts
BACKGROUND_SERVICES = {
    "EC Reader": "ec_reader.py",
    "pH Reader": "ph_reader.py",
    "Temp Reader": "temp_reader.py",
    "Camera Capture": "camera_capture.py",
    "EC Calibration": "ec_calibration.py",
    "pH Calibration": "ph_calibration.py"
}

class Orchestrator:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.threads = []
        self.running = True
        self.server_url = None
        self.last_upload_time = 0
        self.suspended_services = set()
        self.latest_telemetry = {"ph": None, "ec": None, "temperature": None}
        self.last_telemetry_send_time = 0
        self.telemetry_interval = 3.0 # Send telemetry every 3 seconds

    def discover_leafcloud_server(self) -> str:
        """Finds the server URL via Zeroconf or falls back to localhost."""
        print("🔍 [Orchestrator] Searching for LeafCloud Server...")
        url = discover_server(timeout=15)
        if url:
            print(f"📡 [Orchestrator] Found Server at: {url}")
            return url
        print("⚠️ [Orchestrator] Discovery failed. Defaulting to http://localhost:8000")
        return "http://localhost:8000"

    def log_streamer(self, name: str, proc: subprocess.Popen):
        """Pipes stdout/stderr from a subprocess and prefixes it with the process name."""
        try:
            for line in iter(proc.stdout.readline, ''):
                if not self.running:
                    break
                if line:
                    print(f"[{name}] {line.strip()}")
        except Exception:
            pass

    def start_service(self, name: str, script_name: str):
        """Starts a background Python script and launches a monitoring/logging thread."""
        script_path = os.path.join(os.path.dirname(__file__), script_name)
        print(f"🚀 [Orchestrator] Starting background service: {name} ({script_name})...")
        
        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        self.processes[name] = proc
        
        t = threading.Thread(target=self.log_streamer, args=(name, proc), daemon=True)
        t.start()
        self.threads.append(t)

    def stop_all_services(self):
        """Gracefully terminates all running background processes."""
        self.running = False
        print("\n🛑 [Orchestrator] Stopping all background services...")
        for name, proc in self.processes.items():
            if proc.poll() is None:
                print(f"⌛ [Orchestrator] Terminating {name}...")
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("✅ [Orchestrator] Cleanup finished.")

    def load_local_settings(self) -> dict:
        """Helper to safely load settings from local_settings.json."""
        settings_file = os.path.join(os.path.dirname(__file__), "local_settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ [Orchestrator] Error reading local settings: {e}")
        return {}

    def resolve_tank_config(self) -> tuple:
        """
        Resolves the target tank ID and upload interval (in seconds)
        based on server configurations (highest priority) and local_settings.json.
        Returns a tuple of (tank_id, upload_interval_seconds).
        """
        server_tank_id = None
        server_interval = None

        # 1. Try to fetch from server first (highest priority)
        url = f"{self.server_url}/api/v1/tank-configs/"
        try:
            response = requests.get(url, timeout=5.0)
            if response.status_code == 200:
                configs = response.json()
                local_settings = self.load_local_settings()
                local_tank_id = local_settings.get("tank_id")
                
                target_config = None
                if local_tank_id is not None:
                    # Match by local tank_id
                    for config in configs:
                        if config.get("id") == int(local_tank_id):
                            target_config = config
                            break
                
                if target_config is None:
                    # Fall back to finding the active tank
                    for config in configs:
                        if config.get("is_active") is True:
                            target_config = config
                            break
                
                if target_config:
                    server_tank_id = target_config.get("id")
                    server_interval = target_config.get("upload_interval_seconds")
        except Exception as e:
            print(f"⚠️ [Orchestrator] Failed to fetch tank configs from server: {e}")

        # 2. Load from local settings
        local_settings = self.load_local_settings()
        local_tank_id = local_settings.get("tank_id")
        local_interval = local_settings.get("upload_interval_seconds")

        # Resolve tank_id: server (highest) -> local -> fallback 1
        final_tank_id = 1
        if server_tank_id is not None:
            final_tank_id = int(server_tank_id)
        elif local_tank_id is not None:
            final_tank_id = int(local_tank_id)

        # Resolve upload_interval_seconds: server (highest) -> local -> fallback 60
        final_interval = 60
        if server_interval is not None:
            final_interval = int(server_interval)
        elif local_interval is not None:
            final_interval = int(local_interval)

        return final_tank_id, final_interval

    def check_and_upload_payload(self):
        """Safely inspects payload.json, uploads telemetry, and uploads daily readings when cooldown has elapsed."""
        if not os.path.exists(PAYLOAD_FILE):
            return

        try:
            # 1. Check payload.json for new sensor data
            telemetry_updated = False
            with open(PAYLOAD_FILE, "a+") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.seek(0)
                content = f.read()
                payload = {}
                if content.strip():
                    try:
                        payload = json.loads(content)
                    except Exception as e:
                        print(f"⚠️ [Orchestrator] Error parsing {PAYLOAD_FILE}: {e}")
                        fcntl.flock(f, fcntl.LOCK_UN)
                        return

                # Update local cache and clear sensor keys so reader scripts can write new values
                for key, cache_key in [("ph", "ph"), ("ec", "ec"), ("temperature", "temperature")]:
                    if key in payload:
                        self.latest_telemetry[cache_key] = payload[key]
                        payload.pop(key)
                        telemetry_updated = True

                if telemetry_updated:
                    f.seek(0)
                    f.truncate()
                    json.dump(payload, f, indent=4)
                
                fcntl.flock(f, fcntl.LOCK_UN)

            # 2. Upload telemetry to the server
            current_time = time.time()
            active_tank_id, upload_interval = self.resolve_tank_config()

            if telemetry_updated or (current_time - self.last_telemetry_send_time >= self.telemetry_interval):
                if any(v is not None for v in self.latest_telemetry.values()):
                    telemetry_payload = {
                        "tank_id": active_tank_id,
                        "ph": self.latest_telemetry["ph"],
                        "ec": self.latest_telemetry["ec"],
                        "water_temp": self.latest_telemetry["temperature"]
                    }
                    try:
                        telemetry_url = f"{self.server_url}/api/v1/iot/telemetry"
                        response = requests.post(telemetry_url, json=telemetry_payload, timeout=5.0)
                        if response.status_code == 200:
                            self.last_telemetry_send_time = current_time
                            if not hasattr(self, "_last_telemetry_print") or current_time - self._last_telemetry_print >= 10:
                                print(f"📡 [Orchestrator] Telemetry updated: pH={self.latest_telemetry['ph']}, EC={self.latest_telemetry['ec']}, Temp={self.latest_telemetry['temperature']}°C")
                                self._last_telemetry_print = current_time
                        else:
                            print(f"❌ [Orchestrator] Telemetry post failed (Status {response.status_code}): {response.text}")
                    except Exception as e:
                        print(f"⚠️ [Orchestrator] Failed to send telemetry: {e}")

            # 3. Handle Full Daily Upload (with image if camera is enabled)
            local_settings = self.load_local_settings()
            enable_camera = local_settings.get("enable_camera", True)

            image_path = None
            if enable_camera:
                try:
                    with open(PAYLOAD_FILE, "a+") as f:
                        fcntl.flock(f, fcntl.LOCK_EX)
                        f.seek(0)
                        content = f.read()
                        if content.strip():
                            try:
                                payload = json.loads(content)
                                image_path = payload.get("image_path")
                            except Exception:
                                pass
                        fcntl.flock(f, fcntl.LOCK_UN)
                except Exception:
                    pass

            # Determine if we should perform the history upload
            should_upload = False
            if enable_camera:
                if image_path:
                    should_upload = True
            else:
                # Timer-driven history logging when camera is disabled
                if current_time - self.last_upload_time >= upload_interval:
                    should_upload = True

            if should_upload:
                # Check calibration status from the server
                is_calibrating = False
                calibrating_sensors = []
                try:
                    calib_url = f"{self.server_url}/api/v1/calibration/"
                    calib_response = requests.get(calib_url, timeout=3.0)
                    if calib_response.status_code == 200:
                        for cal in calib_response.json():
                            if cal.get("is_calibrating") is True:
                                is_calibrating = True
                                calibrating_sensors.append(cal)
                except Exception:
                    pass

                if is_calibrating:
                    if not hasattr(self, "_last_calibration_print") or current_time - self._last_calibration_print >= 10:
                        sensor_names = ", ".join([c.get("sensor_name", "Unknown") for c in calibrating_sensors])
                        print(f"⚠️ [Orchestrator] Calibration mode is active on the server for: {sensor_names}. Suspending uploads...")
                        self._last_calibration_print = current_time
                    return

                # Enforce cooldown check if camera is enabled (if disabled, should_upload was already timed check)
                if enable_camera and (current_time - self.last_upload_time < upload_interval):
                    if not hasattr(self, "_last_cooldown_print") or current_time - self._last_cooldown_print >= 10:
                        remaining = int(upload_interval - (current_time - self.last_upload_time))
                        print(f"⏳ [Orchestrator] Image captured, but waiting for upload interval cooldown ({remaining}s remaining)...")
                        self._last_cooldown_print = current_time
                    return

                # Check if we have the necessary sensor values cached in-memory
                if self.latest_telemetry["ph"] is None or self.latest_telemetry["ec"] is None or self.latest_telemetry["temperature"] is None:
                    if not hasattr(self, "_last_cache_missing_print") or current_time - self._last_cache_missing_print >= 10:
                        print("⏳ [Orchestrator] Ready for history upload, but waiting for all sensor readings (pH, EC, Temp) to populate cache...")
                        self._last_cache_missing_print = current_time
                    return

                print("📤 [Orchestrator] Cooldown elapsed and payload is ready! Preparing upload...")
                print(f"🎯 [Orchestrator] Target Tank ID: {active_tank_id}")

                data = {
                    "tank_id": active_tank_id,
                    "ph": self.latest_telemetry["ph"],
                    "ec": self.latest_telemetry["ec"],
                    "temp": self.latest_telemetry["temperature"]
                }

                files = None
                if enable_camera and image_path:
                    if not os.path.exists(image_path):
                        print(f"❌ [Orchestrator] Image file not found at {image_path}. Skipping upload.")
                        return
                    try:
                        with open(image_path, "rb") as img_file:
                            img_data = img_file.read()
                        files = {
                            "image": (os.path.basename(image_path), img_data, "image/jpeg")
                        }
                    except Exception as e:
                        print(f"❌ [Orchestrator] Error reading image: {e}")
                        return

                try:
                    upload_url = f"{self.server_url}/api/v1/iot/upload"
                    if files:
                        response = requests.post(upload_url, data=data, files=files, timeout=15.0)
                    else:
                        response = requests.post(upload_url, data=data, timeout=15.0)

                    if response.status_code in [200, 201]:
                        print(f"✅ [Orchestrator] Data successfully uploaded! Server Response: {response.json()}")
                        self.last_upload_time = time.time()

                        # Clear image_path from payload.json if it was uploaded
                        if enable_camera and image_path:
                            try:
                                with open(PAYLOAD_FILE, "a+") as f:
                                    fcntl.flock(f, fcntl.LOCK_EX)
                                    f.seek(0)
                                    content = f.read()
                                    payload = {}
                                    if content.strip():
                                        try:
                                            payload = json.loads(content)
                                        except Exception:
                                            pass
                                    payload.pop("image_path", None)
                                    f.seek(0)
                                    f.truncate()
                                    json.dump(payload, f, indent=4)
                                    fcntl.flock(f, fcntl.LOCK_UN)
                                print(f"🧹 [Orchestrator] Uploaded image path cleared from {PAYLOAD_FILE}")
                            except Exception as e:
                                print(f"❌ [Orchestrator] Failed to clear image_path: {e}")
                    else:
                        print(f"❌ [Orchestrator] Server returned failure status code {response.status_code}: {response.text}")
                except requests.exceptions.RequestException as e:
                    print(f"⚠️ [Orchestrator] Failed to connect to server for upload: {e}")
        except Exception as e:
            print(f"❌ [Orchestrator] Error during payload coordination: {e}")

    def suspend_service(self, name: str):
        """Suspends a service if it is running, and marks it as suspended."""
        if name not in self.suspended_services:
            self.suspended_services.add(name)
        proc = self.processes.get(name)
        if proc and proc.poll() is None:
            print(f"🛑 [Orchestrator] Suspending service '{name}' due to calibration mode...")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        # Remove from active processes so it's not checked or respawned
        self.processes.pop(name, None)

    def resume_service(self, name: str):
        """Resumes a suspended service."""
        if name in self.suspended_services:
            self.suspended_services.remove(name)
        if name not in self.processes:
            # Check enable_camera local settings if resuming camera
            if name == "Camera Capture":
                local_settings = self.load_local_settings()
                if not local_settings.get("enable_camera", True):
                    return
            print(f"🔄 [Orchestrator] Resuming suspended service '{name}'...")
            self.start_service(name, BACKGROUND_SERVICES[name])

    def update_calibration_suspension(self):
        """Fetches active calibration status from the server and suspends/resumes reader services."""
        if not self.server_url:
            return

        is_ph_calibrating = False
        is_ec_calibrating = False

        try:
            calib_url = f"{self.server_url}/api/v1/calibration/"
            response = requests.get(calib_url, timeout=3.0)
            if response.status_code == 200:
                for cal in response.json():
                    if cal.get("is_calibrating") is True:
                        sensor_name = cal.get("sensor_name", "")
                        if "ph" in sensor_name:
                            is_ph_calibrating = True
                        elif "ec" in sensor_name:
                            is_ec_calibrating = True
        except Exception:
            # Silent fallback if offline
            pass

        # Handle pH Reader suspension
        if is_ph_calibrating:
            if "pH Reader" in self.processes:
                self.suspend_service("pH Reader")
        else:
            if "pH Reader" not in self.processes and "pH Reader" in self.suspended_services:
                self.resume_service("pH Reader")

        # Handle EC Reader suspension
        if is_ec_calibrating:
            if "EC Reader" in self.processes:
                self.suspend_service("EC Reader")
        else:
            if "EC Reader" not in self.processes and "EC Reader" in self.suspended_services:
                self.resume_service("EC Reader")

    def monitor_and_loop(self):
        """Main orchestrator monitoring loop."""
        self.server_url = self.discover_leafcloud_server()
        
        local_settings = self.load_local_settings()
        enable_camera = local_settings.get("enable_camera", True)

        # Start all long-running sensor and calibration scripts
        for name, script in BACKGROUND_SERVICES.items():
            if name == "Camera Capture" and not enable_camera:
                print("🚫 [Orchestrator] Camera Capture service disabled in local settings.")
                continue
            self.start_service(name, script)
        
        print("\n⭐ [Orchestrator] IoT Orchestration Engine Active. Press Ctrl+C to terminate.")
        print("-" * 80)
        
        try:
            while self.running:
                # Suspend/Resume readers based on active calibration mode
                self.update_calibration_suspension()

                # Check if payload is complete and upload it
                self.check_and_upload_payload()

                # 3. Check health of background services and respawn if dead
                for name, proc in list(self.processes.items()):
                    if name in self.suspended_services:
                        continue
                    if proc.poll() is not None:
                        print(f"⚠️ [Orchestrator] Service '{name}' terminated unexpectedly. Respawning...")
                        self.start_service(name, BACKGROUND_SERVICES[name])

                time.sleep(2)
        except KeyboardInterrupt:
            print("\n👋 [Orchestrator] Shutdown signal received.")
        finally:
            self.stop_all_services()

def signal_handler(signum, frame):
    raise KeyboardInterrupt

if __name__ == "__main__":
    # Register signal handlers for graceful exit
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    orchestrator = Orchestrator()
    orchestrator.monitor_and_loop()
