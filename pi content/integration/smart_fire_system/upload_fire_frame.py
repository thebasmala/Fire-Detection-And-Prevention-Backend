#!/usr/bin/env python3
"""
Upload a saved fire frame image to the backend; prints the public URL for MQTT frame_url.

Usage (after setting backend .env FIRE_FRAME_UPLOAD_API_KEY):
  python3 upload_fire_frame.py --file /home/pi/smart_fire_system/fire_frames/frame_123.jpg

With JWT instead of API key:
  python3 upload_fire_frame.py --file frame.jpg --token YOUR_JWT

Then publish MQTT with frame_url set to the printed URL (backend stores it in video_url).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests  (or: python3 -m pip install requests --break-system-packages)")
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Upload fire frame JPEG/PNG to backend API.")
    p.add_argument("--file", required=True, help="Path to image file on Pi")
    p.add_argument(
        "--backend",
        default="http://192.168.100.4:8000",
        help="Backend base URL (no trailing slash)",
    )
    p.add_argument(
        "--api-key",
        default="",
        help="Same value as backend FIRE_FRAME_UPLOAD_API_KEY; sent as X-Fire-Frame-Key",
    )
    p.add_argument("--token", default="", help="Optional Bearer JWT instead of API key")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.file)
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    url = f"{args.backend.rstrip('/')}/api/video/fire-frames/upload"
    headers = {}
    if args.api_key:
        headers["X-Fire-Frame-Key"] = args.api_key
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    with path.open("rb") as f:
        files = {"file": (path.name, f, "image/jpeg")}
        r = requests.post(url, files=files, headers=headers, timeout=60)

    if r.status_code != 201:
        print(f"Upload failed HTTP {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)

    data = r.json()
    print(data.get("url", ""))


if __name__ == "__main__":
    main()
