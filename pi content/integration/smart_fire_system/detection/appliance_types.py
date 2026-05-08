from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApplianceDetection:
    """Immutable visualization-only appliance detection."""

    class_id: int
    label: str
    confidence: float
    box: tuple[int, int, int, int]
    cx: float
    cy: float
