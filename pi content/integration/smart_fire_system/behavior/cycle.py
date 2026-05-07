"""
State machine definition and geometric predicates for the turret cycle.

States
------
IDLE       — No active fire. Turret returns to and waits at origin.
TARGETING  — Fire confirmed. Turret moves to the one-time snapped target.
MONITORING — Turret holds the locked target until the fire is extinguished.
"""
from __future__ import annotations

from enum import Enum


class CycleState(str, Enum):
    IDLE       = "IDLE"
    TARGETING  = "TARGETING"
    MONITORING = "MONITORING"


# ---------------------------------------------------------------------------
# Geometric predicates used by app.py
# ---------------------------------------------------------------------------
def at_origin_stepper_servo(
    *,
    dual_servo_mode: bool,
    stepper_position: int,
    stepper_target: int,
    servo_x: int | None,
    servo_y: int | None,
    servo_x_target: int,
    servo_y_target: int,
    stepper_tol: int = 5,
    servo_tol: int = 2,
) -> bool:
    """
    True when all motors are within tolerance of the origin pose.
    servo_tol defaults to ±2° as required by the spec.
    stepper_tol is relaxed to 5 steps to match the hardware deadband.
    """
    sy = int(servo_y if servo_y is not None else servo_y_target)
    if not dual_servo_mode and abs(stepper_position - stepper_target) > stepper_tol:
        return False
    if abs(sy - servo_y_target) > servo_tol:
        return False
    if dual_servo_mode:
        sx = int(servo_x if servo_x is not None else servo_x_target)
        if abs(sx - servo_x_target) > servo_tol:
            return False
    return True


def tracking_settled(
    *,
    pan_abs: float,
    servo_f: float,
    stepper_position: int,
    step_at_origin: int,
    servo_y: int | None,
    servo_y_center: int,
    pan_tol: float = 5.0,
    servo_tol: float = 4.0,
    dual_servo_mode: bool = False,
    servo_x: int | None = None,
    servo_x_center: int = 90,
    servo_x_min: int = 0,
    servo_x_max: int = 360,
) -> bool:
    """
    True when the turret has physically settled on the calibration target.

    pan_tol is relaxed to 5 steps (matches STEPPER_DEADBAND in arduino.py)
    so the system doesn't spin waiting for the last few steps that will
    never be sent due to the deadband.
    """
    sy = float(servo_y if servo_y is not None else servo_y_center)
    if abs(sy - float(servo_f)) > servo_tol:
        return False
    if dual_servo_mode:
        x_tgt = max(float(servo_x_min),
                    min(float(servo_x_max),
                        float(servo_x_center) + float(pan_abs)))
        sx = float(servo_x if servo_x is not None else servo_x_center)
        return abs(sx - x_tgt) <= servo_tol
    cum = float(stepper_position) - float(step_at_origin)
    return abs(cum - float(pan_abs)) <= pan_tol
