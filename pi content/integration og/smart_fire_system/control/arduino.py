"""
ArduinoController — serial communication layer with professional motion control.

Motion control design
---------------------
All motor targets are maintained as continuous floating-point "interpolated"
positions.  Every time a new aim target arrives, the interpolated position
is updated toward that target with a configurable easing factor:

    interp += (target - interp) * ease

This creates the "camera-gimbal" feel: fast initial movement, graceful
deceleration as the turret approaches the target.

Commands are only enqueued to the Arduino when:
  1. The rate-limiting interval has elapsed (default 50 ms -> 20 Hz).
  2. The rounded, clamped motor value differs from the last sent value by
     at least the deadband threshold (2 deg servo, 5 steps stepper).

Jitter prevention
-----------------
A direction-change counter tracks servo oscillation.  If the servo reverses
direction within +/- 2 deg for 3+ consecutive commands, the position is
frozen for 200 ms (configurable via JITTER_FREEZE_SEC in config).
"""
from __future__ import annotations

import queue
import threading
import time

import serial


def format_stepper_command(steps: int) -> str:
    n = int(steps)
    if n == 0:
        return ""
    return f"X {n}" if n > 0 else f"X{n}"


class ArduinoController:
    EASE = 0.15
    SERVO_DEADBAND_DEG  = 2
    STEPPER_DEADBAND_ST = 5

    def __init__(
        self,
        port: str,
        baudrate: int,
        *,
        serial_queue_max: int,
        dual_servo_mode: bool,
        servo_x_min: int,
        servo_x_max: int,
        servo_y_min: int,
        servo_y_max: int,
        pump_uses_laser_lines: bool,
        laser_always_on: bool = True,
        pump_always_on: bool = False,
        initial_stepper_cumulative: int = 0,
        aim_min_interval_s: float = 0.05,
        max_home_stepper_delta_per_frame: int = 12,
        reconnect_cooldown_s: float = 1.0,
        jitter_freeze_sec: float = 0.20,
        acquire_ease: float = 0.40,
        acquire_distance_deg: float = 8.0,
        k_acquire: float = 0.50,
        k_precision: float = 0.20,
        kd_acquire: float = 0.10,
        kd_precision: float = 0.30,
        max_delta_acquire: int = 6,
        max_delta_precision: int = 2,
        stepper_max_delta_acquire: int = 10,
        stepper_max_delta_precision: int = 4,
        micro_correction_threshold: float = 2.0,
        micro_correction_k: float = 0.15,
        micro_correction_max: float = 1.0,
        final_deadzone_deg: float = 0.8,
        settling_hold_sec: float = 0.20,
        settled_lock_freeze_frames: int = 5,
        settled_lock_freeze_sec: float = 0.20,
        backlash_comp_deg: float = 1.0,
        debug: bool = True,
    ):
        self._dry_run      = False
        self._port         = port
        self._baudrate     = int(baudrate)
        self._dual_servo   = bool(dual_servo_mode)
        self._sv_x_min     = int(servo_x_min)
        self._sv_x_max     = int(servo_x_max)
        self._sv_y_min     = int(servo_y_min)
        self._sv_y_max     = int(servo_y_max)
        self._pump_laser   = bool(pump_uses_laser_lines)
        self._laser_on     = bool(laser_always_on)
        self._pump_always  = bool(pump_always_on)
        self._step_origin  = int(initial_stepper_cumulative)
        self._reconnect_cd = float(reconnect_cooldown_s)
        self._last_reconnect = 0.0
        self.debug         = bool(debug)
        self._acquire_ease = float(acquire_ease)
        self._acquire_dist = float(acquire_distance_deg)
        self._k_acq        = float(k_acquire)
        self._k_prec       = float(k_precision)
        self._kd_acq       = float(kd_acquire)
        self._kd_prec      = float(kd_precision)
        self._max_d_acq    = int(max_delta_acquire)
        self._max_d_prec   = int(max_delta_precision)
        self._stp_max_acq  = int(stepper_max_delta_acquire)
        self._stp_max_prec = int(stepper_max_delta_precision)
        # Micro-correction parameters
        self._micro_thresh = float(micro_correction_threshold)
        self._micro_k      = float(micro_correction_k)
        self._micro_max    = float(micro_correction_max)
        self._final_dz     = float(final_deadzone_deg)
        self._settle_sec   = float(settling_hold_sec)
        self._lock_frz_frames = int(settled_lock_freeze_frames)
        self._lock_frz_sec = float(settled_lock_freeze_sec)
        self._backlash     = float(backlash_comp_deg)

        self.ser = None
        self._connect_serial()

        self._sent_sv_x: int | None = None
        self._sent_sv_y: int | None = None
        self._sent_steps: int       = int(initial_stepper_cumulative)

        self._interp_sv_x:  float = 90.0
        self._interp_sv_y:  float = 90.0
        self._interp_steps: float = float(initial_stepper_cumulative)

        self._last_zone:    int   = 0
        self._pump_hw:      bool  = False
        self._laser_warned: bool  = False
        self.last_serial_latency_ms: float = 0.0
        self._last_aim_ts:  float = 0.0
        self._aim_interval: float = float(aim_min_interval_s)
        self._max_home_step: int  = int(max(1, max_home_stepper_delta_per_frame))

        # Jitter detection state
        self._jitter_freeze_sec = float(jitter_freeze_sec)
        self._jitter_frozen_until: float = 0.0
        self._last_servo_y_dir: int = 0   # -1, 0, +1
        self._dir_reversal_count: int = 0

        # Backlash compensation state
        self._prev_dir_y: int = 0   # last servo Y movement direction
        self._prev_dir_x: int = 0   # last servo X movement direction
        self._prev_dir_st: int = 0  # last stepper direction

        # Settling state
        self._settling_until: float = 0.0  # timestamp when settling hold expires
        self._consec_settled: int = 0      # frames under 1.0 deg error
        self._lock_freeze_until: float = 0.0 # timestamp when lock freeze expires

        # PD Control State
        self._prev_err_x: float = 0.0
        self._prev_err_y: float = 0.0
        self._prev_err_st: float = 0.0

        # Serial write queue
        self._ser_lock = threading.Lock()
        self._q:  queue.Queue[str | None] = queue.Queue(maxsize=serial_queue_max)
        self._pq: queue.Queue[str | None] = queue.Queue(maxsize=max(2, serial_queue_max // 2))
        self._tx = threading.Thread(target=self._tx_worker, daemon=True)
        self._tx.start()

        self._all_lamps_on(sync=True)
        if self._laser_on:
            self._send_sync("LASER_ON")
        if self._pump_always and not self._pump_laser:
            self.set_pump(True)

    # ======================================================================
    # Serial plumbing
    # ======================================================================
    def _connect_serial(self) -> None:
        print(f"[Arduino] Connecting on {self._port} @ {self._baudrate} baud…")
        try:
            self.ser = serial.Serial(self._port, self._baudrate, timeout=0.05)
            time.sleep(2)
            self.ser.reset_input_buffer()
            welcome = self.ser.readline().decode(errors="ignore").strip()
            print(f"[Arduino] {welcome or '(no welcome message)'}")
            print("[Arduino] Connected.")
            self._dry_run = False
        except serial.SerialException as exc:
            print(f"[Arduino] WARNING: {exc}")
            print("[Arduino] SAFE MODE — no hardware I/O.")
            self.ser        = None
            self._dry_run   = True

    def _try_reconnect(self) -> None:
        now = time.time()
        if now - self._last_reconnect >= self._reconnect_cd:
            self._last_reconnect = now
            self._connect_serial()

    @staticmethod
    def _is_critical(cmd: str) -> bool:
        return cmd == "RESET" or "PUMP_OFF" in cmd

    def _tx_worker(self) -> None:
        while True:
            try:
                line = self._pq.get_nowait()
            except queue.Empty:
                try:
                    line = self._q.get(timeout=0.2)
                except queue.Empty:
                    continue
            if line is None:
                break
            self._send_sync(line)

    def _enqueue(self, cmd: str) -> None:
        if self._dry_run or not cmd:
            if self.debug:
                print(f"  [→ Arduino DRY] {cmd}")
            return
        target = self._pq if self._is_critical(cmd) else self._q
        try:
            target.put_nowait(cmd)
        except queue.Full:
            try:
                target.get_nowait()
            except queue.Empty:
                pass
            try:
                target.put_nowait(cmd)
            except queue.Full:
                pass

    def _send_sync(self, cmd: str) -> None:
        if self.debug:
            print(f"  [→ Arduino] {cmd}")
        if self.ser and self.ser.is_open:
            try:
                t0 = time.time()
                with self._ser_lock:
                    self.ser.write((cmd + "\n").encode())
                    self.ser.flush()
                    time.sleep(0.012)
                    for _ in range(24):
                        if not self.ser.in_waiting:
                            break
                        reply = self.ser.readline().decode(errors="ignore").strip()
                        if reply and self.debug:
                            print(f"  [← Arduino] {reply}")
                self.last_serial_latency_ms = (time.time() - t0) * 1000.0
            except Exception as exc:
                print(f"  [Arduino] Send error: {exc}")
                self._try_reconnect()
        else:
            self._try_reconnect()

    def _batch(self, commands: list[str], sync: bool = False) -> None:
        if not commands:
            return
        seen: set[str] = set()
        dedup: list[str] = []
        for c in commands:
            if c.startswith("LAMP"):
                if c in seen:
                    continue
                seen.add(c)
            dedup.append(c)
        line = dedup[0] if len(dedup) == 1 else "BATCH|" + "|".join(dedup)
        if sync:
            self._send_sync(line)
        else:
            self._enqueue(line)

    # ======================================================================
    # Jitter detection (NEVER blocks completely — 200ms max freeze)
    # ======================================================================
    @property
    def is_jittering(self) -> bool:
        """True if servo is currently in a jitter freeze window (informational only)."""
        return time.time() < self._jitter_frozen_until

    def _check_jitter(self, new_sv_y: int) -> bool:
        """Check for servo oscillation.

        Returns True ONLY during an active 200ms freeze window.
        After the freeze expires, movement is ALWAYS allowed.
        This can NEVER create a deadlock or infinite block.
        """
        now = time.time()

        # If inside active freeze window, block this one command
        if now < self._jitter_frozen_until:
            return True

        # Freeze expired — always allow movement from here
        if self._sent_sv_y is None:
            return False

        delta = new_sv_y - self._sent_sv_y
        if abs(delta) < 2:
            return False  # Micro-change, ignore for jitter tracking

        new_dir = 1 if delta > 0 else -1
        if self._last_servo_y_dir != 0 and new_dir != self._last_servo_y_dir:
            self._dir_reversal_count += 1
        else:
            self._dir_reversal_count = 0

        self._last_servo_y_dir = new_dir

        if self._dir_reversal_count >= 3:
            # Start a NEW freeze — exactly 200ms, then auto-expires
            self._jitter_frozen_until = now + self._jitter_freeze_sec
            self._dir_reversal_count = 0
            if self.debug:
                print(f"[Arduino] Jitter detected — freezing for {self._jitter_freeze_sec * 1000:.0f}ms")
            return True
        return False

    # ======================================================================
    # Zone lamps
    # ======================================================================
    def _all_lamps_on(self, sync: bool = False) -> None:
        self._batch(["LAMP1_ON", "LAMP2_ON", "LAMP3_ON", "LAMP4_ON"], sync=sync)
        self._last_zone = 0

    def set_zone(self, zone: int) -> None:
        if zone == self._last_zone:
            return
        self._last_zone = zone
        if zone == 0:
            self._batch(["LAMP1_ON", "LAMP2_ON", "LAMP3_ON", "LAMP4_ON"])
        else:
            self._batch([f"LAMP{i}_{'OFF' if i == zone else 'ON'}" for i in range(1, 5)])

    # ======================================================================
    # Motion control — CORE
    # ======================================================================
    def _rate_ok(self) -> bool:
        return (time.time() - self._last_aim_ts) >= self._aim_interval

    def _clamp_sv_y(self, v: float) -> int:
        return max(self._sv_y_min, min(self._sv_y_max, int(round(v))))

    def _clamp_sv_x(self, v: float) -> int:
        return max(self._sv_x_min, min(self._sv_x_max, int(round(v))))

    def aim_from_command(self, cmd, *, acquire_mode: bool = False) -> None:
        """Called by app.py with a CenteringCommand.

        If acquire_mode is True, use fast easing for initial lock-on.
        """
        if not self._rate_ok():
            return
        if self._dual_servo:
            self._aim_dual(cmd.servox_angle, cmd.servoy_angle, acquire=acquire_mode)
        else:
            self._aim_stepper_servo(cmd.pan_steps, cmd.servoy_angle, acquire=acquire_mode)
        self._last_aim_ts = time.time()

    def go_to_origin(self, stepper_cumulative_target: int, servo_y: int, servo_x: int) -> None:
        """Smooth return to the origin pose."""
        if not self._rate_ok():
            return

        self._interp_sv_y += (float(servo_y) - self._interp_sv_y) * self.EASE
        if abs(float(servo_y) - self._interp_sv_y) < self.SERVO_DEADBAND_DEG:
            self._interp_sv_y = float(servo_y)
        new_sv_y = self._clamp_sv_y(self._interp_sv_y)

        cmds: list[str] = []

        if self._dual_servo:
            self._interp_sv_x += (float(servo_x) - self._interp_sv_x) * self.EASE
            if abs(float(servo_x) - self._interp_sv_x) < self.SERVO_DEADBAND_DEG:
                self._interp_sv_x = float(servo_x)
            new_sv_x = self._clamp_sv_x(self._interp_sv_x)
            if self._sent_sv_x is None or (new_sv_x != self._sent_sv_x and (new_sv_x == servo_x or abs(new_sv_x - self._sent_sv_x) >= self.SERVO_DEADBAND_DEG)):
                cmds.append(f"SERVOX{new_sv_x}")
                self._sent_sv_x = new_sv_x
            if self._sent_sv_y is None or (new_sv_y != self._sent_sv_y and (new_sv_y == servo_y or abs(new_sv_y - self._sent_sv_y) >= self.SERVO_DEADBAND_DEG)):
                cmds.append(f"SERVOY{new_sv_y}")
                self._sent_sv_y = new_sv_y
        else:
            self._interp_steps += (float(stepper_cumulative_target) - self._interp_steps) * self.EASE
            if abs(float(stepper_cumulative_target) - self._interp_steps) < self.STEPPER_DEADBAND_ST:
                self._interp_steps = float(stepper_cumulative_target)
            target_int = int(round(self._interp_steps))
            delta = target_int - self._sent_steps
            if delta != 0 and (target_int == stepper_cumulative_target or abs(delta) >= self.STEPPER_DEADBAND_ST):
                cmds.append(format_stepper_command(delta))
                self._sent_steps += delta
            if self._sent_sv_y is None or (new_sv_y != self._sent_sv_y and (new_sv_y == servo_y or abs(new_sv_y - self._sent_sv_y) >= self.SERVO_DEADBAND_DEG)):
                cmds.append(f"SERVO{new_sv_y}")
                self._sent_sv_y = new_sv_y

        if cmds:
            self._batch(cmds)
            self._last_aim_ts = time.time()

    def _compute_step(
        self,
        error: float,
        prev_error: float,
        acquire: bool,
        is_settling: bool,
        is_frozen: bool,
        prev_dir: int,
        max_d_acq: float,
        max_d_prec: float,
    ) -> tuple[float, float]:
        """Compute a single-axis step using PD robotic control, trajectory continuity, and deadzone.

        Regimes:
        1. Lock Freeze: Zero movement.
        2. Trajectory Continuity: Prevent reversal if |error| <= 10.0.
        3. Final deadzone (|error| < 1.0°): Absolute zero.
        4. Micro-correction (|error| ≤ 2.0°): proportional micro-step.
        5. PD Control: step = Kp * e + Kd * de.
        """
        # Settled lock freeze (HIGHEST PRIORITY) — zero output
        if is_frozen:
            return 0.0, error

        abs_err = abs(error)

        # Trajectory Continuity: Prevent unstable hunting
        if abs_err <= 10.0 and prev_dir != 0:
            if (prev_dir == 1 and error < 0) or (prev_dir == -1 and error > 0):
                return 0.0, error  # Halt instead of twitching backwards

        # Final deadzone — absolute zero movement
        if abs_err < self._final_dz:
            return 0.0, error

        # During settling hold, only micro-corrections allowed
        if is_settling or abs_err <= self._micro_thresh:
            # Micro-correction loop
            step = error * self._micro_k
            return max(-self._micro_max, min(self._micro_max, step)), error

        # Normal PD Control with phase-aware limits
        far = abs_err > self._acquire_dist
        if acquire or far:
            kp = self._k_acq
            kd = self._kd_acq
            max_d = max_d_acq
        else:
            kp = self._k_prec
            kd = self._kd_prec
            max_d = max_d_prec

        step = (kp * error) + (kd * (error - prev_error))
        return max(-max_d, min(max_d, step)), error

    def _backlash_offset(self, error: float, prev_dir: int, is_frozen: bool) -> tuple[float, int]:
        """Compute backlash compensation offset on direction reversal.

        Returns (offset, new_dir).
        """
        if is_frozen or abs(error) < self._final_dz:
            return 0.0, prev_dir
        new_dir = 1 if error > 0 else -1
        if prev_dir != 0 and new_dir != prev_dir:
            # Direction reversal — add backlash compensation
            offset = self._backlash * new_dir
            return offset, new_dir
        return 0.0, new_dir

    def _aim_dual(self, target_sv_x: int, target_sv_y: int, *, acquire: bool = False) -> None:
        """Dual-servo pan+tilt mode with full precision control."""
        now = time.time()
        is_settling = now < self._settling_until
        is_frozen = now < self._lock_freeze_until

        err_x = float(target_sv_x) - self._interp_sv_x
        err_y = float(target_sv_y) - self._interp_sv_y

        # Check for settled lock freeze condition
        if max(abs(err_x), abs(err_y)) < 1.0 and not acquire:
            self._consec_settled += 1
            if self._consec_settled >= self._lock_frz_frames and not is_frozen:
                self._lock_freeze_until = now + self._lock_frz_sec
                is_frozen = True
                self._consec_settled = 0
        else:
            self._consec_settled = 0

        # Backlash compensation
        bl_x, self._prev_dir_x = self._backlash_offset(err_x, self._prev_dir_x, is_frozen)
        bl_y, self._prev_dir_y = self._backlash_offset(err_y, self._prev_dir_y, is_frozen)

        # Compute steps
        step_x, self._prev_err_x = self._compute_step(
            err_x + bl_x, self._prev_err_x, acquire, is_settling, is_frozen, self._prev_dir_x, float(self._max_d_acq), float(self._max_d_prec)
        )
        step_y, self._prev_err_y = self._compute_step(
            err_y + bl_y, self._prev_err_y, acquire, is_settling, is_frozen, self._prev_dir_y, float(self._max_d_acq), float(self._max_d_prec)
        )

        # Deadband suppression for output noise
        if abs(step_x) < 0.5 and abs(err_x) < self.SERVO_DEADBAND_DEG:
            step_x = 0.0
        if abs(step_y) < 0.5 and abs(err_y) < self.SERVO_DEADBAND_DEG:
            step_y = 0.0

        self._interp_sv_x += step_x
        self._interp_sv_y += step_y
        sx = self._clamp_sv_x(self._interp_sv_x)
        sy = self._clamp_sv_y(self._interp_sv_y)

        # Jitter check
        if self._check_jitter(sy):
            return

        # Enter settling hold when reaching near-target for the first time
        if not is_settling and max(abs(err_x), abs(err_y)) <= self._micro_thresh and not acquire:
            self._settling_until = now + self._settle_sec

        cmds: list[str] = []
        if self._sent_sv_x is None or abs(sx - self._sent_sv_x) >= self.SERVO_DEADBAND_DEG:
            cmds.append(f"SERVOX{sx}")
            self._sent_sv_x = sx
        if self._sent_sv_y is None or abs(sy - self._sent_sv_y) >= self.SERVO_DEADBAND_DEG:
            cmds.append(f"SERVOY{sy}")
            self._sent_sv_y = sy
        if cmds:
            self._batch(cmds)

    def _aim_stepper_servo(self, pan_steps: int, target_sv_y: int, *, acquire: bool = False) -> None:
        """Stepper (X / pan) + servo Y (tilt) mode with full precision control."""
        now = time.time()
        is_settling = now < self._settling_until
        is_frozen = now < self._lock_freeze_until

        err_y = float(target_sv_y) - self._interp_sv_y
        
        stepper_target = self._sent_steps + pan_steps
        err_st = float(stepper_target) - self._interp_steps

        # Check for settled lock freeze condition
        if max(abs(err_y), abs(err_st)) < 1.0 and not acquire:
            self._consec_settled += 1
            if self._consec_settled >= self._lock_frz_frames and not is_frozen:
                self._lock_freeze_until = now + self._lock_frz_sec
                is_frozen = True
                self._consec_settled = 0
        else:
            self._consec_settled = 0

        # Backlash compensation for servo Y
        bl_y, self._prev_dir_y = self._backlash_offset(err_y, self._prev_dir_y, is_frozen)
        step_y, self._prev_err_y = self._compute_step(
            err_y + bl_y, self._prev_err_y, acquire, is_settling, is_frozen, self._prev_dir_y, float(self._max_d_acq), float(self._max_d_prec)
        )

        if abs(step_y) < 0.5 and abs(err_y) < self.SERVO_DEADBAND_DEG:
            step_y = 0.0

        self._interp_sv_y += step_y
        sy = self._clamp_sv_y(self._interp_sv_y)

        # Jitter check
        if self._check_jitter(sy):
            return

        # Stepper: proportional with phase-aware limits + backlash + PD
        bl_st, self._prev_dir_st = self._backlash_offset(err_st, self._prev_dir_st, is_frozen)

        step_st, self._prev_err_st = self._compute_step(
            err_st + bl_st, self._prev_err_st, acquire, False, is_frozen, self._prev_dir_st, float(self._stp_max_acq), float(self._stp_max_prec)
        )

        self._interp_steps += step_st
        target_int = int(round(self._interp_steps))
        delta = target_int - self._sent_steps

        # Enter settling hold
        if not is_settling and abs(err_y) <= self._micro_thresh and not acquire:
            self._settling_until = now + self._settle_sec

        cmds: list[str] = []
        if abs(delta) >= self.STEPPER_DEADBAND_ST:
            cmds.append(format_stepper_command(delta))
            self._sent_steps += delta
        if self._sent_sv_y is None or abs(sy - self._sent_sv_y) >= self.SERVO_DEADBAND_DEG:
            cmds.append(f"SERVO{sy}")
            self._sent_sv_y = sy
        if cmds:
            self._batch(cmds)

    # ======================================================================
    # Pump / laser
    # ======================================================================
    def set_pump(self, on: bool, *, force: bool = False) -> None:
        if not on and self._pump_always and not force:
            return
        if on == self._pump_hw:
            return
        self._pump_hw = on
        if self._pump_laser:
            if on:
                self._batch(["LASER_ON"])
            elif self._laser_on:
                if not self._laser_warned and self.debug:
                    print("[Arduino] Pump OFF skipped LASER_OFF (LASER_ALWAYS_ON).")
                    self._laser_warned = True
            else:
                self._batch(["LASER_OFF"])
        else:
            self._batch(["PUMP_ON" if on else "PUMP_OFF"])

    # ======================================================================
    # Public properties
    # ======================================================================
    @property
    def last_servo_x(self) -> int | None:
        return self._sent_sv_x

    @property
    def last_servo_y(self) -> int | None:
        return self._sent_sv_y

    @property
    def stepper_position(self) -> int:
        return self._sent_steps

    # ======================================================================
    # Reset / close
    # ======================================================================
    def reset(self) -> None:
        self._send_sync("RESET")
        self._sent_sv_x    = 90 if self._dual_servo else None
        self._sent_sv_y    = 90
        self._sent_steps   = self._step_origin
        self._interp_sv_x  = 90.0
        self._interp_sv_y  = 90.0
        self._interp_steps = float(self._step_origin)
        self._last_zone    = 0
        self._pump_hw      = False
        self._jitter_frozen_until = 0.0
        self._dir_reversal_count = 0
        self._last_servo_y_dir = 0
        if self._laser_on:
            self._send_sync("LASER_ON")
        if self._pump_always and not self._pump_laser:
            self.set_pump(True)

    def close(self) -> None:
        for q in (self._q, self._pq):
            try:
                q.put_nowait(None)
            except queue.Full:
                pass
        if self._tx.is_alive():
            self._tx.join(timeout=3.0)
        if self.ser and self.ser.is_open:
            self.set_pump(False, force=True)
            self._all_lamps_on(sync=True)
            self._send_sync("RESET")
            time.sleep(0.35)
            self.ser.close()
        print("[Arduino] Serial port closed.")
