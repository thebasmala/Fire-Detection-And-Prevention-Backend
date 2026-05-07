"""
ActiveFireTracker — converts a smoothed pixel position into motor commands.

Design
------
1. The smoothed pixel (cx, cy) is mapped via CalibrationMapper to an
   *absolute* motor target: pan_abs (cumulative stepper offset from origin)
   and servo_angle (degrees).

2. Both targets are themselves exponentially smoothed so that
   rapid detection jumps produce only gradual motor movement.

3. The computed commands are clamped per-frame (max steps / max degrees)
   so the physical motors never receive violent impulses.

4. A pixel dead zone suppresses micro-corrections when the fire is
   already centred.

5. Command suppression: if the rounded motor command has not changed
   significantly vs. the last sent value, None is returned so the caller
   knows not to enqueue a serial command.
"""
from __future__ import annotations

from dataclasses import dataclass

from smart_fire_system.calibration.mapper import CalibrationMapper
from smart_fire_system.vision.draw import frame_center


@dataclass
class CenteringCommand:
    servoy_angle: int
    servox_angle: int
    pan_steps: int = 0


class ActiveFireTracker:
    """Converts smoothed pixel target -> CenteringCommand for the Arduino."""

    def __init__(
        self,
        *,
        mapper: CalibrationMapper,
        invert_pan_x: bool,
        invert_tilt_y: bool,
        center_dead_zone_px_x: int,
        center_dead_zone_px_y: int,
        pan_steps_min: int,
        pan_steps_max: int,
        servo_x_min: int,
        servo_x_max: int,
        servo_y_min: int,
        servo_y_max: int,
        servo_x_center: int,
        servo_y_center: int,
        dual_servo_mode: bool,
        latency_comp_frames: float,
        max_pan_delta_per_frame: int,
        max_servo_delta_per_frame: int,
        grid_dead_zone: float,
        stepper_cumulative_at_origin: int,
        # Precision params
        max_servo_delta_acquire: int = 6,
        max_pan_delta_acquire: int = 10,
        stepper_max_delta_precision: int = 4,
        bias_decay: float = 0.98,
        bias_learn_rate: float = 0.02,
        bias_max_deg: float = 2.0,
    ):
        self._mapper                = mapper
        self.invert_pan_x           = bool(invert_pan_x)
        self.invert_tilt_y          = bool(invert_tilt_y)
        self.center_dead_zone_px_x  = int(center_dead_zone_px_x)
        self.center_dead_zone_px_y  = int(center_dead_zone_px_y)
        self.pan_steps_min          = int(pan_steps_min)
        self.pan_steps_max          = int(pan_steps_max)
        self.servo_x_min            = int(servo_x_min)
        self.servo_x_max            = int(servo_x_max)
        self.servo_y_min            = int(servo_y_min)
        self.servo_y_max            = int(servo_y_max)
        self.servo_x_center         = int(servo_x_center)
        self.servo_y_center         = int(servo_y_center)
        self.dual_servo_mode        = bool(dual_servo_mode)
        self._max_pan_d             = int(max_pan_delta_per_frame)
        self._max_sv_d              = int(max_servo_delta_per_frame)
        self._grid_dead             = float(grid_dead_zone)
        self._step_at_origin        = int(stepper_cumulative_at_origin)
        self._max_sv_d_acq          = int(max_servo_delta_acquire)
        self._max_pan_d_acq         = int(max_pan_delta_acquire)
        self._stp_max_prec          = int(stepper_max_delta_precision)
        self._bias_decay            = float(bias_decay)
        self._bias_lr               = float(bias_learn_rate)
        self._bias_max              = float(bias_max_deg)
        self._latency_comp          = float(latency_comp_frames)

        self._precision_mode: bool = False
        self._prev_cx: float | None = None
        self._prev_cy: float | None = None
        # Per-zone calibration bias: key = (grid_zone_x, grid_zone_y)
        self._zone_bias: dict[tuple[int, int], float] = {}
        self._zone_bias_pan: dict[tuple[int, int], float] = {}

    def reset_smoothing(self) -> None:
        """Reset internal state when transitioning to TRACKING."""
        self._precision_mode = False
        self._prev_cx = None
        self._prev_cy = None

    def set_precision_mode(self, enabled: bool) -> None:
        """Switch between acquire (heavy EMA) and precision (light EMA + bias learning)."""
        self._precision_mode = enabled

    def compute(
        self,
        smooth_cx: float,
        smooth_cy: float,
        frame_w: int,
        frame_h: int,
        arduino_last_servox: int | None,
        arduino_last_servoy: int | None,
        stepper_cumulative: int,
    ) -> CenteringCommand | None:
        """Compute a new motor command toward (smooth_cx, smooth_cy).
        Returns None if no command needs to be sent."""
        cx0, cy0 = frame_center(frame_w, frame_h)
        
        # Calculate pixel velocity
        if self._prev_cx is not None and self._prev_cy is not None:
            vx = smooth_cx - self._prev_cx
            vy = smooth_cy - self._prev_cy
        else:
            vx = 0.0
            vy = 0.0

        self._prev_cx = smooth_cx
        self._prev_cy = smooth_cy
        
        # Predict future position using lead compensation
        pred_cx = smooth_cx + (vx * self._latency_comp)
        pred_cy = smooth_cy + (vy * self._latency_comp)

        ex = pred_cx - cx0
        ey = pred_cy - cy0

        if abs(ex) < self.center_dead_zone_px_x and abs(ey) < self.center_dead_zone_px_y:
            return None

        gx, gy, pan_abs, servo_f = self._mapper.map_point(
            pred_cx, pred_cy, frame_w, frame_h,
            invert_pan_x=self.invert_pan_x,
            invert_tilt_y=self.invert_tilt_y,
            nearest_neighbor=not self._precision_mode,
        )

        # Grid dead zone — 5x5 grid, centre at (3.0, 3.0)
        if abs(gx - 3.0) < self._grid_dead and abs(gy - 3.0) < self._grid_dead:
            return None

        # Fully deterministic, no EMA smoothing
        pan_t   = pan_abs
        servo_t = servo_f

        # ── Calibration bias learning ──────────────────────────────────
        zone_key = (int(round(gx)), int(round(gy)))

        # Apply learned bias to servo target
        sv_bias = self._zone_bias.get(zone_key, 0.0)
        pan_bias = self._zone_bias_pan.get(zone_key, 0.0)
        
        # Clamp bias to max limits
        sv_bias = max(-self._bias_max, min(self._bias_max, sv_bias))
        pan_bias = max(-self._bias_max, min(self._bias_max, pan_bias))
        
        servo_t_biased = servo_t + sv_bias
        pan_t_biased = pan_t + pan_bias

        # Phase-aware velocity limits
        max_sv = self._max_sv_d if self._precision_mode else self._max_sv_d_acq
        max_pan = self._max_pan_d if self._precision_mode else self._max_pan_d_acq

        # Servo Y
        last_y = float(arduino_last_servoy if arduino_last_servoy is not None else self.servo_y_center)
        y_tgt = float(max(self.servo_y_min, min(self.servo_y_max, servo_t_biased)))
        dy = max(-float(max_sv), min(float(max_sv), y_tgt - last_y))
        final_servo_y = int(round(max(float(self.servo_y_min), min(float(self.servo_y_max), last_y + dy))))

        # Learn bias: update slowly from residual error
        if self._precision_mode and arduino_last_servoy is not None:
            residual = servo_f - float(arduino_last_servoy)
            if abs(residual) < 5.0:  # only learn from small residuals, not wild ones
                new_bias = sv_bias * self._bias_decay + residual * self._bias_lr
                self._zone_bias[zone_key] = max(-self._bias_max, min(self._bias_max, new_bias))

        if self.dual_servo_mode:
            last_x = float(arduino_last_servox if arduino_last_servox is not None else self.servo_x_center)
            x_tgt = float(max(self.servo_x_min, min(self.servo_x_max, float(self.servo_x_center) + pan_t_biased)))
            dx = max(-float(max_sv), min(float(max_sv), x_tgt - last_x))
            final_servo_x = int(round(max(float(self.servo_x_min), min(float(self.servo_x_max), last_x + dx))))
            if final_servo_x == arduino_last_servox and final_servo_y == arduino_last_servoy:
                return None
            return CenteringCommand(servoy_angle=final_servo_y, servox_angle=final_servo_x, pan_steps=0)

        # Stepper + servo Y mode
        stepper_offset = float(stepper_cumulative) - float(self._step_at_origin)
        err_pan = pan_t_biased - stepper_offset
        cmd_pan = int(round(err_pan))
        cmd_pan = max(self.pan_steps_min, min(self.pan_steps_max, cmd_pan))
        cmd_pan = max(-max_pan, min(max_pan, cmd_pan))

        # Learn pan bias
        if self._precision_mode:
            pan_residual = pan_t - stepper_offset
            if abs(pan_residual) < 8.0:
                new_pan_bias = pan_bias * self._bias_decay + pan_residual * self._bias_lr
                self._zone_bias_pan[zone_key] = max(-self._bias_max, min(self._bias_max, new_pan_bias))

        if cmd_pan == 0 and arduino_last_servoy is not None and final_servo_y == arduino_last_servoy:
            return None

        return CenteringCommand(servoy_angle=final_servo_y, servox_angle=self.servo_x_center, pan_steps=cmd_pan)


def should_reaim(cx, cy, last_aim_cx, last_aim_cy, frame_w, frame_h, now, last_aim_time,
                 *, aim_immediate_err_px, aim_force_interval_s, min_aim_interval_s, dead_zone_px, aim_dead_zone_norm):
    """Return True if a new aim command should be issued."""
    cxf, cyf = frame_center(frame_w, frame_h)
    centre_err = max(abs(cx - cxf), abs(cy - cyf))
    if centre_err >= aim_immediate_err_px:
        return (now - last_aim_time) >= aim_force_interval_s
    if last_aim_cx is None or last_aim_cy is None:
        return (now - last_aim_time) >= min_aim_interval_s
    dx, dy = abs(cx - last_aim_cx), abs(cy - last_aim_cy)
    norm_dx = dx / max(float(frame_w), 1.0)
    norm_dy = dy / max(float(frame_h), 1.0)
    error_score = max(dx / max(dead_zone_px, 1e-6), dy / max(dead_zone_px, 1e-6),
                      norm_dx / max(aim_dead_zone_norm, 1e-6), norm_dy / max(aim_dead_zone_norm, 1e-6))
    return error_score > 1.0 and (now - last_aim_time) >= min_aim_interval_s
