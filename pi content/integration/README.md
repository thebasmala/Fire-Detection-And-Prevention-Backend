# Smart Fire Detection Turret

Production-oriented fire detection and tracking system for Raspberry Pi + Hailo + Arduino.

## Overview

This project detects fire in camera frames, tracks target movement, and sends motion/pump/lamp commands to an Arduino-controlled turret.

For a detailed explanation of every file and how the full system works internally, read [`FILE_GUIDE.md`](FILE_GUIDE.md).

### Hardware
- Raspberry Pi 5
- Picamera2 (`640x480`)
- Hailo AI accelerator
- Arduino Mega (serial `9600`)
- Stepper motor (PAN / X axis)
- Servo motor (TILT / Y axis)

## How to use

### 1. Prerequisites

- **Raspberry Pi OS** on Pi 5, with Picamera2 and Hailo runtime installed per your Hailo / Picamera2 setup guides.
- **Python 3.10+** with packages used by the project (e.g. `opencv-python`, `numpy`, `pyserial`, `picamera2`, Hailo bindings).
- **Arduino** connected via USB serial; firmware must accept the same command lines this project sends (`X …`, `SERVO…`, `PUMP_ON` / `PUMP_OFF`, `LAMP…`, `RESET`, etc.).

### 2. First-time setup

1. **Model path** — In `smart_fire_system/config.py`, set `FIRE_MODEL_PATH` to your `.hef` fire model (default assumes a path under `/home/pi/smart_fire_system/...`).
2. **Serial port** — Set `SERIAL_PORT` (e.g. `/dev/ttyUSB0` or `/dev/ttyACM0`) and `BAUDRATE` (`9600`).
3. **Logs and frames** — `LOG_FILE` and `FIRE_FRAMES_DIR` are created automatically if their parent directories exist; adjust paths in `config.py` if needed.
4. **Display** — The app opens an OpenCV window. Run on the Pi desktop or with a display/export suitable for `cv2.imshow`, or adapt the loop for headless use.

### 3. Run the application

From the project root (the folder that contains `smart_fire_main.py`):

```bash
cd /path/to/integration
python smart_fire_main.py
```

Alternatively:

```bash
python -m smart_fire_system.app
```

(Use the first form if your working directory is the repo root so imports resolve as in `smart_fire_main.py`.)

### 4. Controls (while the preview window is focused)

| Key | Action |
|-----|--------|
| **q** | Quit normally (pump off, serial cleanup, camera stop). |
| **e** | Emergency stop: pump off, `RESET` to Arduino, then exit. |

### 5. MQTT (HiveMQ Cloud vs local Mosquitto)

The Pi **publishes** detection events; the FastAPI backend **subscribes** to the **same broker**.

| Mode | `MQTT_BROKER_HOST` | Port | User / pass | TLS |
|------|-------------------|------|-------------|-----|
| **HiveMQ Cloud** (current default in `config.py`) | `*.hivemq.cloud` | `8883` | set both | yes |
| **Local Mosquitto on Pi** | `127.0.0.1` | `1883` | empty | no |

On the Pi:

1. Copy `smart_fire_system/mqtt.env.example` → `smart_fire_system/mqtt.env` and set `SMART_FIRE_MQTT_PASS` (same password as HiveMQ console / PC `.env`).
2. Or export before run: `export SMART_FIRE_MQTT_PASS='your-password'`
3. Install clients: `sudo apt install mosquitto-clients`
4. Restart runtime; look for `[MQTT] OK published` and `[Config] mode=cloud`.

Requires network from Pi to the internet for HiveMQ (not only LAN).

### 6. Configuration (`smart_fire_system/config.py`)

Important knobs:

| Setting | Purpose |
|---------|---------|
| `DEBUG` | Verbose / debug prints from some subsystems. |
| `EXPECTED_FRAME_W` / `EXPECTED_FRAME_H` | Expected camera size (default `640×480`). |
| `FRAME_MIRROR_X` | Flip image horizontally if the camera is mounted mirrored. |
| `INVERT_PAN_X` / `INVERT_TILT_Y` | Flip mapping from image to pan/tilt direction. |
| `ARDUINO_DUAL_SERVO_PAN_TILT` | `False` = stepper pan + `SERVO` tilt; `True` = dual-servo mode in firmware. |
| `CALIBRATION_DEBUG` | Prints pixel → grid → interpolated pan/servo each aim update (noisy; use for tuning). |
| `CALIB_STEPPER_CUMULATIVE_AT_ORIGIN` | Arduino **cumulative step count** when the turret is physically at grid cell **(3,3)**. If you align center with e.g. `X-40` from your zero reference, set this to **`-40`** so pan error matches the calibration table. |
| `CALIB_MAX_PAN_DELTA_PER_FRAME` / `CALIB_MAX_SERVO_DELTA_PER_FRAME` | Limits per-frame motion to reduce jumps and oscillation. |
| `FIRE_ACTIVE_CONFIRM_FRAMES` | Consecutive valid frames required before fire becomes active. |
| `FIRE_EXTINGUISH_MISSING_FRAMES` | Consecutive missing frames required before an active fire is declared extinguished. |
| `FIRE_TRACK_MATCH_RADIUS_PX` | Pixel radius used to match detections to the same fire ID. |

