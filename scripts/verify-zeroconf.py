from zeroconf import ServiceBrowser, Zeroconf, ServiceListener
import time

class MyListener(ServiceListener):
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"Service {name} updated")

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"Service {name} removed")

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        print(f"Service {name} added, service info: {info}")

if __name__ == "__main__":
    zeroconf = Zeroconf()
    listener = MyListener()
    browser = ServiceBrowser(zeroconf, "_leafcloud._tcp.local.", listener)
    
    print("Browsing for _leafcloud._tcp.local. services for 10 seconds...")
    try:
        time.sleep(10)
    finally:
        zeroconf.close()
