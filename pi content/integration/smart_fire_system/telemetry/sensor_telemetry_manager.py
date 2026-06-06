"""Arduino sensor telemetry → JSONL log + optional MQTT (throttled)."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import serial

from smart_fire_system.utils.logger import log_json

_FLUSH_INTERVAL_SEC = 60.0
_DEFAULT_MQTT_INTERVAL_SEC = 60.0

_TEMP_SENSORS: tuple[tuple[int, str, str], ...] = (
    (1, "Temperature Sensor 1", "C"),
    (2, "Temperature Sensor 2", "C"),
    (3, "Temperature Sensor 3", "C"),
    (4, "Temperature Sensor 4", "C"),
)

_MQ2_SENSORS: tuple[tuple[int, str, str], ...] = (
    (5, "MQ2 Sensor 1", "ppm"),
    (6, "MQ2 Sensor 2", "ppm"),
    (7, "MQ2 Sensor 3", "ppm"),
    (8, "MQ2 Sensor 4", "ppm"),
)


def _iso_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _parse_values(prefix: str, line: str, sensors: tuple[tuple[int, str, str], ...]) -> list[dict[str, Any]]:
    if not line.startswith(prefix):
        return []

    payload = line[len(prefix) :].strip()
    if not payload:
        return []

    raw_values = payload.split(",")
    entries: list[dict[str, Any]] = []
    for index, sensor in enumerate(sensors):
        if index >= len(raw_values):
            break
        token = raw_values[index].strip()
        if not token:
            continue
        try:
            value = float(token)
        except ValueError:
            continue
        sensor_id, sensor_name, unit = sensor
        entries.append(
            {
                "data": {
                    "sensor_id": sensor_id,
                    "sensor_name": sensor_name,
                    "value": value,
                    "unit": unit,
                    "status": "normal",
                    "device_id": 0,
                    "timestamp": "",
                }
            }
        )
    return entries


def parse_sensor_line(line: str) -> list[dict[str, Any]]:
    """Parse one serial line into zero or more sensor JSON objects."""
    text = (line or "").strip()
    if not text:
        return []
    if text.startswith("TEMP:"):
        return _parse_values("TEMP:", text, _TEMP_SENSORS)
    if text.startswith("MQ2:"):
        return _parse_values("MQ2:", text, _MQ2_SENSORS)
    return []


class SensorTelemetryManager:
    """Background reader for MQ2/TEMP serial telemetry."""

    def __init__(
        self,
        log_path: str,
        *,
        port: str | None = None,
        baudrate: int = 9600,
        device_id: int = 1,
        debug: bool = False,
        mqtt_publish: Callable[[int, dict[str, Any]], None] | None = None,
        mqtt_interval_sec: float = _DEFAULT_MQTT_INTERVAL_SEC,
    ) -> None:
        self._log_path = log_path
        self._port = port
        self._baudrate = int(baudrate)
        self._device_id = int(device_id)
        self._debug = bool(debug)
        self._mqtt_publish = mqtt_publish
        self._mqtt_interval_sec = max(1.0, float(mqtt_interval_sec))

        self._ser: serial.Serial | None = None
        self._ser_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._latest: dict[int, dict[str, Any]] = {}
        self._last_flush_mono = time.monotonic()
        self._last_mqtt_mono: dict[int, float] = {}
        self._own_serial = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def attach(self, ser: serial.Serial, lock: threading.Lock | None = None) -> None:
        """Share an existing serial port (e.g. ArduinoController.ser)."""
        self._ser = ser
        if lock is not None:
            self._ser_lock = lock
        self._own_serial = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        if self._ser is None and self._port:
            try:
                self._ser = serial.Serial(self._port, self._baudrate, timeout=0.05)
                self._own_serial = True
                if self._debug:
                    print(f"[SensorTelemetry] Opened serial {self._port} @ {self._baudrate}")
            except serial.SerialException as exc:
                print(f"[SensorTelemetry] Serial unavailable: {exc}")
                return

        if self._ser is None or not getattr(self._ser, "is_open", False):
            print("[SensorTelemetry] No serial connection — telemetry disabled.")
            return

        self._stop.clear()
        self._last_flush_mono = time.monotonic()
        mqtt_note = (
            f", MQTT every {self._mqtt_interval_sec:.0f}s"
            if self._mqtt_publish is not None
            else ""
        )
        self._thread = threading.Thread(
            target=self._read_loop,
            name="sensor-telemetry",
            daemon=True,
        )
        self._thread.start()
        print(
            f"[SensorTelemetry] Logging to {self._log_path} "
            f"(flush every {_FLUSH_INTERVAL_SEC:.0f}s{mqtt_note})"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._flush_to_log()
        self._thread = None
        if self._own_serial and self._ser is not None:
            try:
                if self._ser.is_open:
                    self._ser.close()
            except Exception:
                pass
        if self._own_serial:
            self._ser = None

    def _update_cache(self, entries: list[dict[str, Any]]) -> None:
        with self._cache_lock:
            for entry in entries:
                data = dict(entry.get("data") or {})
                sensor_id = data.get("sensor_id")
                if sensor_id is None:
                    continue
                self._latest[int(sensor_id)] = {
                    "sensor_id": int(sensor_id),
                    "sensor_name": data["sensor_name"],
                    "value": data["value"],
                    "unit": data["unit"],
                    "status": data["status"],
                }

    def _flush_to_log(self) -> None:
        with self._cache_lock:
            if not self._latest:
                return
            snapshot = [self._latest[sid] for sid in sorted(self._latest)]

        timestamp = _iso_timestamp()
        for data in snapshot:
            payload = {
                "data": {
                    **data,
                    "device_id": self._device_id,
                    "timestamp": timestamp,
                }
            }
            try:
                log_json(self._log_path, payload)
            except Exception as exc:
                if self._debug:
                    print(f"[SensorTelemetry] Log write error: {exc}")

    def _maybe_flush(self) -> None:
        now = time.monotonic()
        if now - self._last_flush_mono < _FLUSH_INTERVAL_SEC:
            return
        self._last_flush_mono = now
        self._flush_to_log()

    def _maybe_mqtt_publish(self) -> None:
        if self._mqtt_publish is None:
            return
        now = time.monotonic()
        with self._cache_lock:
            snapshot = dict(self._latest)
        for sensor_id, data in snapshot.items():
            last = self._last_mqtt_mono.get(sensor_id, 0.0)
            if now - last < self._mqtt_interval_sec:
                continue
            payload = {
                "sensor_id": sensor_id,
                "device_id": self._device_id,
                "value": data["value"],
                "unit": data.get("unit", ""),
            }
            try:
                self._mqtt_publish(sensor_id, payload)
                self._last_mqtt_mono[sensor_id] = now
                if self._debug:
                    print(f"[SensorTelemetry] MQTT sensor {sensor_id}={data['value']}")
            except Exception as exc:
                if self._debug:
                    print(f"[SensorTelemetry] MQTT publish error sensor {sensor_id}: {exc}")

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            line = ""
            try:
                with self._ser_lock:
                    ser = self._ser
                    if ser is None or not ser.is_open:
                        time.sleep(0.1)
                        self._maybe_flush()
                        self._maybe_mqtt_publish()
                        continue
                    if ser.in_waiting:
                        line = ser.readline().decode(errors="ignore").strip()
            except Exception as exc:
                if self._debug:
                    print(f"[SensorTelemetry] Serial read error: {exc}")
                time.sleep(0.1)
                self._maybe_flush()
                self._maybe_mqtt_publish()
                continue

            if line:
                try:
                    entries = parse_sensor_line(line)
                    if entries:
                        self._update_cache(entries)
                    elif self._debug and (line.startswith("TEMP:") or line.startswith("MQ2:")):
                        print(f"[SensorTelemetry] Ignored malformed line: {line!r}")
                except Exception as exc:
                    if self._debug:
                        print(f"[SensorTelemetry] Parse error: {exc}")

            self._maybe_flush()
            self._maybe_mqtt_publish()

            if not line:
                time.sleep(0.05)
