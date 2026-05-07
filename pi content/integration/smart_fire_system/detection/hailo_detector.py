from __future__ import annotations

import sys
import time

import cv2
import numpy as np
from picamera2.devices import Hailo


def pick_best_fire(detections: list[dict], labels: dict, min_conf: float) -> dict | None:
    best = None
    best_area = -1.0
    best_conf = -1.0
    for det in detections:
        if labels.get(det["class_id"]) != "FIRE":
            continue
        conf = float(det["conf"])
        if conf < min_conf:
            continue
        x1, y1, x2, y2 = det["box"]
        area = max(0, x2 - x1) * max(0, y2 - y1)
        if area > best_area or (area == best_area and conf > best_conf):
            best = det
            best_area = float(area)
            best_conf = conf
    return best


class HailoDetector:
    def __init__(
        self,
        model_path: str,
        labels: dict,
        min_threshold: float,
        raw_fire_box_prints: int = 0,
        debug: bool = True,
        *,
        min_infer_interval_s: float = 0.0,
        infer_frame_stride: int = 1,
    ):
        print(f"[Hailo] Loading: {model_path}")
        try:
            self.hailo = Hailo(model_path)
            self.model_h, self.model_w, _ = self.hailo.get_input_shape()
        except Exception as e:
            print(f"[Hailo] Failed to load model: {e}")
            sys.exit(1)
        self.labels = labels
        self.min_threshold = float(min_threshold)
        self._raw_fire_box_prints = int(raw_fire_box_prints)
        self.debug = bool(debug)
        self.last_infer_ms = 0.0
        self._min_infer_interval_s = float(max(0.0, min_infer_interval_s))
        self._infer_stride = max(1, int(infer_frame_stride))
        self._frame_index = 0
        self._last_infer_ts = float("-inf")
        self._last_detections: list[dict] = []

    def process_frame(self, frame: np.ndarray, *, timestamp: float | None = None) -> list[dict]:
        ts = time.time() if timestamp is None else float(timestamp)
        self._frame_index += 1
        stride_ok = (self._frame_index % self._infer_stride) == 0
        interval_ok = (ts - self._last_infer_ts) >= self._min_infer_interval_s
        if self._min_infer_interval_s > 0.0 or self._infer_stride > 1:
            if not (stride_ok and interval_ok):
                return list(self._last_detections)
        try:
            t0 = time.time()
            h_orig, w_orig = frame.shape[:2]
            resized = cv2.resize(frame, (self.model_w, self.model_h))
            results = self.hailo.run(resized)
            self.last_infer_ms = (time.time() - t0) * 1000.0
            detections: list[dict] = []
            raw_fire_printed = False
            for class_id, class_dets in enumerate(results):
                if self.labels.get(class_id) == "SMOKE":
                    continue
                for det in class_dets:
                    score = float(det[4])
                    if score < self.min_threshold:
                        continue
                    y0, x0, y1, x1 = map(float, det[:4])
                    y0, x0, y1, x1 = max(0.0, min(1.0, y0)), max(0.0, min(1.0, x0)), max(0.0, min(1.0, y1)), max(0.0, min(1.0, x1))
                    if y1 < y0:
                        y0, y1 = y1, y0
                    if x1 < x0:
                        x0, x1 = x1, x0
                    if self.debug and not raw_fire_printed and self._raw_fire_box_prints > 0 and self.labels.get(class_id) == "FIRE":
                        print(f"[Hailo] raw det[:4] (y0,x0,y1,x1) = {[y0, x0, y1, x1]}")
                        self._raw_fire_box_prints -= 1
                        raw_fire_printed = True
                    x1p = int(round(x0 * float(w_orig - 1)))
                    x2p = int(round(x1 * float(w_orig - 1)))
                    y1p = int(round(y0 * float(h_orig - 1)))
                    y2p = int(round(y1 * float(h_orig - 1)))
                    if x2p < x1p:
                        x1p, x2p = x2p, x1p
                    if y2p < y1p:
                        y1p, y2p = y2p, y1p
                    detections.append({"box": [x1p, y1p, x2p, y2p], "conf": score, "class_id": class_id})
            self._last_detections = detections
            self._last_infer_ts = ts
            return detections
        except Exception as e:
            print(f"[Hailo] Inference error: {e}")
            return list(self._last_detections)
