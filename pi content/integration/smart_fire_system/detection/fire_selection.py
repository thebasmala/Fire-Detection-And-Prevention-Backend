"""
Detection selection — pick the best fire bounding box from a set of candidates.

Scoring formula:
    score = confidence * 0.7 + normalised_area * 0.3

The highest-scoring detection that passes all hard filters is returned.

Hard filters:
  * Class must be "FIRE" (not SMOKE).
  * Confidence  >= min_conf (default 0.60).
  * Bounding-box area >= min_area_px.
  * Box must not touch the frame edge within edge_margin_px pixels.
  * If a fire_validator is provided, HSV + motion validation must also pass.
"""
from __future__ import annotations


def _valid(
    det: dict,
    labels: dict,
    *,
    min_conf: float,
    min_area_px: float,
    edge_margin_px: int,
    frame_w: int,
    frame_h: int,
) -> bool:
    if labels.get(det["class_id"]) != "FIRE":
        return False
    if float(det["conf"]) < min_conf:
        return False
    x1, y1, x2, y2 = det["box"]
    area = max(0, x2 - x1) * max(0, y2 - y1)
    if area < min_area_px:
        return False
    m = max(0, int(edge_margin_px))
    if x1 < m or y1 < m or x2 > frame_w - m or y2 > frame_h - m:
        return False
    return True


def pick_valid_fire(
    detections: list[dict],
    labels: dict,
    *,
    min_conf: float,
    min_area_px: float,
    edge_margin_px: int,
    frame_w: int,
    frame_h: int,
    fire_validator=None,
    frame=None,
    prev_frame=None,
) -> dict | None:
    """
    Return the highest-scoring valid FIRE detection, or None.

    If *fire_validator* is provided (a FireValidator instance), each candidate
    is additionally validated via HSV colour + motion + temporal consistency.
    *frame* and *prev_frame* must also be provided in that case.
    """
    frame_area = max(float(frame_w * frame_h), 1.0)
    best: dict | None = None
    best_score = -1.0

    for det in detections:
        if not _valid(
            det, labels,
            min_conf=min_conf,
            min_area_px=min_area_px,
            edge_margin_px=edge_margin_px,
            frame_w=frame_w,
            frame_h=frame_h,
        ):
            continue

        # Multi-modal validation gate
        if fire_validator is not None and frame is not None:
            bbox = tuple(det["box"])
            conf = float(det["conf"])
            if not fire_validator.validate(frame, prev_frame, bbox, conf):
                continue

        x1, y1, x2, y2 = det["box"]
        area = float(max(0, x2 - x1) * max(0, y2 - y1))
        conf = float(det["conf"])
        score = conf * 0.7 + (area / frame_area) * 0.3
        if score > best_score:
            best       = det
            best_score = score

    return best
