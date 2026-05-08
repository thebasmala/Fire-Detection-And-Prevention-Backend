"""Threaded fire detection runtime with locked-target action states."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
from picamera2 import Picamera2

from smart_fire_system.behavior.cycle import CycleState, at_origin_stepper_servo, tracking_settled
from smart_fire_system.calibration.mapper import CalibrationMapper
from smart_fire_system.config import *
from smart_fire_system.control.arduino import ArduinoController
from smart_fire_system.detection.hailo_detector import HailoDetector
from smart_fire_system.tracking.fire_state import ConfidenceFireTracker, FireTrack, LockedFireTarget
from smart_fire_system.tracking.tracker import CenteringCommand
from smart_fire_system.vision.draw import (
    COLOR_FIRE,
    COLOR_FPS,
    cxcy_to_zone,
    draw_aim_debug_hud,
    draw_crosshair,
    draw_detections,
    draw_zones,
)
from smart_fire_system.runtime_direct_mqtt_helper import (
    FireEventRuntimePublisher,
    save_fire_frame,
    to_iso_datetime,
)


@dataclass(frozen=True)
class DetectionSnapshot:
    frame_id: int
    timestamp: float
    frame: object
    frame_w: int
    frame_h: int
    detections: tuple[dict, ...]
    active_fires: tuple[FireTrack, ...]
    activated_ids: tuple[int, ...]
    extinguished_ids: tuple[int, ...]
    infer_ms: float
    raw_fire_count: int
    event_seq: int


class _MjpegState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame_bytes: bytes | None = None

    def set_frame(self, frame_bytes: bytes) -> None:
        with self._lock:
            self._frame_bytes = frame_bytes

    def get_frame(self) -> bytes | None:
        with self._lock:
            return self._frame_bytes


class _MjpegServer:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._state = _MjpegState()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        state = self._state

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path in ("/health", "/health/"):
                    payload = json.dumps({"status": "healthy", "camera_available": True}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return

                if self.path not in ("/video_feed", "/video_feed/"):
                    self.send_response(404)
                    self.end_headers()
                    return

                self.send_response(200)
                self.send_header("Age", "0")
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()

                while True:
                    frame = state.get_frame()
                    if frame is not None:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                    time.sleep(0.05)

            def log_message(self, _fmt: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((self._host, self._port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="mjpeg-server", daemon=True)
        self._thread.start()
        print(f"[MJPEG] Stream server running on http://{self._host}:{self._port}/video_feed")

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None

    def publish_frame(self, frame_bgr: object) -> None:
        ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, MJPEG_JPEG_QUALITY])
        if ok:
            self._state.set_frame(buf.tobytes())


def _build_arduino() -> ArduinoController:
    return ArduinoController(
        SERIAL_PORT,
        BAUDRATE,
        serial_queue_max=SERIAL_QUEUE_MAX,
        dual_servo_mode=ARDUINO_DUAL_SERVO_PAN_TILT,
        servo_x_min=SERVO_X_MIN,
        servo_x_max=SERVO_X_MAX,
        servo_y_min=SERVO_Y_MIN,
        servo_y_max=SERVO_Y_MAX,
        pump_uses_laser_lines=PUMP_USES_LASER_LINES,
        laser_always_on=LASER_ALWAYS_ON,
        pump_always_on=PUMP_ALWAYS_ON,
        initial_stepper_cumulative=ARDUINO_INITIAL_STEPPER_CUMULATIVE,
        aim_min_interval_s=ARDUINO_AIM_MIN_INTERVAL_S,
        max_home_stepper_delta_per_frame=IDLE_HOME_MAX_STEPPER_DELTA,
        jitter_freeze_sec=JITTER_FREEZE_SEC,
        acquire_ease=ACQUIRE_SERVO_EASE,
        acquire_distance_deg=ACQUIRE_DISTANCE_DEG,
        k_acquire=SERVO_K_ACQUIRE,
        k_precision=SERVO_K_PRECISION,
        max_delta_acquire=SERVO_MAX_DELTA_ACQUIRE,
        max_delta_precision=SERVO_MAX_DELTA_PRECISION,
        stepper_max_delta_acquire=STEPPER_MAX_DELTA_ACQUIRE,
        stepper_max_delta_precision=STEPPER_MAX_DELTA_PRECISION,
        micro_correction_threshold=MICRO_CORRECTION_THRESHOLD_DEG,
        micro_correction_k=MICRO_CORRECTION_K,
        micro_correction_max=MICRO_CORRECTION_MAX_DEG,
        final_deadzone_deg=FINAL_DEADZONE_DEG,
        settling_hold_sec=SETTLING_HOLD_SEC,
        settled_lock_freeze_frames=SETTLED_LOCK_FREEZE_FRAMES,
        settled_lock_freeze_sec=SETTLED_LOCK_FREEZE_SEC,
        backlash_comp_deg=BACKLASH_COMP_DEG,
        debug=DEBUG,
    )


def _frame_ok(frame: object) -> bool:
    return frame is not None and hasattr(frame, "shape") and len(frame.shape) >= 2


def _raw_fire_detections(detections: list[dict]) -> list[dict]:
    """Keep only raw model FIRE detections. No HSV, motion, area, or edge filters."""
    return [det for det in detections if FIRE_SMOKE_LABELS.get(det.get("class_id")) == "FIRE"]


def _origin_ok(arduino: ArduinoController, origin_stepper: int) -> bool:
    return at_origin_stepper_servo(
        dual_servo_mode=ARDUINO_DUAL_SERVO_PAN_TILT,
        stepper_position=arduino.stepper_position,
        stepper_target=origin_stepper,
        servo_x=arduino.last_servo_x,
        servo_y=arduino.last_servo_y,
        servo_x_target=SERVO_X_CENTER,
        servo_y_target=SERVO_Y_CENTER,
    )


def _target_command(target: LockedFireTarget, arduino: ArduinoController, origin_stepper: int) -> CenteringCommand:
    servo_y = max(SERVO_Y_MIN, min(SERVO_Y_MAX, int(round(target.servo_y_deg))))
    if ARDUINO_DUAL_SERVO_PAN_TILT:
        servo_x = max(SERVO_X_MIN, min(SERVO_X_MAX, int(round(target.servo_x_deg))))
        return CenteringCommand(servoy_angle=servo_y, servox_angle=servo_x, pan_steps=0)

    stepper_offset = float(arduino.stepper_position) - float(origin_stepper)
    pan_steps = int(round(target.pan_abs - stepper_offset))
    pan_steps = max(PAN_STEPS_MIN, min(PAN_STEPS_MAX, pan_steps))
    return CenteringCommand(servoy_angle=servo_y, servox_angle=SERVO_X_CENTER, pan_steps=pan_steps)


def _target_settled(target: LockedFireTarget, arduino: ArduinoController, origin_stepper: int) -> bool:
    return tracking_settled(
        pan_abs=target.pan_abs,
        servo_f=target.servo_y_deg,
        stepper_position=arduino.stepper_position,
        step_at_origin=origin_stepper,
        servo_y=arduino.last_servo_y,
        servo_y_center=SERVO_Y_CENTER,
        dual_servo_mode=ARDUINO_DUAL_SERVO_PAN_TILT,
        servo_x=arduino.last_servo_x,
        servo_x_center=SERVO_X_CENTER,
        servo_x_min=SERVO_X_MIN,
        servo_x_max=SERVO_X_MAX,
    )


def _select_active_fire(active_fires: tuple[FireTrack, ...]) -> FireTrack | None:
    if not active_fires:
        return None
    return max(active_fires, key=lambda track: (track.confidence, track.hit_count))


def main() -> None:
    detector = HailoDetector(
        FIRE_MODEL_PATH,
        FIRE_SMOKE_LABELS,
        MIN_THRESHOLD,
        HAILO_FIRE_RAW_BOX_PRINTS,
        DEBUG,
        min_infer_interval_s=0.0,
        infer_frame_stride=1,
    )
    arduino = _build_arduino()
    mapper = CalibrationMapper(debug=CALIBRATION_DEBUG, calibration_mode=CALIBRATION_MODE)
    confidence_tracker = ConfidenceFireTracker(
        mapper=mapper,
        active_frames=FIRE_ACTIVE_CONFIRM_FRAMES,
        extinguish_frames=FIRE_EXTINGUISH_MISSING_FRAMES,
        match_radius_px=FIRE_TRACK_MATCH_RADIUS_PX,
        invert_pan_x=INVERT_PAN_X,
        invert_tilt_y=INVERT_TILT_Y,
        servo_x_center=SERVO_X_CENTER,
    )

    cam = Picamera2()
    cfg = cam.create_preview_configuration(
        main={"format": "RGB888", "size": (EXPECTED_FRAME_W, EXPECTED_FRAME_H)}
    )
    if USE_SCALER_CROP:
        cfg["scaler_crop"] = SCALER_CROP_RECT
    cam.configure(cfg)
    cam.start()
    time.sleep(1)

    latest_lock = threading.Lock()
    tracker_lock = threading.Lock()
    stop_event = threading.Event()
    accept_new_targets = threading.Event()
    accept_new_targets.set()
    latest_snapshot: DetectionSnapshot | None = None
    event_seq = 0
    mjpeg_server = _MjpegServer(MJPEG_STREAM_HOST, MJPEG_STREAM_PORT) if ENABLE_MJPEG_STREAM else None
    if mjpeg_server is not None:
        mjpeg_server.start()

    def detection_loop() -> None:
        nonlocal latest_snapshot, event_seq
        frame_id = 0
        warned_size = False

        while not stop_event.is_set():
            try:
                frame = cam.capture_array()
            except Exception as exc:
                print(f"[Camera] Capture error: {exc}")
                time.sleep(0.03)
                continue

            if not _frame_ok(frame):
                print("[CAMERA] CAMERA PIPELINE BROKEN - frame is None or invalid")
                time.sleep(0.03)
                continue

            if FRAME_MIRROR_X:
                frame = cv2.flip(frame, 1)

            timestamp = time.time()
            frame_id += 1
            frame_h, frame_w = frame.shape[:2]
            if not warned_size and (frame_w != EXPECTED_FRAME_W or frame_h != EXPECTED_FRAME_H):
                print(f"[Camera] WARNING: got {frame_w}x{frame_h}, expected {EXPECTED_FRAME_W}x{EXPECTED_FRAME_H}.")
                warned_size = True

            detections = detector.process_frame(frame, timestamp=timestamp)
            raw_fire_detections = _raw_fire_detections(detections)
            with tracker_lock:
                if accept_new_targets.is_set():
                    active_fires, activated_ids, extinguished_ids = confidence_tracker.update(
                        raw_fire_detections,
                        frame_w=frame_w,
                        frame_h=frame_h,
                    )
                else:
                    confidence_tracker.reset()
                    active_fires = ()
                    activated_ids = ()
                    extinguished_ids = ()
            if activated_ids or extinguished_ids:
                event_seq += 1

            snapshot = DetectionSnapshot(
                frame_id=frame_id,
                timestamp=timestamp,
                frame=frame.copy(),
                frame_w=frame_w,
                frame_h=frame_h,
                detections=tuple(detections),
                active_fires=active_fires,
                activated_ids=activated_ids,
                extinguished_ids=extinguished_ids,
                infer_ms=detector.last_infer_ms,
                raw_fire_count=len(raw_fire_detections),
                event_seq=event_seq,
            )
            with latest_lock:
                latest_snapshot = snapshot

    worker = threading.Thread(target=detection_loop, name="fire-detection-loop", daemon=True)
    worker.start()

    cycle_state = CycleState.IDLE
    origin_stepper = CALIB_STEPPER_CUMULATIVE_AT_ORIGIN
    current_fire_id: int | None = None
    current_target: LockedFireTarget | None = None
    idle_cooldown_until = 0.0
    last_event_seq = -1
    status_text = "IDLE"
    status_until = 0.0
    pump_engaged = bool(PUMP_ALWAYS_ON)
    prev_time = time.time()
    ui_enabled = bool(os.environ.get("DISPLAY"))
    fire_event_publisher = FireEventRuntimePublisher(
        backend_base_url=BACKEND_BASE_URL,
        upload_api_key=FIRE_FRAME_UPLOAD_API_KEY,
        min_send_interval_sec=FIRE_EVENT_MIN_SEND_INTERVAL_SEC,
        min_conf_delta_to_resend=FIRE_EVENT_MIN_CONF_DELTA,
    )

    def set_pump(on: bool, *, force: bool = False) -> None:
        nonlocal pump_engaged
        arduino.set_pump(on, force=force)
        pump_engaged = on if (on or force or not PUMP_ALWAYS_ON) else True

    def handle_extinguished() -> None:
        nonlocal cycle_state, current_fire_id, current_target, idle_cooldown_until, status_text, status_until
        print("[Cycle] FIRE EXTINGUISHED - returning to origin")
        accept_new_targets.clear()
        with tracker_lock:
            confidence_tracker.reset()
        set_pump(False)
        arduino.set_zone(0)
        current_fire_id = None
        current_target = None
        cycle_state = CycleState.IDLE
        idle_cooldown_until = time.time() + DETECTION_COOLDOWN_SEC
        status_text = "FIRE EXTINGUISHED"
        status_until = time.time() + 3.0

    print("\nSmart Fire System - threaded detection with IDLE -> TARGETING -> MONITORING states. 'q' quit, 'e' estop.\n")

    try:
        while True:
            with latest_lock:
                snapshot = latest_snapshot

            now = time.time()
            if snapshot is None:
                arduino.go_to_origin(origin_stepper, SERVO_Y_CENTER, SERVO_X_CENTER)
                time.sleep(0.01)
                continue

            current_fire = None
            if current_fire_id is not None:
                current_fire = next((track for track in snapshot.active_fires if track.id == current_fire_id), None)

            if snapshot.event_seq != last_event_seq:
                last_event_seq = snapshot.event_seq
                if current_fire_id is not None and current_fire_id in snapshot.extinguished_ids:
                    handle_extinguished()
                    current_fire = None

            if cycle_state == CycleState.IDLE:
                set_pump(False)
                arduino.go_to_origin(origin_stepper, SERVO_Y_CENTER, SERVO_X_CENTER)
                at_origin = _origin_ok(arduino, origin_stepper)
                if at_origin and now >= idle_cooldown_until:
                    if not accept_new_targets.is_set():
                        with tracker_lock:
                            confidence_tracker.reset()
                        accept_new_targets.set()
                        print("[Cycle] Origin reached - accepting next fire detection")
                    selected = _select_active_fire(snapshot.active_fires)
                    if selected is not None and selected.locked_target is not None:
                        current_fire_id = selected.id
                        current_target = selected.locked_target
                        cycle_state = CycleState.TARGETING
                        status_text = "ACTIVE FIRE DETECTED"
                        status_until = 0.0
                        zone = cxcy_to_zone(*selected.centroid, snapshot.frame_w, snapshot.frame_h)
                        frame_path = save_fire_frame(snapshot.frame, FIRE_FRAMES_DIR, snapshot.frame_id)
                        dateandtime = to_iso_datetime(snapshot.timestamp)
                        fire_event_publisher.send_if_needed(
                            broker_host=MQTT_BROKER_HOST,
                            broker_port=MQTT_BROKER_PORT,
                            topic=MQTT_TOPIC_FIRE,
                            qos=MQTT_QOS,
                            confidence=float(selected.confidence),
                            frame_id=snapshot.frame_id,
                            zone=int(zone),
                            frame_path=frame_path,
                            dateandtime=dateandtime,
                            device_id=MQTT_DEVICE_ID,
                            camera_id=MQTT_CAMERA_ID,
                            now_ts=snapshot.timestamp,
                        )
                        print(
                            f"[Cycle] ACTIVE FIRE DETECTED id={selected.id} "
                            f"map=({current_target.map_x:.0f},{current_target.map_y:.0f}) "
                            f"pan={current_target.pan_abs:.1f} servo_y={current_target.servo_y_deg:.1f}"
                        )
                elif not at_origin:
                    accept_new_targets.clear()

            elif cycle_state == CycleState.TARGETING:
                if current_target is None or current_fire is None:
                    handle_extinguished()
                else:
                    arduino.set_zone(cxcy_to_zone(*current_fire.centroid, snapshot.frame_w, snapshot.frame_h))
                    arduino.aim_from_command(_target_command(current_target, arduino, origin_stepper), acquire_mode=True)
                    if _target_settled(current_target, arduino, origin_stepper):
                        cycle_state = CycleState.MONITORING
                        print(f"[Cycle] TARGETING -> MONITORING id={current_fire_id}")

            elif cycle_state == CycleState.MONITORING:
                if current_target is None or current_fire is None:
                    handle_extinguished()
                else:
                    arduino.aim_from_command(_target_command(current_target, arduino, origin_stepper), acquire_mode=False)
                    set_pump(True)

            frame = snapshot.frame.copy()
            draw_zones(
                frame,
                snapshot.frame_w,
                snapshot.frame_h,
                cxcy_to_zone(*current_fire.centroid, snapshot.frame_w, snapshot.frame_h)
                if current_fire is not None else 0,
            )
            draw_crosshair(frame, snapshot.frame_w, snapshot.frame_h)
            if snapshot.detections:
                draw_detections(frame, list(snapshot.detections), FIRE_SMOKE_LABELS, COLOR_FIRE)
            if current_fire is not None:
                cx, cy = current_fire.centroid
                cv2.drawMarker(frame, (int(round(cx)), int(round(cy))), (0, 0, 255), cv2.MARKER_CROSS, 24, 2)
                cmd = _target_command(current_target, arduino, origin_stepper) if current_target is not None else None
                if cmd is not None:
                    draw_aim_debug_hud(
                        frame,
                        cx=cx,
                        cy=cy,
                        frame_w=snapshot.frame_w,
                        frame_h=snapshot.frame_h,
                        zone=cxcy_to_zone(cx, cy, snapshot.frame_w, snapshot.frame_h),
                        servox_cmd=cmd.servox_angle,
                        servoy_cmd=cmd.servoy_angle,
                        pan_steps_cmd=cmd.pan_steps,
                        stepper_sum=arduino.stepper_position,
                        servox_sent=arduino.last_servo_x,
                        servoy_sent=arduino.last_servo_y,
                        conf=current_fire.confidence,
                        mirror_x=FRAME_MIRROR_X,
                        pump_on=pump_engaged,
                        dual_servo_mode=ARDUINO_DUAL_SERVO_PAN_TILT,
                    )

            fps_now = time.time()
            fps = 1.0 / max(fps_now - prev_time, 1e-6)
            prev_time = fps_now
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_FPS, 2)
            cv2.putText(
                frame,
                f"INF: {snapshot.infer_ms:.1f}ms RAW_FIRE:{snapshot.raw_fire_count}",
                (10, 56),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                COLOR_FPS,
                1,
            )
            visible_status = status_text if status_until == 0.0 or now < status_until else cycle_state.value
            cv2.putText(frame, visible_status, (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
            cv2.putText(frame, f"STATE: {cycle_state.value}", (10, 104), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 180, 0), 2)
            if mjpeg_server is not None:
                mjpeg_server.publish_frame(frame)

            key = 0xFF
            if ui_enabled:
                try:
                    cv2.imshow("Smart Fire Detection System", frame)
                    key = cv2.waitKey(1) & 0xFF
                except Exception as exc:
                    print(f"[Display] UI error: {exc}")
                    ui_enabled = False

            if key == ord("q"):
                break
            if key == ord("e"):
                print("[System] Emergency stop: pump off, origin, shutdown.")
                set_pump(False, force=True)
                arduino.reset()
                break

            print(
                f"[DEBUG] state={cycle_state.value} fire_id={current_fire_id if current_fire_id is not None else '-'} "
                f"active={len(snapshot.active_fires)} det={len(snapshot.detections)} "
                f"raw_fire={snapshot.raw_fire_count} accepting={int(accept_new_targets.is_set())} "
                f"servo_y={arduino.last_servo_y if arduino.last_servo_y is not None else SERVO_Y_CENTER}"
            )
            time.sleep(0.005)

    finally:
        print("\n[System] Shutting down...")
        stop_event.set()
        worker.join(timeout=2.0)
        set_pump(False, force=True)
        arduino.close()
        if mjpeg_server is not None:
            mjpeg_server.stop()
        cam.stop()
        if ui_enabled:
            cv2.destroyAllWindows()
        print("[System] Done.")
