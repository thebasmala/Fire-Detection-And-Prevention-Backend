from __future__ import annotations

import os

DEBUG = True

FIRE_MODEL_PATH = "/home/pi/smart_fire_system/models/fire_smoke/fire.hef"
CONFIDENCE_THRESHOLD = MIN_THRESHOLD = 0.60
LOG_FILE = "/home/pi/smart_fire_system/detections_output.jsonl"
FIRE_FRAMES_DIR = "/home/pi/smart_fire_system/fire_frames"
SERIAL_PORT = "/dev/ttyUSB0"
BAUDRATE = 9600

ARDUINO_DUAL_SERVO_PAN_TILT = False
PUMP_USES_LASER_LINES = False
# Laser reference: always command LASER_ON at boot; never send LASER_OFF when pump uses separate lines.
LASER_ALWAYS_ON = True
# Keep pump relay/command ON for entire run; ignore set_pump(False) unless force=True (shutdown / estop).
PUMP_ALWAYS_ON = True
# Cumulative stepper sum when turret is at physical origin (grid cell 3,3).
ARDUINO_INITIAL_STEPPER_CUMULATIVE = 0
# 20 Hz motor update rate  (50 ms between serial command batches).
ARDUINO_AIM_MIN_INTERVAL_S = 0.05
# Max stepper steps per tick when homing to origin (limits home-run speed).
IDLE_HOME_MAX_STEPPER_DELTA = 8

# Hybrid: run Hailo at most every N ms and/or every N frames (IDLE only — see behavior cycle).
DETECTION_MIN_INTERVAL_S = 0.22
DETECTION_FRAME_STRIDE = 2

# --- 3-state machine: IDLE → TARGETING → MONITORING ---
# Consecutive valid frames required before a fire becomes active.
FIRE_ACTIVE_CONFIRM_FRAMES = 2
# Consecutive missing frames required before an active fire is extinguished.
FIRE_EXTINGUISH_MISSING_FRAMES = 10
# Pixel radius used to keep the same ID across frames.
FIRE_TRACK_MATCH_RADIUS_PX = 40.0
# Backward-compatible name for older modules.
IDLE_FIRE_CONFIRM_FRAMES = FIRE_ACTIVE_CONFIRM_FRAMES
# Safety: abandon tracking and return home if this many seconds elapse.
TRACKING_MAX_SEC = 30.0
# Frames geometrically "on target" before pump engages during TRACKING.
TRACKING_SETTLED_STREAK_FRAMES = 6
# Consecutive frames at origin (±2°) before leaving RESET → IDLE.
RESET_ORIGIN_STREAK_FRAMES = 5
# After returning to origin, block new Hailo runs until this elapses.
DETECTION_COOLDOWN_SEC = 2.0
# Reject tiny / edge false positives (pixels).
DETECTION_MIN_BOX_AREA_PX = 100
DETECTION_EDGE_MARGIN_PX = 20
CYCLE_LOCK_MIN_CONFIDENCE = 0.60

EXPECTED_FRAME_W = 640
EXPECTED_FRAME_H = 480
FRAME_MIRROR_X = False
USE_SCALER_CROP = False
SCALER_CROP_RECT = (0, 0, 3280, 2464)
HAILO_FIRE_RAW_BOX_PRINTS = 5

SERVO_Y_MIN, SERVO_Y_MAX, SERVO_Y_CENTER = 0, 180, 90
SERVO_X_MIN, SERVO_X_MAX, SERVO_X_CENTER = 0, 360, 90
PAN_DEG_PER_PX = 0.22
PAN_DEG_SIGN = -1.0
PAN_SENSITIVITY = 0.06
TILT_SENSITIVITY = 0.08
PAN_STEPS_MIN, PAN_STEPS_MAX = -20, 20
INVERT_PAN_X = False
INVERT_TILT_Y = False
# Pixel error below which the turret will NOT move (suppresses micro-jitter).
CENTER_DEAD_ZONE_PX_X, CENTER_DEAD_ZONE_PX_Y = 10, 10

# 5×5 workspace calibration (see smart_fire_system/calibration/mapper.py)
CALIBRATION_DEBUG = False
# Print grid cell + motor interpolation on every aiming frame.
CALIBRATION_MODE = False

