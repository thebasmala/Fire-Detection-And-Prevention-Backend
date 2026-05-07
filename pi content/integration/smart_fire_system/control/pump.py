from __future__ import annotations

from smart_fire_system.control.arduino import ArduinoController


class PumpController:
    def __init__(self, cooldown_sec: float):
        self._cooldown_sec = float(cooldown_sec)
        self._pump_on = False
        self._tracking_lost_at: float | None = None

    @property
    def pump_engaged(self) -> bool:
        return self._pump_on

    def update(
        self,
        arduino: ArduinoController,
        now: float,
        *,
        fire_confirmed: bool,
        tracking_locked: bool,
        aim_established: bool,
        tracking_lost: bool,
        stable_track_frames: int,
        min_stable_frames: int,
    ) -> None:
        if tracking_lost:
            if self._tracking_lost_at is None:
                self._tracking_lost_at = now
        else:
            self._tracking_lost_at = None
        lost_timed_out = self._tracking_lost_at is not None and (now - self._tracking_lost_at) >= self._cooldown_sec
        stable_ok = stable_track_frames >= max(1, int(min_stable_frames))
        want_pump = (
            fire_confirmed
            and tracking_locked
            and aim_established
            and stable_ok
            and not lost_timed_out
        )
        if want_pump and not self._pump_on:
            arduino.set_pump(True)
            self._pump_on = True
        elif not want_pump and self._pump_on:
            arduino.set_pump(False, force=False)
            self._pump_on = False

    def force_off(self, arduino: ArduinoController) -> None:
        if self._pump_on:
            arduino.set_pump(False, force=True)
        self._pump_on = False
