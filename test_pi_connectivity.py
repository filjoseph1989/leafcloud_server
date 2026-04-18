import requests
import json
import socket
from datetime import datetime

# --- Configuration ---
# Replace with your server's actual IP address
SERVER_IP = "localhost" 
SERVER_PORT = 8000
ENDPOINT = f"http://{SERVER_IP}:{SERVER_PORT}/iot/ping"

def get_pi_info():
    """Gathers some basic info from the Pi to send as test data."""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        hostname = "unknown-pi"
        local_ip = "0.0.0.0"
        
    return {
        "device_id": hostname,
        "pi_local_ip": local_ip,
        "test_timestamp": datetime.now().isoformat(),
        "message": "Hello from Raspberry Pi!"
    }

def test_connectivity():
    print(f"🚀 Testing connectivity to: {ENDPOINT}")
    
    # 1. Prepare data
    data = get_pi_info()
    print(f"📦 Sending payload: {json.dumps(data, indent=2)}")

    try:
        # 2. Send POST request
        response = requests.post(
            ENDPOINT,
            json=data,
            timeout=5
        )

        # 3. Handle response
        if response.status_code == 200:
            print("✅ SUCCESS: Server responded!")
            print(f"📩 Server Reply: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"❌ FAILED: Server returned status code {response.status_code}")
            print(f"📝 Response body: {response.text}")

    except requests.exceptions.ConnectionError:
        print(f"❌ ERROR: Could not connect to {SERVER_IP}:{SERVER_PORT}.")
        print("   - Is the server running?")
        print("   - Are you on the same network?")
        print(f"   - Is the IP '{SERVER_IP}' correct?")
    except Exception as e:
        print(f"❌ ERROR: An unexpected error occurred: {e}")

if __name__ == "__main__":
    test_connectivity()
