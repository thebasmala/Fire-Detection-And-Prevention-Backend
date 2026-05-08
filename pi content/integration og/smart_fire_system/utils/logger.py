from __future__ import annotations

import json
import queue
import threading

import cv2


def log_json(path: str, data: dict) -> None:
    with open(path, "a") as f:
        f.write(json.dumps(data) + "\n")


class FrameWriter:
    def __init__(self, max_queue: int = 2):
        self._queue: queue.Queue[tuple[str, object] | None] = queue.Queue(maxsize=max_queue)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            path, frame = item
            try:
                cv2.imwrite(path, frame)
            except Exception:
                pass

    def enqueue(self, path: str, frame) -> None:
        try:
            self._queue.put_nowait((path, frame.copy()))
        except queue.Full:
            try:
                _ = self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait((path, frame.copy()))
            except queue.Full:
                pass

    def close(self) -> None:
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
