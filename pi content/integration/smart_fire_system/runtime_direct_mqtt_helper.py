#!/usr/bin/env python3
"""
Direct MQTT publish helper for production runtime (Option A).

"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import requests


def _mosquitto_pub_binary() -> str:
    ov = os.environ.get("MOSQUITTO_PUB_EXE", "").strip()
    if ov and os.path.isfile(ov):
        return ov
    w = shutil.which("mosquitto_pub")
    if w:
        return w
    for p in ("/usr/bin/mosquitto_pub", "/usr/sbin/mosquitto_pub", "/bin/mosquitto_pub"):
        if os.path.isfile(p):
            return p
    return "mosquitto_pub"


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = "/usr/local/bin:/usr/local/sbin:/usr/bin:/sbin:/bin" + os.pathsep + env.get("PATH", "")
    return env


def _mosquitto_pub_cmd(
    *,
    broker_host: str,
    broker_port: int,
    topic: str,
    qos: int,
    message: str,
    username: str = "",
    password: str = "",
    use_tls: bool = False,
    tls_capath: str = "/etc/ssl/certs",
) -> list[str]:
    cmd: list[str] = [
        _mosquitto_pub_binary(),
        "-h",
        str(broker_host),
        "-p",
        str(broker_port),
        "-t",
        str(topic),
        "-q",
        str(qos),
        "-m",
        message,
    ]
    if username:
        cmd.extend(["-u", str(username)])
    if password:
        cmd.extend(["-P", str(password)])
    if use_tls:
        # Prefer OS bundle (matches HiveMQ TLS on Raspberry Pi OS / Debian; avoids bad CRLF pasted paths).
        cmd.append("--tls-use-os-certs")
    return cmd


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
    mqtt_username: str = "",
    mqtt_password: str = "",
    mqtt_use_tls: bool = False,
    mqtt_tls_capath: str = "/etc/ssl/certs",
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
    cmd_list = _mosquitto_pub_cmd(
        broker_host=broker_host,
        broker_port=broker_port,
        topic=topic,
        qos=qos,
        message=json.dumps(payload),
        username=mqtt_username,
        password=mqtt_password,
        use_tls=mqtt_use_tls,
        tls_capath=mqtt_tls_capath,
    )
    try:
        subprocess.run(
            cmd_list,
            check=True,
            capture_output=True,
            text=True,
            env=_subprocess_env(),
        )
        print(f"[MQTT] OK published FIRE -> {topic} ({broker_host}:{broker_port})", flush=True)
        return True
    except FileNotFoundError:
        print("[MQTT] mosquitto_pub not found — sudo apt install mosquitto-clients", flush=True)
        return False
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or "").strip()
        print(f"[MQTT] publish FIRE failed: {err}", flush=True)
        return False
    except Exception as exc:
        print(f"[MQTT] publish FIRE error: {exc}", flush=True)
        return False


def publish_device_event_via_mosquitto(
    *,
    broker_host: str,
    broker_port: int,
    topic: str,
    qos: int,
    detection_type: str,
    confidence: float,
    frame_id: int,
    zone: int,
    frame_path: str = "",
    frame_url: str = "",
    dateandtime: str,
    device_id: int,
    camera_id: int,
    mqtt_username: str = "",
    mqtt_password: str = "",
    mqtt_use_tls: bool = False,
    mqtt_tls_capath: str = "/etc/ssl/certs",
) -> bool:
    payload = {
        "alert_status": "DEVICE_DETECTED",
        "detection_type": str(detection_type),
        "confidence": float(confidence),
        "frame": int(frame_id),
        "zone": int(zone),
        "frame_path": frame_path,
        "frame_url": frame_url,
        "dateandtime": dateandtime,
        "device_id": int(device_id),
        "camera_id": int(camera_id),
    }
    cmd_list = _mosquitto_pub_cmd(
        broker_host=broker_host,
        broker_port=broker_port,
        topic=topic,
        qos=qos,
        message=json.dumps(payload),
        username=mqtt_username,
        password=mqtt_password,
        use_tls=mqtt_use_tls,
        tls_capath=mqtt_tls_capath,
    )
    try:
        subprocess.run(
            cmd_list,
            check=True,
            capture_output=True,
            text=True,
            env=_subprocess_env(),
        )
        print(f"[MQTT] OK published DEVICE -> {topic} ({broker_host}:{broker_port})", flush=True)
        return True
    except FileNotFoundError:
        print("[MQTT] mosquitto_pub not found — sudo apt install mosquitto-clients", flush=True)
        return False
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or "").strip()
        print(f"[MQTT] publish DEVICE failed: {err}", flush=True)
        return False
    except Exception as exc:
        print(f"[MQTT] publish DEVICE error: {exc}", flush=True)
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
        self._lock = threading.Lock()

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

    def _upload_frame_and_get_url(self, frame_path: str, timeout_sec: int = 12) -> str:
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
                    timeout=(5, timeout_sec),
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
        mqtt_username: str = "",
        mqtt_password: str = "",
        mqtt_use_tls: bool = False,
        mqtt_tls_capath: str = "/etc/ssl/certs",
    ) -> bool:
        now_ts = float(now_ts if now_ts is not None else time.time())
        with self._lock:
            if not self._should_send(zone=zone, confidence=confidence, now_ts=now_ts):
                return False

            frame_url = ""
            if frame_path:
                frame_url = self._upload_frame_and_get_url(frame_path) or ""

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
                mqtt_username=mqtt_username,
                mqtt_password=mqtt_password,
                mqtt_use_tls=mqtt_use_tls,
                mqtt_tls_capath=mqtt_tls_capath,
            )
            if sent:
                self._last_zone = int(zone)
                self._last_confidence = float(confidence)
                self._last_sent_at = now_ts
            return sent


class DeviceEventRuntimePublisher:
    """Publish high-risk device detections to MQTT with dedupe/throttle."""

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
        self._last_type: str | None = None
        self._last_confidence: float | None = None
        self._lock = threading.Lock()

    def _should_send(self, *, detection_type: str, zone: int, confidence: float, now_ts: float) -> bool:
        if self._last_type is None:
            return True
        if str(detection_type) != str(self._last_type):
            return True
        if int(zone) != int(self._last_zone):
            return True
        if self._last_confidence is None or abs(float(confidence) - self._last_confidence) >= self.min_conf_delta_to_resend:
            return True
        if (now_ts - self._last_sent_at) >= self.min_send_interval_sec:
            return True
        return False

    def _upload_frame_and_get_url(self, frame_path: str, timeout_sec: int = 12) -> str:
        if not frame_path:
            return ""
        url = f"{self.backend_base_url}/api/video/frames/upload"
        headers = {}
        if self.upload_api_key:
            headers["X-Fire-Frame-Key"] = self.upload_api_key
        try:
            with open(frame_path, "rb") as f:
                resp = requests.post(
                    url,
                    files={"file": (Path(frame_path).name, f, "image/jpeg")},
                    headers=headers,
                    timeout=(5, timeout_sec),
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
        detection_type: str,
        confidence: float,
        frame_id: int,
        zone: int,
        frame_path: str,
        dateandtime: str,
        device_id: int,
        camera_id: int,
        now_ts: float | None = None,
        mqtt_username: str = "",
        mqtt_password: str = "",
        mqtt_use_tls: bool = False,
        mqtt_tls_capath: str = "/etc/ssl/certs",
    ) -> bool:
        now_ts = float(now_ts if now_ts is not None else time.time())
        with self._lock:
            if not self._should_send(
                detection_type=detection_type, zone=zone, confidence=confidence, now_ts=now_ts
            ):
                return False

            frame_url = ""
            if frame_path:
                frame_url = self._upload_frame_and_get_url(frame_path) or ""

            sent = publish_device_event_via_mosquitto(
                broker_host=broker_host,
                broker_port=broker_port,
                topic=topic,
                qos=qos,
                detection_type=str(detection_type),
                confidence=float(confidence),
                frame_id=int(frame_id),
                zone=int(zone),
                frame_path=frame_path,
                frame_url=frame_url,
                dateandtime=str(dateandtime),
                device_id=int(device_id),
                camera_id=int(camera_id),
                mqtt_username=mqtt_username,
                mqtt_password=mqtt_password,
                mqtt_use_tls=mqtt_use_tls,
                mqtt_tls_capath=mqtt_tls_capath,
            )
            if sent:
                self._last_type = str(detection_type)
                self._last_zone = int(zone)
                self._last_confidence = float(confidence)
                self._last_sent_at = now_ts
            return sent

