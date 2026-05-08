"""
Deterministic 5x5 calibration mapping system.
Replaces smoothing and iterative relaxation with strict lookup and linear interpolation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EnvironmentPoint:
    """A discrete physical point in the calibrated 5x5 environment map."""

    grid_x: int
    grid_y: int
    pan_abs: float
    servo_y_deg: float


class CalibrationMapper:
    """
    Maps pixel (cx, cy) → grid (gx, gy) ∈ [1,5] → motor targets.
    """

    def __init__(self, *, debug: bool = False, calibration_mode: bool = False):
        self.debug = bool(debug)
        self.calibration_mode = bool(calibration_mode)

        self._pan = np.array(
            [
                [np.nan, np.nan, -9.0, 78.0, 78.0],
                [20.0, 10.0, -10.0, 60.0, 60.0],
                [50.0, 80.0, 0.0, 40.0, np.nan],
                [75.0, 90.0, -10.0, 17.0, 23.0],
                [82.0, 93.0, -10.0, np.nan, 20.0],
            ],
            dtype=np.float64,
        )

        self._servo = np.array(
            [
                [126.0, 122.0, 123.0, 55.0, 55.0],
                [110.0, 109.0, 123.0, 65.0, 58.0],
                [107.0, 109.0, 90.0, 65.0, np.nan],
                [112.0, 105.0, 74.0, 70.0, 61.0],
                [122.0, 118.0, 61.0, 58.0, 55.0],
            ],
            dtype=np.float64,
        )

        self._fill_missing_values()

    def _fill_missing_values(self):
        """Deterministically fill missing values without aggressive extrapolation."""
        # (3,5) missing: fallback to column interpolation
        self._pan[2, 4] = (self._pan[1, 4] + self._pan[3, 4]) / 2.0
        self._servo[2, 4] = (self._servo[1, 4] + self._servo[3, 4]) / 2.0

        # (5,4) missing pan: use nearest 2 valid neighbors in same row
        self._pan[4, 3] = (self._pan[4, 2] + self._pan[4, 4]) / 2.0

        # (1,1) and (1,2) missing pan: safe fallback, copy from row 2
        self._pan[0, 0] = self._pan[1, 0]
        self._pan[0, 1] = self._pan[1, 1]

    def pixels_to_grid(
        self,
        cx: float,
        cy: float,
        frame_w: int,
        frame_h: int,
        *,
        invert_pan_x: bool,
        invert_tilt_y: bool,
    ) -> tuple[float, float]:
        """Convert pixel coordinate to continuous 5x5 grid position [1, 5]."""
        fw = max(float(frame_w - 1), 1.0)
        fh = max(float(frame_h - 1), 1.0)
        u = cx / fw
        v = cy / fh
        if invert_pan_x:
            u = 1.0 - u
        if invert_tilt_y:
            v = 1.0 - v
        gx = 1.0 + u * 4.0
        gy = 1.0 + v * 4.0
        # Clamp to bounds [1.0, 5.0]
        gx = max(1.0, min(5.0, gx))
        gy = max(1.0, min(5.0, gy))
        return gx, gy

    @staticmethod
    def _nearest_grid_index(value: float) -> int:
        """Return nearest 0-based grid index using half-up rounding, clamped to 0..4."""
        return max(0, min(4, int(np.floor(float(value) + 0.5)) - 1))

    def _environment_point_from_indices(self, row_idx: int, col_idx: int) -> EnvironmentPoint:
        return EnvironmentPoint(
            grid_x=col_idx + 1,
            grid_y=row_idx + 1,
            pan_abs=float(self._pan[row_idx, col_idx]),
            servo_y_deg=float(max(55.0, min(126.0, self._servo[row_idx, col_idx]))),
        )

    def snap_grid_point(self, gx: float, gy: float) -> EnvironmentPoint:
        """Snap continuous grid coordinates to the nearest calibrated EnvironmentMap point."""
        row_idx = self._nearest_grid_index(gy)
        col_idx = self._nearest_grid_index(gx)
        return self._environment_point_from_indices(row_idx, col_idx)

    def snap_point(
        self,
        cx: float,
        cy: float,
        frame_w: int,
        frame_h: int,
        *,
        invert_pan_x: bool,
        invert_tilt_y: bool,
    ) -> EnvironmentPoint:
        """Convert a pixel coordinate to the nearest discrete EnvironmentMap point."""
        gx, gy = self.pixels_to_grid(
            cx,
            cy,
            frame_w,
            frame_h,
            invert_pan_x=invert_pan_x,
            invert_tilt_y=invert_tilt_y,
        )
        point = self.snap_grid_point(gx, gy)
        if self.debug:
            print(
                f"[CAL] snap ({cx:.1f},{cy:.1f}) -> "
                f"grid({gx:.2f},{gy:.2f}) -> "
                f"map({point.grid_x},{point.grid_y}) "
                f"pan={point.pan_abs:.1f}, servo={point.servo_y_deg:.1f}"
            )
        return point

    def _get_servo_from_x(self, gx: float, gy: float, nearest_neighbor: bool) -> tuple[float, float]:
        """
        Deterministic lookup.
        STEP 1: Find nearest calibration row based on Y proximity.
        STEP 2: Within that row: prefer exact match, else linear interpolation.
        STEP 3: Clamp output servo to [55, 126].
        """
        row_idx = self._nearest_grid_index(gy)
        
        if nearest_neighbor:
            # FAST ACQUIRE / FIRE LOCK -> exact discrete mapping
            point = self.snap_grid_point(gx, gy)
            pan_out = point.pan_abs
            servo_out = point.servo_y_deg
        else:
            # PRECISION MODE -> horizontal linear interpolation within row
            c0 = int(np.floor(gx)) - 1
            c1 = int(np.ceil(gx)) - 1
            
            if c0 == c1:
                pan_out = self._pan[row_idx, c0]
                servo_out = self._servo[row_idx, c0]
            else:
                tc = gx - (c0 + 1.0)
                pan_out = (1.0 - tc) * self._pan[row_idx, c0] + tc * self._pan[row_idx, c1]
                servo_out = (1.0 - tc) * self._servo[row_idx, c0] + tc * self._servo[row_idx, c1]

        # STEP 3: Clamp output servo
        servo_out = max(55.0, min(126.0, servo_out))
        
        # Clamp pan to min/max of the row to prevent extrapolation beyond bounds
        min_pan = np.min(self._pan[row_idx, :])
        max_pan = np.max(self._pan[row_idx, :])
        pan_out = max(min_pan, min(max_pan, pan_out))

        return pan_out, servo_out

    def map_point(
        self,
        cx: float,
        cy: float,
        frame_w: int,
        frame_h: int,
        *,
        invert_pan_x: bool,
        invert_tilt_y: bool,
        nearest_neighbor: bool = False,
    ) -> tuple[float, float, float, float]:
        """Returns (gx, gy, pan_abs, servo_angle)."""
        gx, gy = self.pixels_to_grid(
            cx, cy, frame_w, frame_h,
            invert_pan_x=invert_pan_x,
            invert_tilt_y=invert_tilt_y,
        )
        pan_abs, servo = self._get_servo_from_x(gx, gy, nearest_neighbor)
        
        if self.debug:
            print(f"[CAL] map ({cx:.1f},{cy:.1f}) -> grid({gx:.2f},{gy:.2f}) mode={'NN' if nearest_neighbor else 'LERP'} -> pan={pan_abs:.1f}, servo={servo:.1f}")
            
        return gx, gy, pan_abs, servo

    def evaluate(
        self,
        cx: float,
        cy: float,
        frame_w: int,
        frame_h: int,
        *,
        invert_pan_x: bool,
        invert_tilt_y: bool,
    ) -> tuple[float, float, float, float, float]:
        """Evaluate for HUD/telemetry without debug prints."""
        gx, gy = self.pixels_to_grid(
            cx, cy, frame_w, frame_h,
            invert_pan_x=invert_pan_x,
            invert_tilt_y=invert_tilt_y,
        )
        # Always evaluate HUD as interpolation
        pan_abs, servo = self._get_servo_from_x(gx, gy, nearest_neighbor=False)
        return gx, gy, pan_abs, servo, 1.0
