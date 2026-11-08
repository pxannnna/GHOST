"""Pressure -> floor, using the Nucleus survey (config pressure.survey).

Absolute pressure drifts with the weather (easily 1 hPa = 100 Pa a day, more
than one floor), so we never use absolute values. We *zero* once on a known
floor ("I'm on G now"), which gives the pressure the reference floor would
read right now, and compare later readings with the surveyed per-floor
differences. Re-zero before the demo.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

import numpy as np


@dataclass
class FloorState:
    floor_id: Optional[str]
    status: str                    # settled | transition | uncertain | uncalibrated
    relative_height_m: Optional[float]
    nearest_floor: Optional[str]
    distance_to_floor_m: Optional[float]
    calibration_id: Optional[str]


class FloorEstimator:
    def __init__(self, survey: Dict, pa_per_m: float = 12.0, dwell_s: float = 3.0,
                 hysteresis_m: float = 0.6, uncertain_m: float = 1.5, moving_mps: float = 0.12):
        ref = str(survey["reference_floor"])
        hpa = {str(k): float(v) for k, v in survey["readings_hpa"].items()}
        # Pa above the reference floor (positive = higher up = lower pressure).
        self.delta_pa = {f: (hpa[ref] - v) * 100.0 for f, v in hpa.items()}
        self.reference_floor = ref
        self.pa_per_m = pa_per_m
        self.dwell_s = dwell_s
        self.hysteresis_m = hysteresis_m
        self.uncertain_m = uncertain_m
        self.moving_mps = moving_mps
        self.p_ref_pa: Optional[float] = None   # what the reference floor reads right now
        self.calibration_id: Optional[str] = None
        self.calibrated_at: Optional[float] = None
        self.window: Deque[Tuple[float, float]] = deque()
        self.current: Optional[str] = None

    # -------------------------------------------------------------- calibration
    def zero(self, pressure_pa: float, at_floor: Optional[str] = None, t: Optional[float] = None) -> str:
        f = str(at_floor if at_floor is not None else self.reference_floor)
        if f not in self.delta_pa:
            raise ValueError(f"unknown floor {f!r}; survey has {sorted(self.delta_pa)}")
        self.p_ref_pa = pressure_pa + self.delta_pa[f]
        self.calibrated_at = t if t is not None else time.time()
        self.calibration_id = f"zero@{f}-{time.strftime('%H%M%S', time.localtime(self.calibrated_at))}"
        self.current = f
        return self.calibration_id

    def zero_from_window(self, at_floor: Optional[str] = None) -> Optional[str]:
        if not self.window:
            return None
        return self.zero(float(np.median([p for _, p in self.window])), at_floor)

    def set_reference(self, p_ref_pa: float, calibration_id: str, calibrated_at: float) -> None:
        self.p_ref_pa, self.calibration_id, self.calibrated_at = p_ref_pa, calibration_id, calibrated_at

    # -------------------------------------------------------------- estimation
    def height_of(self, pressure_pa: float) -> Optional[float]:
        if self.p_ref_pa is None:
            return None
        return (self.p_ref_pa - pressure_pa) / self.pa_per_m

    def floor_heights_m(self) -> Dict[str, float]:
        return {f: d / self.pa_per_m for f, d in self.delta_pa.items()}

    def update(self, t: float, pressure_pa: float) -> FloorState:
        self.window.append((t, pressure_pa))
        while self.window and self.window[0][0] < t - self.dwell_s:
            self.window.popleft()
        if self.p_ref_pa is None:
            return FloorState(None, "uncalibrated", None, None, None, None)

        ts = np.array([t for t, _ in self.window])
        ps = np.array([p for _, p in self.window])
        hs = (self.p_ref_pa - ps) / self.pa_per_m
        h = float(np.median(hs))
        # Vertical speed from a line fit: noise averages out, stairs/lift don't.
        speed = abs(float(np.polyfit(ts - ts[0], hs, 1)[0])) if len(ts) >= 3 and ts[-1] > ts[0] else 0.0
        heights = self.floor_heights_m()
        nearest = min(heights, key=lambda f: abs(heights[f] - h))
        dist = abs(heights[nearest] - h)
        span_s = self.window[-1][0] - self.window[0][0]

        if speed > self.moving_mps or span_s < 0.5 * self.dwell_s:
            return FloorState(self.current, "transition", h, nearest, dist, self.calibration_id)
        if self.current is None or nearest == self.current:
            self.current = nearest
        else:
            # Switch only if clearly nearer to the new floor (hysteresis).
            if dist + self.hysteresis_m < abs(heights[self.current] - h):
                self.current = nearest
        cur_dist = abs(heights[self.current] - h)
        status = "uncertain" if cur_dist > self.uncertain_m else "settled"
        return FloorState(self.current, status, h, nearest, cur_dist, self.calibration_id)
