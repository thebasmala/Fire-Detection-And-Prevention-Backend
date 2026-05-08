"""
Detection coordinate filter — exponential moving average (EMA).

Formula:  smoothed = alpha * smoothed_prev + (1 - alpha) * new_measurement

With alpha = 0.7:
  - 70 % weight on the previous stable position
  - 30 % weight on the new noisy measurement
  → strong noise rejection, lag is acceptable for fire tracking.
"""
from __future__ import annotations


class StableTargetFilter:
    """
    Temporal sliding-window stabilizer for bounding-box centre coordinates.
    Maintains a 5-frame ring buffer of detections and computes a confidence-weighted
    average, rejecting physical anomalies.
    """

    def __init__(
        self,
        buffer_size: int = 5,
        max_jump_px: float = 25.0,
        max_area_change: float = 0.40,
        min_high_conf: float = 0.85,
        # Legacy parameters accepted but ignored (kept for API compatibility)
        alpha: float = 0.70,
        velocity_damp: float = 0.0,
        max_delta_per_frame: float = 0.0,
        drift_decay: float = 0.0,
        micro_px: float = 4.0,
    ):
        self.buffer_size = buffer_size
        self.max_jump_px = float(max_jump_px)
        self.max_area_change = float(max_area_change)
        self.min_high_conf = float(min_high_conf)
        
        # Buffer elements will be tuples: (cx, cy, w, h, conf)
        self.history = []

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Hard reset — clears the history buffer."""
        self.history.clear()

    def soft_reset(self) -> None:
        """No-op kept for API compatibility."""
        pass

    # ------------------------------------------------------------------
    def update(self, cx: float, cy: float, w: float, h: float, conf: float) -> tuple[float, float]:
        """
        Feed a new raw bounding-box centre (cx, cy) along with dimensions and confidence.
        Returns the temporally stabilized estimate.
        """
        if not self.history:
            # First observation
            self.history.append((cx, cy, w, h, conf))
            return cx, cy

        # Get previous smoothed position and size for outlier rejection
        prev_cx, prev_cy = self._get_weighted_average()
        _, _, prev_w, prev_h, _ = self.history[-1]
        
        dx = cx - prev_cx
        dy = cy - prev_cy
        dist = (dx**2 + dy**2)**0.5
        
        prev_area = prev_w * prev_h
        curr_area = w * h
        area_change = abs(curr_area - prev_area) / max(prev_area, 1e-6)
        
        # Outlier Rejection
        is_jump_outlier = dist > self.max_jump_px and conf < self.min_high_conf
        is_area_outlier = area_change > self.max_area_change
        
        if is_jump_outlier or is_area_outlier:
            # Reject this frame by not adding it, return previous stabilized centroid
            return prev_cx, prev_cy
            
        self.history.append((cx, cy, w, h, conf))
        if len(self.history) > self.buffer_size:
            self.history.pop(0)
            
        return self._get_weighted_average()
        
    def _get_weighted_average(self) -> tuple[float, float]:
        sum_cx = 0.0
        sum_cy = 0.0
        sum_conf = 0.0
        
        for cx, cy, w, h, conf in self.history:
            sum_cx += cx * conf
            sum_cy += cy * conf
            sum_conf += conf
            
        if sum_conf == 0:
            return self.history[-1][0], self.history[-1][1]
            
        return sum_cx / sum_conf, sum_cy / sum_conf