# EMA alpha for motor-space target smoothing inside ActiveFireTracker.
# (REMOVED: Calibration is now purely deterministic)
# Max stepper steps per 50 ms tick (limits max pan speed).
CALIB_MAX_PAN_DELTA_PER_FRAME = 6
# Max servo degrees per 50 ms tick (limits max tilt speed).
CALIB_MAX_SERVO_DELTA_PER_FRAME = 3
# Dead zone in grid units around centre cell — fire considered centred.
CALIB_GRID_DEAD_ZONE = 0.20
# Cumulative stepper sum when turret is at physical origin (grid cell 3,3).
CALIB_STEPPER_CUMULATIVE_AT_ORIGIN = 0

# Pump: require this many consecutive "stable track" frames before enabling (reduces false triggers)
PUMP_MIN_STABLE_FRAMES = 5

# EMA alpha for pixel-space detection filter (StableTargetFilter).
# Formula: smoothed = alpha * prev + (1-alpha) * new_raw  (alpha=0.70 → strong noise rejection).
AIM_SMOOTH_ALPHA = 0.70
# Ignored by new filter (kept for API compatibility).
AIM_VELOCITY_DAMP = 0.0
# Pixel jitter below which detection position is not updated.
AIM_MICRO_PX = 4.0
# Pixels jump considered a target switch; filter resets.
AIM_MAX_DELTA_PX = 120.0
AIM_DEAD_ZONE_NORM, MIN_AIM_INTERVAL_S = 0.02, 0.2
AIM_IMMEDIATE_ERR_PX, AIM_FORCE_INTERVAL_S, DEAD_ZONE_PX = 44.0, 0.22, 14
# Minimum detection confidence to command motors.
AIM_MIN_CONFIDENCE = 0.60

SERIAL_QUEUE_MAX = 4
FIRE_PUMP_COOLDOWN_SEC = 2.5
MAX_FRAME_SAVE_INTERVAL_S = 1.0

FIRE_SMOKE_LABELS = {0: "FIRE", 1: "SMOKE"}

# ---------------------------------------------------------------------------
# HSV + motion fire validation  (fire_validator.py)
# ---------------------------------------------------------------------------
# HSV bright fire colour range (H, S, V lower and upper).
HSV_FIRE_H_LOW, HSV_FIRE_H_HIGH = 0, 35
HSV_FIRE_S_LOW, HSV_FIRE_S_HIGH = 80, 255
HSV_FIRE_V_LOW, HSV_FIRE_V_HIGH = 180, 255
# Extended HSV range for dim/candle flames (secondary mask ORed with primary).
HSV_DIM_H_LOW1, HSV_DIM_H_HIGH1 = 0, 15
HSV_DIM_H_LOW2, HSV_DIM_H_HIGH2 = 160, 180
HSV_DIM_S_LOW, HSV_DIM_S_HIGH = 50, 255
HSV_DIM_V_LOW, HSV_DIM_V_HIGH = 100, 255
# Minimum ratio of fire-coloured pixels in the bounding-box ROI.
HSV_MIN_FIRE_RATIO = 0.05
# Motion detection: absolute-difference threshold and min ratio.
MOTION_DIFF_THRESHOLD = 25
MOTION_MIN_RATIO = 0.02
# Temporal consistency: fire must be valid in at least N of the last M frames.
TEMPORAL_REQUIRED_FRAMES = 2
TEMPORAL_WINDOW_SIZE = 3
# Jitter freeze duration (seconds) — freeze servo if oscillation detected.
JITTER_FREEZE_SEC = 0.20
# Origin tolerance in degrees for RESET state (±2°).
ORIGIN_TOLERANCE_DEG = 2

# ---------------------------------------------------------------------------
# Fire lock + fast-acquire behaviour
# ---------------------------------------------------------------------------
# Consecutive frames with NO fire before releasing the locked target.
# While locked, the servo targets the initial snapped EnvironmentMap point.
FIRE_LOCK_LOSS_FRAMES = FIRE_EXTINGUISH_MISSING_FRAMES
# Easing factor during ACQUIRE phase (faster initial lock-on).
# Normal EASE = 0.15 (slow gimbal feel).  Acquire = 0.40 (snappy lock-on).
ACQUIRE_SERVO_EASE = 0.40
# Distance in degrees at which ACQUIRE phase switches to STABILIZE phase.
ACQUIRE_DISTANCE_DEG = 8

