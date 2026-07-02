import socket
import time
from zeroconf import Zeroconf, ServiceBrowser, ServiceListener
from typing import Optional

class LeafCloudListener(ServiceListener):
    def __init__(self):
        self.server_url = None

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            # Get IP address
            addresses = info.addresses
            if addresses:
                ip = socket.inet_ntoa(addresses[0])
                port = info.port
                self.server_url = f"http://{ip}:{port}"
                print(f"📡 Discovered LeafCloud Server at {self.server_url}")

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

def discover_server(timeout: int = 10) -> Optional[str]:
    """
    Browses the local network for the LeafCloud Server using Zeroconf.
    Returns the server URL (e.g., 'http://192.168.1.50:8000') or None if not found.
    """
    zeroconf = Zeroconf()
    listener = LeafCloudListener()

    # assigned to a variable (not discarded) to prevent garbage collection from killing its background thread
    browser = ServiceBrowser(zeroconf, "_leafcloud._tcp.local.", listener)
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        if listener.server_url:
            zeroconf.close()
            return listener.server_url
        time.sleep(0.5)
        
    zeroconf.close()
    return None

if __name__ == "__main__":
    print("🔍 Searching for LeafCloud Server on the local network...")
    url = discover_server()
    if url:
        print(f"✅ Found! URL: {url}")
    else:
        print("❌ Server not found within timeout.")
