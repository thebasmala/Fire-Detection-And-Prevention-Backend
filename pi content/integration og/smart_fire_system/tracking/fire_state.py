from __future__ import annotations

from dataclasses import dataclass, replace
from math import hypot

from smart_fire_system.calibration.mapper import CalibrationMapper
from smart_fire_system.vision.draw import bbox_center_float, clamp_centre_to_frame


@dataclass(frozen=True)
class LockedFireTarget:
    """One-time snapped EnvironmentMap target for a validated fire."""

    map_x: float
    map_y: float
    pan_abs: float
    servo_y_deg: float
    servo_x_deg: float


@dataclass(frozen=True)
class FireTrack:
    id: int
    centroid: tuple[float, float]
    bbox: tuple[int, int, int, int]
    confidence: float
    hit_count: int = 0
    miss_count: int = 0
    active: bool = False
    extinguished: bool = False
    locked_target: LockedFireTarget | None = None


def snap_to_environment_map(
    point: tuple[float, float],
    *,
    frame_w: int,
    frame_h: int,
    mapper: CalibrationMapper,
    invert_pan_x: bool,
    invert_tilt_y: bool,
    servo_x_center: int,
) -> LockedFireTarget:
    """
    Snap a detected fire coordinate to the nearest pre-defined calibration point.

    Confidence buffer math:
      detected frame: hit_count += 1, miss_count = 0
      missing frame:  miss_count += 1
      active when:    hit_count >= active_frames
      extinguished:   active and miss_count >= extinguish_frames
    """
    cx, cy = point
    env_point = mapper.snap_point(
        cx,
        cy,
        frame_w,
        frame_h,
        invert_pan_x=invert_pan_x,
        invert_tilt_y=invert_tilt_y,
    )
    return LockedFireTarget(
        map_x=float(env_point.grid_x),
        map_y=float(env_point.grid_y),
        pan_abs=env_point.pan_abs,
        servo_y_deg=env_point.servo_y_deg,
        servo_x_deg=float(servo_x_center) + env_point.pan_abs,
    )


class ConfidenceFireTracker:
    """Assigns fire IDs and applies consecutive-frame activation/loss buffers."""

    def __init__(
        self,
        *,
        mapper: CalibrationMapper,
        active_frames: int,
        extinguish_frames: int,
        match_radius_px: float,
        invert_pan_x: bool,
        invert_tilt_y: bool,
        servo_x_center: int,
    ):
        self._mapper = mapper
        self._active_frames = max(1, int(active_frames))
        self._extinguish_frames = max(1, int(extinguish_frames))
        self._match_radius_px = float(match_radius_px)
        self._invert_pan_x = bool(invert_pan_x)
        self._invert_tilt_y = bool(invert_tilt_y)
        self._servo_x_center = int(servo_x_center)
        self._next_id = 1
        self._tracks: dict[int, FireTrack] = {}

    @property
    def tracks(self) -> tuple[FireTrack, ...]:
        return tuple(self._tracks.values())

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    def update(
        self,
        detections: list[dict],
        *,
        frame_w: int,
        frame_h: int,
    ) -> tuple[tuple[FireTrack, ...], tuple[int, ...], tuple[int, ...]]:
        """
        Update tracks from this frame.

        Returns (active_tracks, newly_active_ids, newly_extinguished_ids).
        """
        matched_ids: set[int] = set()
        newly_active: list[int] = []
        newly_extinguished: list[int] = []

        for det in detections:
            x1, y1, x2, y2 = (int(v) for v in det["box"])
            cx, cy = clamp_centre_to_frame(
                *bbox_center_float((x1, y1, x2, y2)),
                frame_w,
                frame_h,
            )
            track_id = self._match_track((cx, cy), matched_ids)
            if track_id is None:
                track_id = self._next_id
                self._next_id += 1
                self._tracks[track_id] = FireTrack(
                    id=track_id,
                    centroid=(cx, cy),
                    bbox=(x1, y1, x2, y2),
                    confidence=float(det["conf"]),
                    hit_count=0,
                )

            prev = self._tracks[track_id]
            hit_count = prev.hit_count + 1
            active = prev.active
            locked_target = prev.locked_target

            if not active and hit_count >= self._active_frames:
                active = True
                locked_target = snap_to_environment_map(
                    (cx, cy),
                    frame_w=frame_w,
                    frame_h=frame_h,
                    mapper=self._mapper,
                    invert_pan_x=self._invert_pan_x,
                    invert_tilt_y=self._invert_tilt_y,
                    servo_x_center=self._servo_x_center,
                )
                newly_active.append(track_id)

            self._tracks[track_id] = replace(
                prev,
                centroid=(cx, cy),
                bbox=(x1, y1, x2, y2),
                confidence=float(det["conf"]),
                hit_count=hit_count,
                miss_count=0,
                active=active,
                extinguished=False,
                locked_target=locked_target,
            )
            matched_ids.add(track_id)

        for track_id, track in list(self._tracks.items()):
            if track_id in matched_ids or track.extinguished:
                continue

            miss_count = track.miss_count + 1
            extinguished = track.active and miss_count >= self._extinguish_frames
            if extinguished:
                newly_extinguished.append(track_id)

            self._tracks[track_id] = replace(
                track,
                miss_count=miss_count,
                active=False if extinguished else track.active,
                extinguished=extinguished,
            )

        self._prune_dead_tracks()
        active_tracks = tuple(
            track
            for track in self._tracks.values()
            if track.active and not track.extinguished and track.locked_target is not None
        )
        return active_tracks, tuple(newly_active), tuple(newly_extinguished)

    def _match_track(self, centroid: tuple[float, float], used_ids: set[int]) -> int | None:
        best_id: int | None = None
        best_dist = self._match_radius_px
        cx, cy = centroid
        for track_id, track in self._tracks.items():
            if track_id in used_ids or track.extinguished:
                continue
            tx, ty = track.centroid
            dist = hypot(cx - tx, cy - ty)
            if dist <= best_dist:
                best_id = track_id
                best_dist = dist
        return best_id

    def _prune_dead_tracks(self) -> None:
        for track_id, track in list(self._tracks.items()):
            if track.extinguished and track.miss_count > self._extinguish_frames:
                del self._tracks[track_id]
            elif not track.active and track.hit_count < self._active_frames and track.miss_count > self._extinguish_frames:
                del self._tracks[track_id]
