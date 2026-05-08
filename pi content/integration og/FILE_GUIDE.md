# Smart Fire System File Guide

This document explains every source file in the project, what each file is responsible for, and how the files work together.

## Big Picture

The application is a Raspberry Pi fire-detection turret. A camera frame is captured, a Hailo model searches for fire, validated fires are tracked with confidence buffers, and an Arduino moves the pan/tilt hardware plus pump/lamp outputs.

The current runtime is built around two loops:

- Detection loop: runs continuously in a background thread. It reads camera frames, runs model inference, validates detections, assigns fire IDs, and updates confidence state.
- Action loop: runs in the main thread. It reads the latest detection snapshot and drives the state machine: `IDLE`, `TARGETING`, and `MONITORING`.

The most important rule is target locking. Once a fire becomes active, its pixel location is snapped once to the nearest calibration map point. The servo/stepper target stays fixed while that fire remains active.

## Runtime Flow

```text
smart_fire_main.py
  -> smart_fire_system.app.main
    -> smart_fire_system.runtime.main
      -> detection thread
         -> camera frame
         -> Hailo detector
         -> HSV/motion validation
         -> confidence fire tracker
      -> action loop
         -> IDLE
         -> TARGETING
         -> MONITORING
         -> return to origin after extinguish
```

## Root Files

### `README.md`

The main project README. It gives the high-level overview, hardware assumptions, setup instructions, run commands, controls, configuration notes, and project structure.

Use this file first when you need to know how to run the project.

### `FILE_GUIDE.md`

This file. It is the detailed explanation of every project file.

Use this file when you want to understand how the code works internally.

### `smart_fire_main.py`

This is the simplest launcher.

```python
from smart_fire_system.app import main

if __name__ == "__main__":
    main()
```

It imports `main` from `smart_fire_system.app` and runs it. Because `app.py` now points `main` to the threaded runtime, this command starts the new dual-loop system:

```bash
python smart_fire_main.py
```

## Package: `smart_fire_system`

### `smart_fire_system/app.py`

This file is now a compatibility wrapper around the new runtime.

At the top, it imports:

```python
from smart_fire_system.runtime import main as threaded_main
```

At the bottom, it assigns:

```python
main = threaded_main
```

That means old code that imports `smart_fire_system.app.main` still works, but the actual running logic comes from `runtime.py`.

The rest of `app.py` still contains the older single-loop application code. It is kept in the file, but the exported `main` points to the new threaded runtime. If you are trying to understand the current behavior, read `runtime.py` first.

### `smart_fire_system/runtime.py`

This is the current main application.

It creates the hardware/software subsystems:

- `HailoDetector` for fire model inference.
- `ArduinoController` for serial commands to Arduino.
- `CalibrationMapper` for pixel-to-map and map-to-servo conversion.
- `FireValidator` for HSV and motion checks.
- `ConfidenceFireTracker` for fire IDs, active/extinguished state, and target locking.

The file contains the dual-thread design:

- `detection_loop()` runs in a daemon thread.
- The main `while True` loop handles UI, state machine, servo movement, pump state, and keyboard controls.

Important classes/functions:

- `DetectionSnapshot`: immutable data object shared from the detection thread to the action loop.
- `_build_arduino()`: builds `ArduinoController` using values from `config.py`.
- `_build_validator()`: builds `FireValidator` using HSV/motion thresholds from `config.py`.
- `_origin_ok()`: checks whether the turret is physically at origin.
- `_target_command()`: converts a locked fire target into a `CenteringCommand`.
- `_target_settled()`: checks whether the hardware has reached the locked target.
- `_select_active_fire()`: chooses which active fire to act on if more than one exists.
- `main()`: starts camera, detection thread, and action loop.

State machine behavior:

- `IDLE`: pump off, turret returns to origin, waits for an active fire.
- `TARGETING`: turret moves to the locked target calculated once by the confidence tracker.
- `MONITORING`: turret holds the same target and pump can stay on while the fire remains active.

UI behavior:

- When a fire first becomes active, the screen shows `ACTIVE FIRE DETECTED`.
- When an active fire is missing long enough, the screen shows `FIRE EXTINGUISHED`.
- Press `q` to quit.
- Press `e` for emergency stop.

### `smart_fire_system/config.py`

This file contains centralized settings. Most tuning should happen here instead of inside logic files.

Important sections:

