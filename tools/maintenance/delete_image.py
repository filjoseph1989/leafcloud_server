"""
Delete an image via the leafcloud API by providing its full image URL.
The script first checks if the image exists (GET), then sends a DELETE request.

Usage:
    python delete_image.py <image_url>

Example:
    python delete_image.py http://192.168.1.18:8000/images/2026-05-03/NPK/._reading_NPK_20260503_163917.jpg
"""

import sys
import requests
from urllib.parse import urlparse

TOKEN = "demo-access-token-xyz-789"
HEADERS = {"Authorization": TOKEN}


def delete_image(image_url: str):
    parsed = urlparse(image_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Extract the path after /images/ to use as the filename for DELETE
    path = parsed.path  # e.g. /images/2026-05-03/NPK/filename.jpg
    if not path.startswith("/images/"):
        print(f"ERROR: URL path must start with /images/, got: {path}")
        sys.exit(1)

    # Check if the image exists first
    print(f"Checking if image exists: {image_url}")
    try:
        head_resp = requests.head(image_url, timeout=10)
    except requests.ConnectionError:
        print(f"ERROR: Cannot connect to {base_url}")
        sys.exit(1)

    if head_resp.status_code == 404:
        print(f"Image not found (404): {image_url}")
        sys.exit(1)
    elif head_resp.status_code != 200:
        print(f"Unexpected status when checking image: {head_resp.status_code}")
        sys.exit(1)

    print(f"Image exists. Sending DELETE request...")

    # DELETE /images/<filename:path>  — strip leading /images/ from path
    delete_url = f"{base_url}{path}"
    resp = requests.delete(delete_url, headers=HEADERS, timeout=10)

    if resp.status_code == 200:
        print(f"SUCCESS: {resp.json().get('message', resp.text)}")
    elif resp.status_code == 401:
        print("ERROR: Unauthorized — check the token.")
    elif resp.status_code == 404:
        print(f"ERROR: Image not found on server — {resp.json().get('detail', resp.text)}")
    else:
        print(f"ERROR {resp.status_code}: {resp.text}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python delete_image.py <image_url>")
        print("Example: python delete_image.py http://192.168.1.18:8000/images/2026-05-03/NPK/._reading_NPK_20260503_163917.jpg")
        sys.exit(1)

    delete_image(sys.argv[1])