After changing `config.py`, restart the app.

### 6. Calibration (5×5 grid)

Aiming uses **`smart_fire_system/calibration/mapper.py`**: measured pan/servo samples on a 5×5 grid, nearest-neighbor snapping for locked fire targets, and row interpolation for precision helpers. Pixel `(cx, cy)` is mapped to continuous grid coordinates `(gx, gy)` in `[1,5]`, then motor targets come from the calibration table.

- To **tune** alignment, enable `CALIBRATION_DEBUG = True` and watch the console.
- To **match your mechanical zero**, set `CALIB_STEPPER_CUMULATIVE_AT_ORIGIN` to the stepper sum reported when the nozzle is at the real-world **(3,3)** position.

For stronger perspective correction, you can later replace the pixel→grid mapping with a homography while keeping the same grid→motor tables.

### 7. Outputs

- **JSONL log** — Append-only lines to `LOG_FILE` (detections, smoothing, zone, timing, etc.).
- **Saved frames** — Rate-limited / event-based JPEGs under `FIRE_FRAMES_DIR` (written in a background queue to limit blocking).

## Entry Point

- **Recommended:** `smart_fire_main.py` (thin launcher → `smart_fire_system.app.main()`).
- **Current application loop:** `smart_fire_system/runtime.py`.
- **Compatibility wrapper:** `smart_fire_system/app.py`.

## Project Structure

```text
smart_fire_system/
├── app.py
├── config.py
├── runtime.py
├── calibration/
│   ├── __init__.py
│   └── mapper.py
├── detection/
│   ├── fire_selection.py
│   ├── fire_validator.py
│   └── hailo_detector.py
├── control/
│   ├── arduino.py
│   └── pump.py
├── tracking/
│   ├── fire_state.py
│   ├── tracker.py
│   ├── filter.py
│   └── gate.py
├── vision/
│   └── draw.py
└── utils/
    └── logger.py
```

## Module Responsibilities

- `config.py`  
  Centralized constants and runtime configuration.

- `runtime.py`  
  Current threaded application runtime. Runs detection continuously in a background thread and uses the `IDLE → TARGETING → MONITORING` action state machine.

- `tracking/fire_state.py`  
  Fire ID assignment, confidence-buffer math, active/extinguished state, and one-time snapping to the calibration map.

- `detection/hailo_detector.py`  
  Hailo inference and detection post-processing.  
  Includes `pick_best_fire(...)` for selecting the best fire candidate.

- `detection/fire_selection.py`  
  Selects the best valid fire box using class, confidence, area, edge, HSV, and motion filters.

- `detection/fire_validator.py`  
  Validates Hailo detections with HSV color evidence, motion evidence, brightness diagnostics, and frame health checks.

- `tracking/gate.py`  
  Fire retention finite state machine (`NO_FIRE`, `CONFIRMING`, `LOCKED`, `HOLD`, `LOST`).

- `tracking/filter.py`  
  Target smoothing and jitter reduction (`StableTargetFilter`).

- `tracking/tracker.py`  
  Motion command computation (`ActiveFireTracker`) and re-aim decision (`should_reaim`). Uses the calibration mapper for pan/servo targets.

- `calibration/mapper.py`  
  5×5 grid calibration table, missing-value fill, pixel→grid mapping, nearest-neighbor snapping, and row interpolation helpers.

- `control/arduino.py`  
  Arduino serial communication, command queueing, safety prioritization, and motor/lamp/pump command transmission.

- `control/pump.py`  
  Pump state logic based on tracking/fire conditions.

- `vision/draw.py`  
  Geometry helpers and OpenCV drawing utilities.

- `utils/logger.py`  
  JSON event logging and background frame writing (`FrameWriter`).

## Notes

- Arduino command syntax is preserved and handled only through `ArduinoController`.
- The main loop in `app.py` is orchestration-focused: capture, detect, track, control, draw, and log.
- Frame saving is asynchronous/rate-limited to reduce blocking in real-time operation.
