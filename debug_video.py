import cv2
import os
import platform
import socket
import time

def get_host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def test_video_receiver(port=5000):
    host_ip = get_host_ip()
    is_wsl = "microsoft-standard-WSL2" in platform.uname().release
    
    # Standard FFmpeg options for UDP listening
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "protocol_whitelist;file,rtp,udp|timeout;5000000|stimeout;5000000|buffer_size;10485760"
    
    source_url = f"udp://0.0.0.0:{port}?listen=1"
    
    print(f"--- Video Debug Tool ---")
    print(f"OS: {platform.system()} (WSL: {is_wsl})")
    print(f"Internal IP: {host_ip}")
    print(f"Listening on: {source_url}")
    print(f"\n💡 Command for Raspberry Pi:")
    print(f"rpicam-vid -t 0 --inline -g 30 --flush -o udp://{host_ip}:{port}")
    
    if is_wsl:
        print(f"\n⚠️  WSL2 detected. If this fails to connect:")
        print(f"1. Open PowerShell on Windows and run:")
        print(f"   Test-NetConnection -ComputerName {host_ip} -Port {port} (Note: This is TCP only, but checks route)")
        print(f"2. Ensure Windows Firewall allows UDP port {port}.")
        print(f"3. Try using the Windows Host IP in the Pi command instead of {host_ip}.")
    
    print(f"\nTrying to open stream... (Press Ctrl+C to stop)")
    cap = cv2.VideoCapture(source_url, cv2.CAP_FFMPEG)
    
    if not cap.isOpened():
        print(f"❌ Failed to open stream.")
        return

    print(f"✅ Stream opened! Press 'q' to quit.")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Lost frame/timeout.")
            break
        
        cv2.imshow("Video Debug", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    test_video_receiver()
