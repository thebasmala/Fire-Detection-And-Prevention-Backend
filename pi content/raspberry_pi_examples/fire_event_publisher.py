#!/usr/bin/env python3
"""
Publish fire/device events in the same shape used by integration JSON lines.
Use this first to validate Pi MQTT -> backend ingestion.
"""

import argparse
import json
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


MQTT_BROKER = "raspberrypi.local"
MQTT_PORT = 1883
MQTT_TOPIC = "camera/pi"
MQTT_QOS = 1


def build_fire_payload(args: argparse.Namespace) -> dict:
    return {
        "alert_status": "FIRE_DETECTED",
        "detection_type": "FIRE",
        "confidence": args.confidence,
        "frame": args.frame,
        "zone": args.zone,
        "frame_path": args.frame_path,
        "dateandtime": datetime.now(timezone.utc).isoformat(),
        "device_id": args.device_id,
        "camera_id": args.camera_id,
    }


def build_device_payload(args: argparse.Namespace) -> dict:
    return {
        "alert_status": "DEVICE_DETECTED",
        "detection_type": args.device_type,
        "confidence": args.confidence,
        "frame": args.frame,
        "dateandtime": datetime.now(timezone.utc).isoformat(),
        "device_id": args.device_id,
        "camera_id": args.camera_id,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish test fire/device event to MQTT.")
    parser.add_argument("--kind", choices=["fire", "device"], default="fire")
    parser.add_argument("--broker", default=MQTT_BROKER)
    parser.add_argument("--port", type=int, default=MQTT_PORT)
    parser.add_argument("--topic", default=MQTT_TOPIC)
    parser.add_argument("--confidence", type=float, default=0.62)
    parser.add_argument("--frame", type=int, default=857)
    parser.add_argument("--zone", type=int, default=2)
    parser.add_argument("--frame-path", default="/home/pi/smart_fire_system/fire_frames/frame_857.jpg")
    parser.add_argument("--device-id", type=int, default=1)
    parser.add_argument("--camera-id", type=int, default=1)
    parser.add_argument("--device-type", default="kettle")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_fire_payload(args) if args.kind == "fire" else build_device_payload(args)

    client = mqtt.Client()
    client.connect(args.broker, args.port, 60)
    result = client.publish(args.topic, json.dumps(payload), qos=MQTT_QOS)
    client.disconnect()

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"Published to {args.topic}:")
        print(json.dumps(payload, indent=2))
    else:
        print(f"Publish failed, rc={result.rc}")


if __name__ == "__main__":
    main()

