#!/usr/bin/env python3
import socket
import sys
import subprocess
import re
import argparse
from concurrent.futures import ThreadPoolExecutor

# Known Raspberry Pi MAC Address prefixes (OUI)
RPI_MAC_PREFIXES = {
    "b8:27:eb",  # Pi 3 and older
    "dc:a6:32",  # Pi 4
    "e4:5f:01",  # Pi 4 / Pi 5
    "d8:3a:dd",  # Pi 4 / Pi 5
    "2c:cf:67",  # Pi 5
    "38:1f:8d",  # Pi 5 / newer
}

def get_local_ip():
    """Gets the local IP address of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def ping_ip(ip):
    """Sends a single quick ping to populate the ARP table."""
    try:
        # -c 1: 1 packet, -t 1: 1 second timeout (macOS/Linux compatible)
        result = subprocess.run(
            ["ping", "-c", "1", "-t", "1", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return ip, result.returncode == 0
    except Exception:
        return ip, False

def check_ssh(ip, timeout=1.5):
    """Checks if port 22 (SSH) is open on the target IP and tries to read the SSH banner."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, 22))
        if result == 0:
            try:
                banner = sock.recv(1024).decode('utf-8', errors='ignore').strip()
            except Exception:
                banner = "Unknown (port 22 open)"
            sock.close()
            return True, banner
        sock.close()
    except Exception:
        pass
    return False, ""

def get_arp_table():
    """Runs 'arp -an' and parses IP and MAC addresses."""
    devices = {}
    try:
        # arp -an works on macOS and Linux
        output = subprocess.check_output(["arp", "-an"]).decode('utf-8')
        
        # Regex to match IP and MAC address in macOS/Linux arp -an output
        pattern = r"\((.*?)\)\s+at\s+([0-9a-fA-F:-]+)"
        matches = re.findall(pattern, output)
        for ip, mac in matches:
            # Normalize MAC address formatting (remove leading zeros, lowercase)
            mac_parts = [part.zfill(2) for part in mac.replace("-", ":").split(":")]
            normalized_mac = ":".join(mac_parts).lower()
            devices[ip] = normalized_mac
    except Exception as e:
        print(f"[!] Error reading ARP table: {e}")
    return devices

def scan_single_device(ip):
    """Pings and checks SSH status for a single IP."""
    ping_ip(ip)
    ssh_active, banner = check_ssh(ip)
    return ip, ssh_active, banner

def check_mdns_resolution(hostname="raspberrypi.local"):
    """Attempts to resolve the IP address of a local hostname."""
    try:
        ip = socket.gethostbyname(hostname)
        return ip
    except socket.gaierror:
        return None

def run_diagnostics(target_ip):
    """Runs detailed connectivity diagnostics on a specific IP."""
    print(f"=== Diagnosing Connection to {target_ip} ===")
    
    # 1. Ping test
    print(f"[*] 1. Pinging {target_ip}...")
    _, ping_ok = ping_ip(target_ip)
    if ping_ok:
        print(f"   [+] Ping responded successfully!")
    else:
        print(f"   [-] Ping failed (host may be down, blocking ICMP, or unreachable).")
        
    # 2. Port 22 (SSH) Check
    print(f"[*] 2. Checking port 22 (SSH) on {target_ip}...")
    ssh_ok, banner = check_ssh(target_ip, timeout=2.5)
    if ssh_ok:
        print(f"   [+] Port 22 (SSH) is OPEN!")
        print(f"   [+] SSH Banner: {banner}")
    else:
        print(f"   [-] Port 22 (SSH) is CLOSED or FILTERED.")
        
    # 3. ARP cache check
    print(f"[*] 3. Checking ARP cache...")
    arp_devices = get_arp_table()
    mac = arp_devices.get(target_ip)
    if mac:
        is_pi_mac = False
        for prefix in RPI_MAC_PREFIXES:
            if mac.startswith(prefix):
                is_pi_mac = True
                break
        pi_desc = " (Raspberry Pi Foundation MAC)" if is_pi_mac else ""
        print(f"   [+] MAC address found: {mac}{pi_desc}")
    else:
        print(f"   [-] Not found in local ARP cache. The device might not be on the local network.")

    # 4. Actionable Advice
    print("\n=== Troubleshooting Recommendations ===")
    if ssh_ok:
        print(f"👉 Since port 22 is OPEN, your network connectivity is working!")
        print(f"👉 If you still cannot connect via 'ssh tin@{target_ip}':")
        print(f"   a) Check if the user 'tin' exists on the Raspberry Pi.")
        print(f"   b) Check for host key verification errors. Try clearing the stored host key by running:")
        print(f"      ssh-keygen -R {target_ip}")
        print(f"   c) Try connecting with strict checking disabled to verify:")
        print(f"      ssh -o StrictHostKeyChecking=no tin@{target_ip}")
    else:
        print(f"👉 Since port 22 is CLOSED/FILTERED:")
        print(f"   a) Double-check if the Raspberry Pi's IP address has changed.")
        print(f"      Run this script without arguments to scan the subnet: python3 find_pi.py")
        print(f"   b) Ensure SSH is enabled on the Raspberry Pi:")
        print(f"      - Headless: Mount the SD card on your computer, and create an empty file named 'ssh'")
        print(f"        (no extension) in the root of the 'boot' or 'bootfs' partition.")
        print(f"      - Desktop/Terminal: Run 'sudo raspi-config', navigate to 'Interface Options' -> 'SSH',")
        print(f"        and choose 'Yes' to enable.")
        print(f"   c) iPhone Hotspot Client Isolation:")
        print(f"      If both your computer and the Pi are connected to an iPhone hotspot, Apple devices")
        print(f"      sometimes restrict client-to-client traffic. Try turning Personal Hotspot off and on again,")
        print(f"      or connect both devices to a standard Wi-Fi router.")