- Model path and thresholds: `FIRE_MODEL_PATH`, `CONFIDENCE_THRESHOLD`, `MIN_THRESHOLD`.
- Logging paths: `LOG_FILE`, `FIRE_FRAMES_DIR`.
- Arduino serial setup: `SERIAL_PORT`, `BAUDRATE`.
- Hardware mode: `ARDUINO_DUAL_SERVO_PAN_TILT`.
- Camera setup: `EXPECTED_FRAME_W`, `EXPECTED_FRAME_H`, `FRAME_MIRROR_X`.
- Detection timing: `DETECTION_MIN_INTERVAL_S`, `DETECTION_FRAME_STRIDE`.
- Confidence buffer:
  - `FIRE_ACTIVE_CONFIRM_FRAMES`: number of consecutive detected frames needed before a fire becomes active.
  - `FIRE_EXTINGUISH_MISSING_FRAMES`: number of consecutive missing frames needed before an active fire is considered extinguished.
  - `FIRE_TRACK_MATCH_RADIUS_PX`: pixel distance used to match detections to the same fire ID.
- Servo/stepper limits:
  - `SERVO_Y_MIN`, `SERVO_Y_MAX`, `SERVO_Y_CENTER`.
  - `SERVO_X_MIN`, `SERVO_X_MAX`, `SERVO_X_CENTER`.
  - `PAN_STEPS_MIN`, `PAN_STEPS_MAX`.
- Calibration settings:
  - `CALIBRATION_DEBUG`.
  - `CALIB_STEPPER_CUMULATIVE_AT_ORIGIN`.
  - `INVERT_PAN_X`, `INVERT_TILT_Y`.
- HSV/motion validation thresholds.
- Motion-control tuning such as acquire speed, precision speed, backlash compensation, and final deadzone.

The bottom of the file creates log/frame directories automatically:

```python
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(FIRE_FRAMES_DIR, exist_ok=True)
```

## Package: `smart_fire_system/behavior`

### `smart_fire_system/behavior/__init__.py`

Small package marker and description for behavior/state-machine code.

### `smart_fire_system/behavior/cycle.py`

Defines the high-level state names and geometric state checks.

`CycleState` contains:

- `IDLE`
- `TARGETING`
- `MONITORING`

The file also contains helper functions:

- `at_origin_stepper_servo(...)`: returns `True` when the turret is close enough to origin.
- `tracking_settled(...)`: returns `True` when the turret has reached a target within tolerance.

These functions are used by `runtime.py` to know when it can leave `IDLE` and when `TARGETING` has reached the locked fire target.

## Package: `smart_fire_system/calibration`

### `smart_fire_system/calibration/__init__.py`

Exports `CalibrationMapper` so other modules can import it from the calibration package.

### `smart_fire_system/calibration/mapper.py`

This file maps image coordinates into physical motor targets.

It contains a 5x5 environment map:

- `_pan`: pan/stepper calibration values.
- `_servo`: tilt servo calibration values.

The map represents known physical positions. A detected fire is converted from pixel coordinates to a grid coordinate `(gx, gy)` in the range `[1, 5]`.

Important methods:

- `_fill_missing_values()`: fills missing calibration table values using nearby values.
- `pixels_to_grid(...)`: converts pixel `(cx, cy)` into continuous grid `(gx, gy)`.
- `_get_servo_from_x(...)`: looks up or interpolates motor targets.
- `map_point(...)`: returns `(gx, gy, pan_abs, servo_angle)`.
- `evaluate(...)`: returns map values for HUD/telemetry without noisy debug prints.

For target locking, `runtime.py` and `fire_state.py` use nearest-neighbor mode so the fire snaps to the nearest known environment point instead of constantly interpolating while active.

## Package: `smart_fire_system/control`

### `smart_fire_system/control/arduino.py`

This is the serial communication and motor-control layer.

Responsibilities:

- Connect to the Arduino serial port.
- Queue commands so the main loop is not blocked by serial writes.
- Prioritize critical commands such as reset and pump-off.
- Send servo, stepper, pump, laser, and lamp commands.
- Smooth movement and reduce jitter.
- Track last sent servo/stepper positions.

Important command formats:

- `X 10` or `X-10`: stepper movement.
- `SERVO90`: tilt servo in stepper+servo mode.
- `SERVOX90` / `SERVOY90`: dual-servo mode.
- `PUMP_ON` / `PUMP_OFF`.
- `LASER_ON` / `LASER_OFF`.
- `LAMP1_ON`, `LAMP1_OFF`, etc.
- `RESET`.

Important methods:

- `aim_from_command(...)`: accepts a `CenteringCommand` and moves toward it.
- `go_to_origin(...)`: smoothly returns the turret to origin.
- `set_zone(...)`: controls lamp zone indicators.
- `set_pump(...)`: turns pump output on/off.
- `reset()`: sends reset and resets internal position state.
- `close()`: stops serial worker thread and closes serial connection.

The controller supports two hardware modes:

