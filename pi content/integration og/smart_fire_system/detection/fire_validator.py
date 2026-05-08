"""
Multi-modal fire validation — HSV colour + motion (OR logic).

FIRE DETECTION RULE (CRITICAL):
    fire_detected = (hailo_conf >= 0.6) AND (
        (hsv_score >= 0.05) OR (motion_score >= 0.02)
    )

Temporal consistency is a SOFT ENHANCER only — it boosts confidence
but NEVER blocks a detection that passes the HSV-or-motion gate.

Ambient brightness is measured per frame so the HSV thresholds adapt
automatically to high-brightness and low-contrast conditions.
"""
from __future__ import annotations

from collections import deque

import cv2
import numpy as np


class FireValidator:
    """Combined HSV + motion fire validator with OR logic."""

    def __init__(
        self,
        *,
        # HSV bright fire thresholds
        hsv_h_low: int = 0,
        hsv_h_high: int = 35,
        hsv_s_low: int = 80,
        hsv_s_high: int = 255,
        hsv_v_low: int = 180,
        hsv_v_high: int = 255,
        # HSV dim/candle thresholds (secondary mask, ORed)
        hsv_dim_h_low1: int = 0,
        hsv_dim_h_high1: int = 15,
        hsv_dim_h_low2: int = 160,
        hsv_dim_h_high2: int = 180,
        hsv_dim_s_low: int = 50,
        hsv_dim_s_high: int = 255,
        hsv_dim_v_low: int = 100,
        hsv_dim_v_high: int = 255,
        # HSV fire ratio
        hsv_min_fire_ratio: float = 0.05,
        # Motion detection
        motion_diff_threshold: int = 25,
        motion_min_ratio: float = 0.02,
        # Temporal consistency (soft enhancer only)
        temporal_required: int = 2,
        temporal_window: int = 3,
        # Confidence
        min_confidence: float = 0.60,
        debug: bool = False,
    ):
        # Bright fire HSV
        self._h_lo = int(hsv_h_low)
        self._h_hi = int(hsv_h_high)
        self._s_lo = int(hsv_s_low)
        self._s_hi = int(hsv_s_high)
        self._v_lo = int(hsv_v_low)
        self._v_hi = int(hsv_v_high)
        # Dim fire HSV
        self._dh_lo1 = int(hsv_dim_h_low1)
        self._dh_hi1 = int(hsv_dim_h_high1)
        self._dh_lo2 = int(hsv_dim_h_low2)
        self._dh_hi2 = int(hsv_dim_h_high2)
        self._ds_lo = int(hsv_dim_s_low)
        self._ds_hi = int(hsv_dim_s_high)
        self._dv_lo = int(hsv_dim_v_low)
        self._dv_hi = int(hsv_dim_v_high)
        # Ratios
        self._hsv_ratio = float(hsv_min_fire_ratio)
        self._mot_thresh = int(motion_diff_threshold)
        self._mot_ratio = float(motion_min_ratio)
        self._min_conf = float(min_confidence)
        # Temporal (soft only)
        self._temp_req = int(temporal_required)
        self._ring: deque[bool] = deque(maxlen=int(temporal_window))
        self.debug = bool(debug)

        # Exposed scores for debug printing (updated every validate() call)
        self.last_hsv_score: float = 0.0
        self.last_motion_score: float = 0.0

        # ── Frame-level diagnostics (ALWAYS updated, Hailo-independent) ──
        self.frame_hsv_score: float = 0.0
        self.frame_motion_score: float = 0.0
        self.frame_brightness: float = 0.0
        self._prev_gray: np.ndarray | None = None  # for frame-freeze detection
        self._freeze_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def validate(
        self,
        frame: np.ndarray,
        prev_frame: np.ndarray | None,
        bbox: tuple[int, int, int, int],
        confidence: float,
    ) -> bool:
        """
        Validate a Hailo fire detection.

        LOGIC:
            fire_detected = (conf >= 0.6) AND (hsv_score >= 0.05 OR motion_score >= 0.02)

        Temporal consistency is soft enhancer only — does NOT block.

        Returns True if detection passes the HSV-or-motion gate.
        """
        self.last_hsv_score = 0.0
        self.last_motion_score = 0.0

        # Gate 1: confidence (hard gate — keep at 0.6)
        if confidence < self._min_conf:
            self._ring.append(False)
            return False

        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        # Clamp ROI to frame
        x1 = max(0, min(x1, w - 1))
        y1 = max(0, min(y1, h - 1))
        x2 = max(x1 + 1, min(x2, w))
        y2 = max(y1 + 1, min(y2, h))

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            self._ring.append(False)
            return False

        # Compute HSV score
        hsv_score = self._compute_hsv_score(roi, frame)
        self.last_hsv_score = hsv_score

        # Compute motion score
        if prev_frame is not None and prev_frame.shape == frame.shape:
            motion_score = self._compute_motion_score(frame, prev_frame, x1, y1, x2, y2)
        else:
            # First frame — no reference, accept by default
            motion_score = 1.0
        self.last_motion_score = motion_score

        # ──────────────────────────────────────────────────────
        # CORE LOGIC: OR gate (NOT AND)
        # fire_detected = (conf >= 0.6) AND (hsv OR motion)
        # ──────────────────────────────────────────────────────
        hsv_ok = hsv_score >= self._hsv_ratio
        motion_ok = motion_score >= self._mot_ratio

        frame_valid = hsv_ok or motion_ok

        # Temporal consistency — SOFT ENHANCER ONLY, never blocks
        self._ring.append(frame_valid)

        if self.debug:
            temporal_count = sum(self._ring)
            print(
                f"[Validator] conf={confidence:.2f} "
                f"hsv_score={hsv_score:.3f}({'OK' if hsv_ok else '--'}) "
                f"motion_score={motion_score:.3f}({'OK' if motion_ok else '--'}) "
                f"temporal={temporal_count}/{len(self._ring)} "
                f"-> {'VALID' if frame_valid else 'REJECT'}"
            )

        return frame_valid

    def reset(self) -> None:
        """Clear temporal history."""
        self._ring.clear()
        self.last_hsv_score = 0.0
        self.last_motion_score = 0.0
        self.frame_hsv_score = 0.0
        self.frame_motion_score = 0.0
        self.frame_brightness = 0.0

    # ------------------------------------------------------------------
    # PIPELINE A: Frame-level diagnostics (Hailo-independent, ALWAYS run)
    # ------------------------------------------------------------------
    def compute_frame_diagnostics(
        self,
        frame_bgr: np.ndarray,
        prev_frame_bgr: np.ndarray | None,
    ) -> tuple[float, float, float, bool]:
        """
        Compute visual metrics on the FULL FRAME, independent of Hailo.

        This MUST be called every loop iteration BEFORE any detection pipeline.

        Returns (hsv_score, motion_score, brightness, frame_healthy).
        Updates self.frame_hsv_score, self.frame_motion_score, self.frame_brightness.
        """
        # ── Camera health check ──────────────────────────────────────
        if frame_bgr is None or frame_bgr.size == 0:
            print("[CAMERA] CAMERA PIPELINE BROKEN — frame is None/empty")
            return 0.0, 0.0, 0.0, False

        if len(frame_bgr.shape) != 3 or frame_bgr.shape[2] != 3:
            print(f"[CAMERA] CAMERA PIPELINE BROKEN — bad shape {frame_bgr.shape}")
            return 0.0, 0.0, 0.0, False

        # Frame-freeze detection: if identical pixels for 10+ frames, flag it
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        if self._prev_gray is not None and self._prev_gray.shape == gray.shape:
            if np.array_equal(gray, self._prev_gray):
                self._freeze_count += 1
                if self._freeze_count >= 10:
                    print(f"[CAMERA] CAMERA PIPELINE BROKEN — frame frozen for {self._freeze_count} frames")
                    self._prev_gray = gray.copy()
                    return 0.0, 0.0, 0.0, False
            else:
                self._freeze_count = 0
        self._prev_gray = gray.copy()

        # ── Full-frame HSV score ─────────────────────────────────────
        hsv_score = self._compute_hsv_score(frame_bgr, frame_bgr)
        self.frame_hsv_score = hsv_score

        # ── Full-frame motion score ──────────────────────────────────
        h, w = frame_bgr.shape[:2]
        if prev_frame_bgr is not None and prev_frame_bgr.shape == frame_bgr.shape:
            motion_score = self._compute_motion_score(
                frame_bgr, prev_frame_bgr, 0, 0, w, h,
            )
        else:
            motion_score = 0.0
        self.frame_motion_score = motion_score

        # ── Brightness ───────────────────────────────────────────────
        hsv_full = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        brightness = float(np.mean(hsv_full[:, :, 2]))
        self.frame_brightness = brightness

        return hsv_score, motion_score, brightness, True

    @staticmethod
    def check_frame_health(frame) -> bool:
        """Quick null/shape check — returns False if frame is broken."""
        if frame is None:
            return False
        if not hasattr(frame, 'shape') or len(frame.shape) < 2:
            return False
        if frame.size == 0:
            return False
        return True

    # ------------------------------------------------------------------
    # HSV colour score
    # ------------------------------------------------------------------
    def _compute_hsv_score(self, roi: np.ndarray, full_frame: np.ndarray) -> float:
        """Return ratio of fire-coloured pixels in the ROI (0.0 to 1.0)."""
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        total_px = float(hsv_roi.shape[0] * hsv_roi.shape[1])
        if total_px < 1.0:
            return 0.0

        # Adapt thresholds to ambient brightness
        s_lo, v_lo = self._adaptive_thresholds(full_frame)

        # Primary mask: bright fire
        lo1 = np.array([self._h_lo, s_lo, v_lo], dtype=np.uint8)
        hi1 = np.array([self._h_hi, self._s_hi, self._v_hi], dtype=np.uint8)
        mask1 = cv2.inRange(hsv_roi, lo1, hi1)

        # Secondary mask: dim / candle (range 1)
        lo2a = np.array([self._dh_lo1, self._ds_lo, self._dv_lo], dtype=np.uint8)
        hi2a = np.array([self._dh_hi1, self._ds_hi, self._dv_hi], dtype=np.uint8)
        mask2a = cv2.inRange(hsv_roi, lo2a, hi2a)

        # Secondary mask: dim / candle (range 2 — wraps around H=180)
        lo2b = np.array([self._dh_lo2, self._ds_lo, self._dv_lo], dtype=np.uint8)
        hi2b = np.array([self._dh_hi2, self._ds_hi, self._dv_hi], dtype=np.uint8)
        mask2b = cv2.inRange(hsv_roi, lo2b, hi2b)

        combined = cv2.bitwise_or(mask1, cv2.bitwise_or(mask2a, mask2b))
        fire_px = float(cv2.countNonZero(combined))
        return fire_px / total_px

    # ------------------------------------------------------------------
    # Motion score
    # ------------------------------------------------------------------
    def _compute_motion_score(
        self,
        frame: np.ndarray,
        prev_frame: np.ndarray,
        x1: int, y1: int, x2: int, y2: int,
    ) -> float:
        """Return ratio of motion pixels in the ROI (0.0 to 1.0)."""
        gray_cur = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(gray_cur, gray_prev)
        roi_diff = diff[y1:y2, x1:x2]
        if roi_diff.size == 0:
            return 0.0
        _, thresh = cv2.threshold(roi_diff, self._mot_thresh, 255, cv2.THRESH_BINARY)
        motion_px = float(cv2.countNonZero(thresh))
        total_px = float(roi_diff.shape[0] * roi_diff.shape[1])
        if total_px < 1.0:
            return 0.0
        return motion_px / total_px

    # ------------------------------------------------------------------
    # Adaptive thresholds
    # ------------------------------------------------------------------
    def _adaptive_thresholds(self, frame: np.ndarray) -> tuple[int, int]:
        """Adjust S and V lower bounds based on ambient brightness."""
        hsv_full = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mean_v = float(np.mean(hsv_full[:, :, 2]))

        if mean_v > 180:
            # Very bright ambient — tighten S to reject reflections
            s_lo = min(self._s_lo + 40, 200)
            v_lo = self._v_lo
        elif mean_v < 80:
            # Dim ambient — relax V to catch candle flames
            s_lo = max(self._s_lo - 20, 30)
            v_lo = max(self._v_lo - 60, 80)
        else:
            s_lo = self._s_lo
            v_lo = self._v_lo

        return s_lo, v_lo