def scan_network():
    local_ip = get_local_ip()
    print(f"[*] Your computer's IP address: {local_ip}")
    
    if local_ip == '127.0.0.1':
        print("[!] Could not detect a valid local network IP. Please check your network connection.")
        sys.exit(1)
        
    ip_parts = local_ip.split('.')
    subnet = ".".join(ip_parts[:3])
    print(f"[*] Sweeping subnet {subnet}.1 to {subnet}.254 (checking both ping and SSH port 22 concurrently)...")
    
    ips_to_scan = [f"{subnet}.{i}" for i in range(1, 255)]
    
    # Concurrent sweep of ping AND SSH (this finds devices that ignore ICMP ping but have SSH open)
    scan_results = {}
    with ThreadPoolExecutor(max_workers=60) as executor:
        futures = {executor.submit(scan_single_device, ip): ip for ip in ips_to_scan}
        for future in futures:
            ip, ssh_active, banner = future.result()
            scan_results[ip] = {
                "ssh_active": ssh_active,
                "banner": banner
            }
            
    print("[*] Reading local network ARP cache...")
    arp_devices = get_arp_table()
    
    print("\n=== Scan Results ===")
    
    pi_candidates = []
    other_ssh_devices = []
    other_active_devices = []
    
    for ip, results in scan_results.items():
        if ip == local_ip:
            continue
            
        ssh_active = results["ssh_active"]
        banner = results["banner"]
        mac = arp_devices.get(ip)
        
        # Determine if active (either ssh is open or it is in ARP table or ping succeeded)
        is_active = ssh_active or (mac is not None)
        
        if not is_active:
            continue
            
        is_pi = False
        if mac:
            for prefix in RPI_MAC_PREFIXES:
                if mac.startswith(prefix):
                    is_pi = True
                    break
                    
        device_info = {
            "ip": ip,
            "mac": mac or "Unknown",
            "ssh_active": ssh_active,
            "banner": banner,
            "is_pi": is_pi
        }
        
        if is_pi:
            pi_candidates.append(device_info)
        elif ssh_active:
            other_ssh_devices.append(device_info)
        else:
            other_active_devices.append(device_info)
            
    # Also check if raspberrypi.local resolves
    rpi_local_ip = check_mdns_resolution("raspberrypi.local")
    if rpi_local_ip:
        print(f"[+] Multicast DNS: 'raspberrypi.local' resolves to {rpi_local_ip}")
        # Add to candidates if not already there
        if not any(d["ip"] == rpi_local_ip for d in pi_candidates):
            ssh_active, banner = check_ssh(rpi_local_ip)
            pi_candidates.append({
                "ip": rpi_local_ip,
                "mac": arp_devices.get(rpi_local_ip, "Unknown"),
                "ssh_active": ssh_active,
                "banner": banner,
                "is_pi": True
            })
            
    if pi_candidates:
        print(f"\n[+] Found {len(pi_candidates)} Raspberry Pi candidate(s):")
        for dev in pi_candidates:
            print(f"\n  - IP: {dev['ip']}")
            print(f"    MAC: {dev['mac']} (Raspberry Pi Foundation)")
            print(f"    SSH Active: {dev['ssh_active']}")
            if dev['ssh_active']:
                print(f"    SSH Banner: {dev['banner']}")
                print(f"    Command: ssh tin@{dev['ip']}")
            else:
                print("    [!] SSH is closed on port 22. You need to enable SSH on the Pi.")
    else:
        print("\n[-] No devices matching a Raspberry Pi MAC address were found.")
        
    if other_ssh_devices:
        print(f"\n[*] Found {len(other_ssh_devices)} other device(s) with SSH (port 22) OPEN:")
        print("    (Note: If your Raspberry Pi is using a Wi-Fi dongle or randomized MAC, it might be one of these!)")
        for dev in other_ssh_devices:
            print(f"  - IP: {dev['ip']} | MAC: {dev['mac']} | SSH Active ({dev['banner']})")
            print(f"    Command: ssh tin@{dev['ip']}")
            
    if other_active_devices:
        print(f"\n[*] Found {len(other_active_devices)} other active device(s) on your network (SSH Closed):")
        for dev in other_active_devices:
            print(f"  - IP: {dev['ip']} | MAC: {dev['mac']}")
            
    if not pi_candidates and not other_ssh_devices and not other_active_devices:
        print("[!] No active devices were found. Ensure you are connected to the correct Wi-Fi/network.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find Raspberry Pi devices on local network or diagnose connection.")
    parser.add_argument("target_ip", nargs="?", help="Specific IP address to run diagnostics on.")
    args = parser.parse_args()
    
    if args.target_ip:
        run_diagnostics(args.target_ip)
    else:
        scan_network()