- Stepper pan + one tilt servo.
- Dual-servo pan/tilt.

### `smart_fire_system/control/pump.py`

This is an older helper class for pump decision logic.

`PumpController` turns the pump on only when several conditions are true:

- Fire is confirmed.
- Tracking is locked.
- Aim is established.
- Stable tracking frame count is high enough.
- Tracking has not been lost for longer than cooldown.

The current threaded runtime mainly controls pump directly in `runtime.py`, but this file remains useful if you want a separate pump-state object.

## Package: `smart_fire_system/detection`

### `smart_fire_system/detection/hailo_detector.py`

This file wraps the Hailo model.

Responsibilities:

- Load the `.hef` model.
- Resize camera frames to the model input shape.
- Run Hailo inference.
- Convert normalized model boxes back into original frame pixel coordinates.
- Filter low-confidence detections.
- Return detections as dictionaries:

```python
{
    "box": [x1, y1, x2, y2],
    "conf": score,
    "class_id": class_id,
}
```

Important items:

- `HailoDetector.process_frame(...)`: main inference function.
- `last_infer_ms`: last inference duration for UI/debug display.
- `pick_best_fire(...)`: helper for choosing the largest/highest-confidence fire detection.

In the new runtime, `process_frame(...)` is called continuously by the detection thread.

### `smart_fire_system/detection/fire_selection.py`

Chooses the best valid fire from a list of model detections.

It applies hard filters:

- Class label must be `FIRE`.
- Confidence must be at least `min_conf`.
- Bounding-box area must be large enough.
- Bounding box must not be too close to the frame edge.
- Optional HSV/motion validation must pass.

Main function:

- `pick_valid_fire(...)`

The score formula is:

```text
score = confidence * 0.7 + normalized_area * 0.3
```

The highest-scoring valid fire is returned.

### `smart_fire_system/detection/fire_validator.py`

Adds extra validation after the model detects fire.

The model alone can produce false positives, so this file checks visual evidence:

- HSV fire-color ratio.
- Motion ratio.
- Ambient brightness.
- Camera health/frozen-frame detection.

Core rule:

```text
fire_detected =
    confidence >= threshold
    AND
    (hsv_score >= threshold OR motion_score >= threshold)
```

Important methods:

- `validate(...)`: validates one bounding box.
- `compute_frame_diagnostics(...)`: updates full-frame HSV/motion/brightness diagnostics every frame.
- `check_frame_health(...)`: checks that a camera frame exists and has a valid shape.
- `reset()`: clears temporal history and scores.

The detection thread calls frame diagnostics every loop so the debug UI stays updated even when no fire is active.

## Package: `smart_fire_system/tracking`

### `smart_fire_system/tracking/fire_state.py`

This is the new confidence-buffer and fire-ID tracker.

Important data classes:

- `LockedFireTarget`: the one-time snapped target for a validated fire.
- `FireTrack`: one tracked fire cluster with ID, centroid, confidence, hit/miss counters, active state, extinguished state, and locked target.

Important function:

- `snap_to_environment_map(...)`: maps a pixel point to the nearest calibration/environment map point and returns fixed servo/stepper targets.

Important class:

- `ConfidenceFireTracker`

Confidence buffer math:

```text
If detected:
    hit_count = hit_count + 1
    miss_count = 0

If missing:
    miss_count = miss_count + 1

Active:
    hit_count >= FIRE_ACTIVE_CONFIRM_FRAMES

Extinguished:
    active and miss_count >= FIRE_EXTINGUISH_MISSING_FRAMES
```

When a fire first becomes active, the target is calculated once:

```python
locked_target = snap_to_environment_map(...)
```

After that, the locked target is not recalculated while the fire remains active.

### `smart_fire_system/tracking/filter.py`

Provides `StableTargetFilter`, a smoothing/filtering helper for bounding-box centers.

It keeps a short history of recent detections and returns a confidence-weighted average. It also rejects suspicious jumps or large area changes.

Important methods:

- `update(cx, cy, w, h, conf)`: adds a detection and returns the smoothed center.
- `reset()`: clears detection history.
- `soft_reset()`: compatibility no-op.

The new locked-target runtime does not need constant re-aiming, but the filter is still useful for older tracking paths or future smoothing before activation.

### `smart_fire_system/tracking/tracker.py`

Converts a target pixel coordinate into motor commands.

Important data class:

- `CenteringCommand`: contains `servoy_angle`, `servox_angle`, and `pan_steps`.

Important class:

- `ActiveFireTracker`

It uses `CalibrationMapper` to convert a pixel coordinate to motor targets, applies dead zones, clamps speed, and returns commands suitable for `ArduinoController`.

