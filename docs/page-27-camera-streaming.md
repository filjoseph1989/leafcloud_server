[Prev](./page-26-nutrient-classifier-training-summary.md) | [Next](./page-28-upload-interval-configuration.md)

# Camera Streaming and Terminal Visualization

This guide explains how to stream the Raspberry Pi camera feed over the network and view it either as a high-quality GUI window or directly inside your terminal as live ASCII/TCT art.

---

## 1. Local Network Video Streaming (UDP Broadcaster)

To stream video from the Raspberry Pi to a target machine (such as your Mac) over the local network, you can use the native camera commands.

### Prerequisite: Find your Target Machine's IP Address
On your target machine (e.g., Mac), run:
```bash
ipconfig getifaddr en0
```
*(Assume the target IP is `192.168.1.150` for the examples below).*

### Start the Stream on the Raspberry Pi
Run the appropriate command on the Pi to capture H.264 video and broadcast it over UDP to port `5000` of the target machine:

*   **Modern Raspberry Pi OS (Bookworm/Bullseye):**
    ```bash
    rpicam-vid -t 0 --inline -g 30 --flush --codec h264 --width 640 --height 480 --framerate 30 -o udp://192.168.1.150:5000
    ```
*   **Legacy Raspberry Pi OS:**
    ```bash
    raspivid -t 0 -w 640 -h 480 -fps 30 -o udp://192.168.1.150:5000
    ```

---

## 2. Viewing the UDP Stream on the Target Machine (Mac)

To view the incoming UDP stream, you can install either `ffmpeg` (which includes `ffplay`) or `mpv` on your Mac using Homebrew:

```bash
# Recommended: Install FFmpeg (includes ffplay)
brew install ffmpeg

# Alternative: Install MPV
brew install mpv
```

### Option A: High-Quality Popup GUI Window (Standard Player)
If you prefer a standard video playback window with minimal latency:

*   **Using `ffplay` (Recommended - FFmpeg popup window):**
    ```bash
    ffplay -fflags nobuffer -flags low_delay udp://0.0.0.0:5000
    ```
*   **Using `mpv`:**
    ```bash
    mpv --demuxer-lavf-o=analyzeduration=0,probesize=32 --profile=low-latency udp://0.0.0.0:5000
    ```

### Option B: Render INSIDE the Terminal (Text-Based)
You can render the live video stream as character blocks or colored ASCII text directly inside your terminal buffer (requires `mpv`):

*   **True Color Terminal Blocks (TCT):**
    ```bash
    mpv --vo=tct udp://0.0.0.0:5000
    ```
*   **Classic Colored ASCII Art (Libcaca):**
    ```bash
    # Requires libcaca (usually installed alongside mpv or via 'brew install libcaca')
    mpv --vo=caca udp://0.0.0.0:5000
    ```

---

## 3. Standalone ASCII Stream (Local terminal renderer)

We also provide a standalone script [ascii_stream.py](../raspberry_pi/ascii_stream.py) that runs directly on the Pi and outputs a live video stream rendered entirely as ASCII characters.

### How it Works
1.  It spawns `rpicam-vid` (or `raspivid`) as a subprocess, requesting a raw YUV420 stream written to `stdout`.
2.  It parses `stdout` byte-by-byte. In YUV420 format, the first $Width \times Height$ bytes represent the **Y (Luminance)** channel, which is a raw grayscale representation of the image.
3.  It scales the grid to your current terminal dimensions and maps the pixel brightness values to an ASCII scale (`@%#*+=-:. `).
4.  It prints the frame and uses ANSI escape cursor codes (`\033[H`) to draw the next frame smoothly over the old one without causing buffer flicker.

### Usage
On your Raspberry Pi:
```bash
python3 raspberry_pi/ascii_stream.py
```
*(Press `Ctrl+C` to terminate the stream).*