# ---------------------------------------------------------------------------
# Industrial-grade servo precision control
# ---------------------------------------------------------------------------
# Motion Prediction Latency Compensation (frames)
LATENCY_COMP_FRAMES = 1.5
# Proportional gain (Kp): servo_step = error * Kp
SERVO_K_ACQUIRE = 0.50    # COARSE phase (error > ACQUIRE_DISTANCE_DEG)
SERVO_K_PRECISION = 0.20  # PRECISION phase (error <= ACQUIRE_DISTANCE_DEG)
# Derivative gain (Kd): damping based on velocity (error - prev_error)
SERVO_KD_ACQUIRE = 0.10
SERVO_KD_PRECISION = 0.30
# Maximum servo degrees/frame per phase.
SERVO_MAX_DELTA_ACQUIRE = 6
SERVO_MAX_DELTA_PRECISION = 2
# Maximum stepper steps/frame per phase.
STEPPER_MAX_DELTA_ACQUIRE = 10
STEPPER_MAX_DELTA_PRECISION = 4
# Pixel jump threshold for noise rejection (reject jumps > this unless sustained).
NOISE_JUMP_THRESHOLD_PX = 25.0
# Frames a large jump must sustain before being accepted (prevents spikes).
NOISE_JUMP_SUSTAIN_FRAMES = 3
# Fire lock fine-tracking zone: allow micro-adjustment within ±N pixels.
FIRE_LOCK_FINE_ZONE_PX = 5.0

# ---------------------------------------------------------------------------
# Final precision: micro-correction, settling, backlash, bias learning
# ---------------------------------------------------------------------------
# Micro-correction loop: when abs(error) <= MICRO_THRESHOLD_DEG,
# apply correction = error * MICRO_K, clamped to ±MICRO_MAX_DEG.
MICRO_CORRECTION_THRESHOLD_DEG = 2.0
MICRO_CORRECTION_K = 0.15
MICRO_CORRECTION_MAX_DEG = 0.5
# Final deadzone: if abs(error) < this, do NOT move servo at all.
FINAL_DEADZONE_DEG = 1.0
# Settling hold: after reaching near-target, hold for this duration (seconds).
# During hold only micro-corrections are allowed.
SETTLING_HOLD_SEC = 0.20
# Settled lock freeze: if error < 1.0 deg for N frames, freeze ALL corrections.
# This prevents feedback loops and over-correction bounce from physical backlash.
SETTLED_LOCK_FREEZE_FRAMES = 5
SETTLED_LOCK_FREEZE_SEC = 0.20
# Backlash compensation: offset applied on direction reversal (degrees).
BACKLASH_COMP_DEG = 1.0
# Calibration bias learning: per-zone bias updated slowly.
# bias = bias * DECAY + error * LEARN_RATE
BIAS_DECAY = 0.98
BIAS_LEARN_RATE = 0.02
BIAS_MAX_DEG = 2.0

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(FIRE_FRAMES_DIR, exist_ok=True)


MQTT_ENABLED = True
MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC_FIRE = "camera/pi"
MQTT_QOS = 1
MQTT_DEVICE_ID = 1
MQTT_CAMERA_ID = 1

# Built-in MJPEG server (single camera owner mode).
# Keep this enabled when running smart_fire_main.py so you do not need a second
# video_stream_server.py process competing for the same camera.
ENABLE_MJPEG_STREAM = True
MJPEG_STREAM_HOST = "0.0.0.0"
MJPEG_STREAM_PORT = 5000
MJPEG_JPEG_QUALITY = 85

# Backend frame upload (real public URL for backend video_url)
# BACKEND_BASE_URL = "http://192.168.100.4:8000"
BACKEND_BASE_URL = "http://Basmala.local:8000"
FIRE_FRAME_UPLOAD_API_KEY = "f7k2m9x4p1q8w3n6j5r0t2y8u1v4z9s"

# Alert dedupe/throttle:
# send first event, then resend only if zone/confidence changed
# or after cooldown seconds.
FIRE_EVENT_MIN_SEND_INTERVAL_SEC = 20.0
FIRE_EVENT_MIN_CONF_DELTA = 0.08