The new runtime mainly uses `CenteringCommand` from this file and calculates commands from locked targets in `runtime.py`.

Important method:

- `compute(...)`: returns a `CenteringCommand` or `None`.

Important helper:

- `should_reaim(...)`: decides if a new aim command should be sent based on movement/error timing.

### `smart_fire_system/tracking/gate.py`

Older fire-retention gate.

It implements a small state machine:

- `NO_FIRE`
- `CONFIRMING`
- `LOCKED`
- `HOLD`
- `LOST`

It was used to prevent flicker by confirming fire for multiple frames and retaining fire for a short time after it disappears.

The new runtime uses `ConfidenceFireTracker` in `fire_state.py` instead because it also assigns IDs and stores locked targets.

## Package: `smart_fire_system/utils`

### `smart_fire_system/utils/logger.py`

Utility file for logging and frame saving.

Important function:

- `log_json(path, data)`: appends one JSON object per line to a `.jsonl` log file.

Important class:

- `FrameWriter`

`FrameWriter` saves frames in a background thread. This keeps disk writes from blocking the real-time camera/control loop.

Important methods:

- `enqueue(path, frame)`: queues a frame to save.
- `close()`: stops the writer thread.

## Package: `smart_fire_system/vision`

### `smart_fire_system/vision/draw.py`

Contains OpenCV drawing and geometry helpers.

Geometry helpers:

- `frame_center(frame_w, frame_h)`: returns the image center.
- `clamp_centre_to_frame(cx, cy, frame_w, frame_h)`: keeps a point inside the frame.
- `bbox_center_float(box)`: returns the center of a bounding box.
- `cxcy_to_zone(cx, cy, frame_w, frame_h)`: converts image position into one of four lamp zones.

Drawing helpers:

- `draw_detections(...)`: draws model bounding boxes and confidence labels.
- `draw_zones(...)`: draws the 2x2 zone overlay.
- `draw_crosshair(...)`: draws the frame center marker.
- `draw_aim_debug_hud(...)`: draws target, servo, stepper, confidence, and pump information.

## How Files Work Together

### Startup

1. `smart_fire_main.py` imports `smart_fire_system.app.main`.
2. `app.py` points `main` to `runtime.py`.
3. `runtime.py` creates detector, validator, mapper, Arduino controller, and fire tracker.
4. Camera starts.
5. Detection thread starts.
6. Action loop starts.

### Detection Thread

1. Capture frame from Picamera2.
2. Check frame health.
3. Optionally mirror the frame.
4. Convert frame to BGR for OpenCV validation.
5. Compute HSV/motion/brightness diagnostics.
6. Run Hailo inference.
7. Pick best valid fire detection.
8. Update `ConfidenceFireTracker`.
9. Publish a `DetectionSnapshot`.

### Action Loop

1. Read the latest `DetectionSnapshot`.
2. If `IDLE`, keep turret at origin and wait for active fire.
3. If active fire exists, show `ACTIVE FIRE DETECTED` and enter `TARGETING`.
4. In `TARGETING`, move to the locked target.
5. When settled, enter `MONITORING`.
6. In `MONITORING`, hold the locked target and keep pump active.
7. If the current fire is missing for enough frames, show `FIRE EXTINGUISHED`, turn pump off, return to origin, and go back to `IDLE`.

## What To Edit For Common Changes

### Change how many frames confirm a fire

Edit `FIRE_ACTIVE_CONFIRM_FRAMES` in `smart_fire_system/config.py`.

### Change how many missing frames extinguish a fire

Edit `FIRE_EXTINGUISH_MISSING_FRAMES` in `smart_fire_system/config.py`.

### Change fire matching sensitivity

Edit `FIRE_TRACK_MATCH_RADIUS_PX` in `smart_fire_system/config.py`.

### Change physical aiming points

Edit the `_pan` and `_servo` 5x5 arrays in `smart_fire_system/calibration/mapper.py`.

### Change serial port

Edit `SERIAL_PORT` in `smart_fire_system/config.py`.

### Change model path

Edit `FIRE_MODEL_PATH` in `smart_fire_system/config.py`.

### Change UI overlays

Edit `smart_fire_system/vision/draw.py` or the display section of `smart_fire_system/runtime.py`.

### Change Arduino command behavior

Edit `smart_fire_system/control/arduino.py`.

## Safety Notes

- The detection thread should never wait for servo movement.
- The action loop should never recalculate a locked fire target while that fire remains active.
- Pump shutdown and emergency stop should stay high priority.
- Always test servo directions with the pump disabled first.
- If the turret moves opposite the expected direction, adjust `INVERT_PAN_X` or `INVERT_TILT_Y` in `config.py`.
