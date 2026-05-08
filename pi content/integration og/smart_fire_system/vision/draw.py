from __future__ import annotations

import cv2

COLOR_FIRE = (0, 0, 255)
COLOR_FPS = (0, 200, 255)
COLOR_ZONE_LINE = (80, 80, 80)
COLOR_DEBUG_HUD = (0, 255, 255)

ZONE_COLORS = {
    1: (0, 60, 200),
    4: (0, 120, 200),
    2: (0, 160, 200),
    3: (0, 200, 200),
}


def _quadrant_fullscreen_split(frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
    if frame_w < 1 or frame_h < 1:
        return 1, 1, 1, 1
    w1 = frame_w // 2
    h1 = frame_h // 2
    w2 = frame_w - w1
    h2 = frame_h - h1
    return w1, h1, w2, h2


def frame_center(frame_w: int, frame_h: int) -> tuple[float, float]:
    return (frame_w - 1) * 0.5, (frame_h - 1) * 0.5


def clamp_centre_to_frame(cx: float, cy: float, frame_w: int, frame_h: int) -> tuple[float, float]:
    max_x = max(float(frame_w - 1), 0.0)
    max_y = max(float(frame_h - 1), 0.0)
    return max(0.0, min(max_x, cx)), max(0.0, min(max_y, cy))


def bbox_center_float(box: list[int] | tuple[int, ...]) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) * 0.5, (y1 + y2) * 0.5


def cxcy_to_zone(cx: float, cy: float, frame_w: int, frame_h: int) -> int:
    """
    Quadrant zones (image: x right, y down):
      top-left    → zone 3 (LAMP3)    | top-right    → zone 2 (LAMP2)
      bottom-left → zone 4 (LAMP4)    | bottom-right → zone 1 (LAMP1)
    """
    w1, h1, _, _ = _quadrant_fullscreen_split(frame_w, frame_h)
    lx = max(0.0, min(float(frame_w - 1), cx))
    ly = max(0.0, min(float(frame_h - 1), cy))
    idx = (1 if ly >= h1 else 0) * 2 + (1 if lx >= w1 else 0)
    return (3, 2, 4, 1)[idx]


def draw_detections(frame, detections, labels, color):
    for det in detections:
        x1, y1, x2, y2 = det["box"]
        lbl = f"{labels.get(det['class_id'], '?')} {det['conf']:.2f}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, lbl, (x1, max(y1 - 8, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


def draw_zones(frame, frame_w, frame_h, active_zone: int):
    if frame_w < 1 or frame_h < 1:
        return
    w1, h1, w2, h2 = _quadrant_fullscreen_split(frame_w, frame_h)
    rects = {
        3: (0, 0, w1, h1),
        2: (w1, 0, w2, h1),
        4: (0, h1, w1, h2),
        1: (w1, h1, w2, h2),
    }
    labels = {3: (4, 16), 2: (w1 + 4, 16), 4: (4, h1 + 16), 1: (w1 + 4, h1 + 16)}
    if active_zone in ZONE_COLORS:
        qx, qy, qw, qh = rects[active_zone]
        qx2, qy2 = qx + qw - 1, qy + qh - 1
        overlay = frame.copy()
        cv2.rectangle(overlay, (qx, qy), (qx2, qy2), ZONE_COLORS[active_zone], -1)
        cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
        cv2.putText(
            frame,
            f"ZONE {active_zone} | LAMP{active_zone} OFF",
            (qx + 4, min(qy2 - 6, frame_h - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            ZONE_COLORS[active_zone],
            1,
        )
    fx2, fy2 = frame_w - 1, frame_h - 1
    cv2.rectangle(frame, (0, 0), (fx2, fy2), COLOR_ZONE_LINE, 2)
    mid_x, mid_y = w1, h1
    cv2.line(frame, (mid_x, 0), (mid_x, fy2), COLOR_ZONE_LINE, 1)
    cv2.line(frame, (0, mid_y), (fx2, mid_y), COLOR_ZONE_LINE, 1)
    for zi, (tx, ty) in labels.items():
        cv2.putText(frame, f"Z{zi}", (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_ZONE_LINE, 1)


def draw_crosshair(frame, frame_w: int, frame_h: int):
    cx, cy = frame_center(frame_w, frame_h)
    cv2.drawMarker(frame, (int(round(cx)), int(round(cy))), (200, 200, 200), cv2.MARKER_CROSS, 16, 1)


def draw_aim_debug_hud(
    frame,
    *,
    cx: float,
    cy: float,
    frame_w: int,
    frame_h: int,
    zone: int,
    servox_cmd: int,
    servoy_cmd: int,
    pan_steps_cmd: int,
    stepper_sum: int,
    servox_sent: int | None,
    servoy_sent: int | None,
    conf: float,
    mirror_x: bool,
    pump_on: bool,
    dual_servo_mode: bool,
):
    cxf, cyf = frame_center(frame_w, frame_h)
    pan_line = (
        f"servox_cmd: {servox_cmd} deg  servox_sent: {servox_sent if servox_sent is not None else '-'} deg"
        if dual_servo_mode
        else f"X cmd: {pan_steps_cmd:+d} steps  stepper_sum: {stepper_sum}"
    )
    lines = [
        f"cx,cy: ({cx:.1f},{cy:.1f})  err: ({cx - cxf:.1f},{cy - cyf:.1f})",
        f"zone: {zone}  conf: {conf:.2f}  mirror_x: {mirror_x}",
        f"servoy_cmd: {servoy_cmd} deg  servoy_sent: {servoy_sent if servoy_sent is not None else '-'} deg",
        f"{pan_line}  pump: {int(pump_on)}",
    ]
    y0 = 92
    for i, line in enumerate(lines):
        cv2.putText(frame, line, (10, y0 + i * 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_DEBUG_HUD, 1, cv2.LINE_AA)
