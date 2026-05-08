from __future__ import annotations


class FireRetentionGate:
    def __init__(self, confirm_frames: int, retain_sec: float, retain_frames: int):
        self.confirm_frames = max(1, int(confirm_frames))
        self.retain_sec = float(retain_sec)
        self.retain_frames = max(0, int(retain_frames))
        self.state = "NO_FIRE"
        self._confirm_count = 0
        self._hold_count = 0
        self._hold_started_at: float | None = None
        self._last_det: dict | None = None

    def update(self, now: float, raw_best_fire: dict | None) -> tuple[bool, dict | None, str]:
        has_fire = raw_best_fire is not None
        if has_fire:
            self._last_det = raw_best_fire

        if self.state == "NO_FIRE":
            if has_fire:
                self.state = "CONFIRMING"
                self._confirm_count = 1
        elif self.state == "CONFIRMING":
            if has_fire:
                self._confirm_count += 1
                if self._confirm_count >= self.confirm_frames:
                    self.state = "LOCKED"
                    self._hold_count = 0
                    self._hold_started_at = None
            else:
                self.state = "NO_FIRE"
                self._confirm_count = 0
                self._last_det = None
        elif self.state == "LOCKED":
            if not has_fire:
                self.state = "HOLD"
                self._hold_count = 1
                self._hold_started_at = now
        elif self.state == "HOLD":
            if has_fire:
                self.state = "LOCKED"
                self._hold_count = 0
                self._hold_started_at = None
            else:
                self._hold_count += 1
                hold_elapsed = now - (self._hold_started_at if self._hold_started_at is not None else now)
                over_frames = self.retain_frames > 0 and self._hold_count >= self.retain_frames
                over_time = self.retain_sec > 0 and hold_elapsed >= self.retain_sec
                if over_frames or over_time:
                    self.state = "LOST"
        elif self.state == "LOST":
            self._last_det = None
            self._confirm_count = 0
            self._hold_count = 0
            self._hold_started_at = None
            self.state = "NO_FIRE"
            if has_fire:
                self.state = "CONFIRMING"
                self._confirm_count = 1

        fire_confirmed = self.state in ("LOCKED", "HOLD")
        return fire_confirmed, self._last_det if fire_confirmed else None, self.state
