#!/usr/bin/env python3
"""
Direct MQTT publish helper for production runtime (Option A).

"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import requests


def save_fire_frame(frame: Any, fire_frames_dir: str, frame_id: int) -> str:
    frame_path = str(Path(fire_frames_dir) / f"frame_{frame_id}.jpg")
    try:
        cv2.imwrite(frame_path, frame)
    except Exception:
        return ""
    return frame_path


def to_iso_datetime(value: Any) -> str:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            pass
    if isinstance(value, str) and value.strip():
        return value.strip()
    return datetime.now(timezone.utc).isoformat()


def publish_fire_event_via_mosquitto(
    *,
    broker_host: str,
    broker_port: int,
    topic: str,
    qos: int,
    confidence: float,
    frame_id: int,
    zone: int,
    frame_path: str,
    frame_url: str = "",
    dateandtime: str,
    device_id: int,
    camera_id: int,
) -> bool:
    payload = {
        "alert_status": "FIRE_DETECTED",
        "detection_type": "FIRE",
        "confidence": float(confidence),
        "frame": int(frame_id),
        "zone": int(zone),
        "frame_path": frame_path,
        "frame_url": frame_url,
        "dateandtime": dateandtime,
        "device_id": int(device_id),
        "camera_id": int(camera_id),
    }
    try:
        subprocess.run(
            [
                "mosquitto_pub",
                "-h",
                str(broker_host),
                "-p",
                str(broker_port),
                "-t",
                str(topic),
                "-q",
                str(qos),
                "-m",
                json.dumps(payload),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except FileNotFoundError:
        print("[MQTT] mosquitto_pub not found. Install mosquitto-clients.")
        return False
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or "").strip()
        print(f"[MQTT] publish failed: {err}")
        return False


class FireEventRuntimePublisher:
    """Upload frame + publish MQTT with dedupe/throttle."""

    def __init__(
        self,
        *,
        backend_base_url: str,
        upload_api_key: str,
        min_send_interval_sec: float = 20.0,
        min_conf_delta_to_resend: float = 0.08,
    ) -> None:
        self.backend_base_url = backend_base_url.rstrip("/")
        self.upload_api_key = upload_api_key
        self.min_send_interval_sec = float(min_send_interval_sec)
        self.min_conf_delta_to_resend = float(min_conf_delta_to_resend)
        self._last_sent_at = 0.0
        self._last_zone: int | None = None
        self._last_confidence: float | None = None

    def _should_send(self, *, zone: int, confidence: float, now_ts: float) -> bool:
        if self._last_zone is None:
            return True
        if int(zone) != int(self._last_zone):
            return True
        if self._last_confidence is None or abs(float(confidence) - self._last_confidence) >= self.min_conf_delta_to_resend:
            return True
        if (now_ts - self._last_sent_at) >= self.min_send_interval_sec:
            return True
        return False

    def _upload_frame_and_get_url(self, frame_path: str, timeout_sec: int = 30) -> str:
        if not frame_path:
            return ""
        url = f"{self.backend_base_url}/api/video/fire-frames/upload"
        headers = {}
        if self.upload_api_key:
            headers["X-Fire-Frame-Key"] = self.upload_api_key
        try:
            with open(frame_path, "rb") as f:
                resp = requests.post(
                    url,
                    files={"file": (Path(frame_path).name, f, "image/jpeg")},
                    headers=headers,
                    timeout=timeout_sec,
                )
            if resp.status_code != 201:
                print(f"[UPLOAD] failed HTTP {resp.status_code}: {resp.text}")
                return ""
            return str(resp.json().get("url", "")).strip()
        except Exception as exc:
            print(f"[UPLOAD] exception: {exc}")
            return ""

    def send_if_needed(
        self,
        *,
        broker_host: str,
        broker_port: int,
        topic: str,
        qos: int,
        confidence: float,
        frame_id: int,
        zone: int,
        frame_path: str,
        dateandtime: str,
        device_id: int,
        camera_id: int,
        now_ts: float | None = None,
    ) -> bool:
        now_ts = float(now_ts if now_ts is not None else time.time())
        if not self._should_send(zone=zone, confidence=confidence, now_ts=now_ts):
            return False

        frame_url = self._upload_frame_and_get_url(frame_path)
        sent = publish_fire_event_via_mosquitto(
            broker_host=broker_host,
            broker_port=broker_port,
            topic=topic,
            qos=qos,
            confidence=float(confidence),
            frame_id=int(frame_id),
            zone=int(zone),
            frame_path=frame_path,
            frame_url=frame_url,
            dateandtime=dateandtime,
            device_id=int(device_id),
            camera_id=int(camera_id),
        )
        if sent:
            self._last_zone = int(zone)
            self._last_confidence = float(confidence)
            self._last_sent_at = now_ts
        return sent

