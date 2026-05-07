#!/usr/bin/env python3
"""
Bridge integration JSONL events -> MQTT.

Reads appended lines from detections_output.jsonl and publishes:
- FIRE_DETECTED + detection_type FIRE (+ confidence >= 0.6)
- DEVICE_DETECTED (+ confidence >= 0.6)
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


DEFAULT_JSONL_PATH = "/home/pi/smart_fire_system/detections_output.jsonl"
DEFAULT_BROKER = "raspberrypi.local"
DEFAULT_PORT = 1883
DEFAULT_TOPIC = "camera/pi"
MIN_CONFIDENCE = 0.6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish JSONL fire/device events to MQTT.")
    parser.add_argument("--jsonl", default=DEFAULT_JSONL_PATH)
    parser.add_argument("--broker", default=DEFAULT_BROKER)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument("--camera-id", type=int, default=1)
    parser.add_argument("--from-start", action="store_true", help="Read existing file from beginning.")
    return parser.parse_args()


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_datetime(raw_ts) -> str:
    if isinstance(raw_ts, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw_ts), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            pass
    if isinstance(raw_ts, str) and raw_ts.strip():
        return raw_ts.strip()
    return datetime.now(timezone.utc).isoformat()


def _build_payload(evt: dict, args: argparse.Namespace) -> dict | None:
    alert_status = str(evt.get("alert_status", "")).strip().upper()
    detection_type = str(evt.get("detection_type", "")).strip()
    confidence = _to_float(evt.get("confidence"))

    if not alert_status:
        return None

    if alert_status == "FIRE_DETECTED":
        if detection_type.upper() != "FIRE":
            return None
        if confidence is None or confidence < MIN_CONFIDENCE:
            return None
        payload = {
            "alert_status": "FIRE_DETECTED",
            "detection_type": "FIRE",
            "confidence": confidence,
            "frame": evt.get("frame"),
            "zone": evt.get("zone"),
            "frame_path": (
                evt.get("frame_path")
                or evt.get("fire_frame_path")
                or evt.get("fire_frame")
                or evt.get("image_path")
            ),
            "dateandtime": _normalize_datetime(evt.get("dateandtime") or evt.get("timestamp")),
            "device_id": evt.get("device_id", args.device_id),
            "camera_id": evt.get("camera_id", args.camera_id),
        }
        return payload

    if alert_status == "DEVICE_DETECTED":
        if confidence is None or confidence < MIN_CONFIDENCE:
            return None
        payload = {
            "alert_status": "DEVICE_DETECTED",
            "detection_type": detection_type or "unknown",
            "confidence": confidence,
            "frame": evt.get("frame"),
            "dateandtime": _normalize_datetime(evt.get("dateandtime") or evt.get("timestamp")),
            "device_id": evt.get("device_id", args.device_id),
            "camera_id": evt.get("camera_id", args.camera_id),
        }
        return payload

    return None


def main() -> None:
    args = parse_args()
    client = mqtt.Client()
    client.connect(args.broker, args.port, 60)
    client.loop_start()

    print(f"[Bridge] JSONL: {args.jsonl}")
    print(f"[Bridge] MQTT: {args.broker}:{args.port} topic={args.topic}")
    print("[Bridge] Running... Ctrl+C to stop")

    try:
        while not os.path.exists(args.jsonl):
            print(f"[Bridge] waiting for file: {args.jsonl}")
            time.sleep(1.0)

        with open(args.jsonl, "r", encoding="utf-8") as f:
            if not args.from_start:
                f.seek(0, os.SEEK_END)

            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.2)
                    continue

                line = line.strip()
                if not line:
                    continue

                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue

                payload = _build_payload(evt, args)
                if payload is None:
                    continue

                result = client.publish(args.topic, json.dumps(payload), qos=1)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    print(f"[Bridge] published: {payload.get('alert_status')} conf={payload.get('confidence')}")
                else:
                    print(f"[Bridge] publish failed rc={result.rc}")

    except KeyboardInterrupt:
        print("\n[Bridge] stopping...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

