from __future__ import annotations

from smart_fire_system.detection.appliance_types import ApplianceDetection
from smart_fire_system.detection.hailo_detector import HailoDetector


class ApplianceDetector:
    """Visualization-only appliance detector wrapper."""

    def __init__(
        self,
        model_path: str,
        labels: dict[int, str],
        min_confidence: float,
        *,
        debug: bool = False,
        min_infer_interval_s: float = 0.0,
        infer_frame_stride: int = 1,
    ) -> None:
        self._labels = labels
        self._detector = HailoDetector(
            model_path=model_path,
            labels=labels,
            min_threshold=min_confidence,
            raw_fire_box_prints=0,
            debug=debug,
            min_infer_interval_s=min_infer_interval_s,
            infer_frame_stride=infer_frame_stride,
        )

    @property
    def last_infer_ms(self) -> float:
        return self._detector.last_infer_ms

    def process_frame(self, frame, *, timestamp: float | None = None) -> list[ApplianceDetection]:
        raw = self._detector.process_frame(frame, timestamp=timestamp)
        out: list[ApplianceDetection] = []
        for det in raw:
            x1, y1, x2, y2 = det["box"]
            cx = (x1 + x2) * 0.5
            cy = (y1 + y2) * 0.5
            class_id = int(det["class_id"])
            out.append(
                ApplianceDetection(
                    class_id=class_id,
                    label=str(self._labels.get(class_id, "unknown")),
                    confidence=float(det["conf"]),
                    box=(int(x1), int(y1), int(x2), int(y2)),
                    cx=float(cx),
                    cy=float(cy),
                )
            )
        return out
