"""Diurnal load model with day-of-week variation.

load_factor(hour, weekday, profile) -> 0..1 traffic intensity for a cell.
  - high-traffic sites peak in business/transit hours (~10:00 and ~18:00)
  - residential sites peak morning (~08:00) and evening (~21:00)
  - weekends scaled by WEEKEND_FACTOR
"""
from __future__ import annotations

import math
import random

WEEKEND_FACTOR = 0.75

# profile -> (base, [(centre_hour, amplitude, width), ...])
_CURVES = {
    "high": (0.15, [(10.0, 0.85, 3.0), (18.0, 1.0, 3.0)]),
    "res":  (0.12, [(8.0, 0.7, 2.5), (21.0, 1.0, 3.0)]),
}


def diurnal(hour: float, profile: str) -> float:
    base, centres = _CURVES.get(profile, _CURVES["res"])
    val = base
    for c, amp, width in centres:
        val += amp * math.exp(-((hour - c) ** 2) / (2 * width ** 2))
    return min(1.0, val)


def load_factor(hour: float, weekday: int, profile: str, rng: random.Random) -> float:
    val = diurnal(hour, profile)
    if weekday >= 5:  # Saturday=5, Sunday=6
        val *= WEEKEND_FACTOR
    val *= rng.uniform(0.85, 1.06)
    return max(0.02, min(1.0, val))
