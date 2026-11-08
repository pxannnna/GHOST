"""Plan B: match echo measurements against rooms from the floor plan.

For every room on the barometer floor we *predict* what the echoes should look
like from its geometry in rooms.json, and compare with what we measured:

1. Reverberation time. Predicted with Eyring's formula from the room volume and
   surface area, with a mean absorption for the room kind (calibrated on rooms
   we tape-measured). Compared on a log scale: RT60 grows with room size.
2. Ceiling height. A flat ceiling is the same distance above the laptop at
   every position, while wall distances change; a reflection distance that
   repeats across positions is therefore the ceiling. Compared with the room's
   ceiling height (or its min-max range for raked theatres).
3. Nearest wall. At each position the first lateral reflection is the nearest
   wall. Compared with the nearest-wall distances predicted from the room's
   polygon (random positions >=1 m from walls, our protocol). This is where the
   room's *shape* enters, not just its size.

Each term is a squared z-score; the total cost becomes score = exp(-cost/2).
The score is a match score, NOT a probability, and is never shown as a %.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from services.acoustics.rooms import Room

DEFAULT_MATCHING: Dict[str, Any] = {
    "absorption_by_kind": {"lecture_theatre": 0.28, "studio": 0.22, "lab": 0.12,
                           "open_area": 0.18, "retail": 0.18, "study_room": 0.2, "room": 0.2},
    "absorption_scale": 1.0,
    "sigma_log_rt60": 0.35,
    "sigma_height_m": 0.4,
    "sigma_log_wall": 0.6,
    "min_wall_m": 1.0,
    "ceiling_tolerance_m": 0.15,
    "no_match_cost": 9.0,
    "ambiguous_ratio": 0.5,
    "min_positions_supported": 2,
    "assumed_aspect": 1.3,
    "sigma_log_span": 0.25,
    "span_tolerance_m": 0.15,
    "span_top_n": 4,
    "use_spans": False,
    # One noisy clue must not veto an otherwise good room: each term is capped, so a single
    # bad clue costs at most 2.5 sigma while two bad clues still reject the room. RT60 is the
    # most direct physics term, so it may count much more before it is capped.
    "term_cap": {"rt60": 25.0, "height": 6.25, "wall": 6.25},
    "max_ceiling_margin_m": 1.0,
    # "Not a room" hypotheses. If one of these explains the echoes better than every
    # real room, the answer is no_match: GHOST only claims to locate you INSIDE a room.
    "non_room_models": [
        {"id": "corridor", "label": "corridor", "length_m": 25.0, "width_m": 2.4,
         "ceiling_m": [2.4, 4.0], "absorption": 0.15},
        # An open area is NOT modelled: acoustically it is indistinguishable from a big
        # lecture theatre, and in simulation it made Elm come out as "not a room".
    ],
}


@dataclass
class PositionMeasurement:
    measurement_id: str
    rt60_s: Optional[float]
    reflection_distances_m: List[float]
    mic_height_m: float = 0.75
    position_label: Optional[str] = None
    reflection_strengths_db: Optional[List[float]] = None  # same order as distances


@dataclass
class Combined:
    n_positions: int
    rt60_s: Optional[float]
    ceiling_distance_m: Optional[float]
    height_m: Optional[float]
    nearest_walls_m: List[float] = field(default_factory=list)
    spans_m: List[float] = field(default_factory=list)

    @property
    def nearest_wall_median_m(self) -> Optional[float]:
        return float(np.median(self.nearest_walls_m)) if self.nearest_walls_m else None


def combine(positions: Sequence[PositionMeasurement], cfg: Dict[str, Any] = DEFAULT_MATCHING,
            max_height_m: Optional[float] = None) -> Combined:
    rts = [p.rt60_s for p in positions if p.rt60_s]
    rt = float(np.median(rts)) if rts else None
    tol = cfg["ceiling_tolerance_m"]
    mic_h = float(np.median([p.mic_height_m for p in positions])) if positions else 0.75

    # Ceiling: a distance (>=1.4 m) seen at >= 60% of positions (needs >=2 positions).
    # A candidate that would put the ceiling above `max_height_m` (the tallest room that can
    # be on this floor, plus a margin) is multi-bounce clutter, not a ceiling.
    ceiling = None
    if len(positions) >= 2:
        need = max(2, int(np.ceil(0.6 * len(positions))))
        cands = sorted({round(d, 2) for p in positions for d in p.reflection_distances_m
                        if d >= 1.4 and (max_height_m is None or d + mic_h <= max_height_m)})
        best = (0, None)
        for c in cands:
            hits = [min((d for d in p.reflection_distances_m if abs(d - c) <= tol), key=lambda d: abs(d - c), default=None)
                    for p in positions]
            hits = [h for h in hits if h is not None]
            if len(hits) >= need and len(hits) > best[0]:
                best = (len(hits), float(np.median(hits)))
        ceiling = best[1]
        # Sound that bounces ceiling -> floor (or floor -> ceiling) arrives at one-way distance
        # H = ceiling echo + mic height, so it can look like a ceiling echo of a taller room.
        # If an echo also repeats one mic-height closer, that closer one is the real ceiling.
        if ceiling is not None and ceiling - mic_h >= 1.4:
            partner = [min((d for d in p.reflection_distances_m if abs(d - (ceiling - mic_h)) <= tol),
                           key=lambda d: abs(d - (ceiling - mic_h)), default=None) for p in positions]
            partner = [d for d in partner if d is not None]
            if len(partner) >= need:      # as well supported as any ceiling candidate, not a chance echo
                ceiling = float(np.median(partner))
    height = None if ceiling is None else ceiling + mic_h

    walls, laterals = [], []
    for p in positions:
        strengths = p.reflection_strengths_db or [0.0] * len(p.reflection_distances_m)
        lateral = [(d, st) for d, st in zip(p.reflection_distances_m, strengths)
                   if d >= cfg["min_wall_m"] - tol
                   and abs(d - p.mic_height_m) > tol                   # floor
                   and (ceiling is None or abs(d - ceiling) > tol)     # ceiling
                   and (height is None or abs(d - height) > tol)]      # floor-ceiling double bounce
        if lateral:
            walls.append(min(d for d, _ in lateral))
        # strongest few lateral echoes = best candidates for first-order walls
        laterals.append([d for d, _ in sorted(lateral, key=lambda x: -x[1])[:cfg.get("span_top_n", 4)]])
    return Combined(len(positions), rt, ceiling, height, walls, find_spans(laterals, cfg))


def find_spans(laterals: Sequence[Sequence[float]], cfg: Dict[str, Any] = DEFAULT_MATCHING,
               max_spans: int = 2) -> List[float]:
    """Room spans from opposite-wall pairs.

    Standing anywhere between two parallel walls, the two wall distances add up
    to the wall-to-wall span. A span is accepted only if, at EVERY position
    (>=3), some pair of strong lateral echoes sums to it within tolerance, AND
    the individual distances change between positions (otherwise it's the same
    two surfaces seen from one spot, not evidence of a span)."""
    if len(laterals) < 3 or any(len(L) < 2 for L in laterals):
        return []
    tol = cfg.get("span_tolerance_m", 0.15)
    pairs = [[(a + b, min(a, b)) for i, a in enumerate(L) for b in L[i + 1:]] for L in laterals]
    found: List[tuple] = []
    for c in sorted({round(x, 2) for P in pairs for x, _ in P}):
        hits = []
        for P in pairs:
            best = min(P, key=lambda x: abs(x[0] - c))
            if abs(best[0] - c) > tol:
                break
            hits.append(best)
        else:
            sums, mins = zip(*hits)
            if np.std(mins) >= 0.3:  # the near wall moved -> positions really differ
                found.append((-float(np.std(sums)), float(np.median(sums))))
    spans: List[float] = []
    for _, sp in sorted(found, reverse=True):
        if all(abs(sp - o) > 1.0 for o in spans):
            spans.append(round(sp, 2))
        if len(spans) >= max_spans:
            break
    return spans


def absorption_for(room: Room, cfg: Dict[str, Any]) -> float:
    a = room.absorption or cfg["absorption_by_kind"].get(room.kind, cfg["absorption_by_kind"]["room"])
    return float(np.clip(a * cfg.get("absorption_scale", 1.0), 0.02, 0.9))


def eyring_rt60(volume: float, surface: float, alpha: float) -> float:
    return float(-0.161 * volume / (surface * np.log(1.0 - alpha)))


def predict(room: Room, cfg: Dict[str, Any] = DEFAULT_MATCHING) -> Dict[str, float]:
    walls = room.nearest_wall_distances(cfg["min_wall_m"])
    return {
        "rt60_s": eyring_rt60(room.volume_m3, room.surface_m2, absorption_for(room, cfg)),
        "height_min_m": room.ceiling_range_m[0],
        "height_max_m": room.ceiling_range_m[1],
        "nearest_wall_median_m": float(np.median(walls)),
        "nearest_wall_max_m": float(np.max(walls)),
    }


def room_cost(c: Combined, room: Room, cfg: Dict[str, Any] = DEFAULT_MATCHING) -> Dict[str, Any]:
    pred = predict(room, cfg)
    terms: Dict[str, float] = {}
    if c.rt60_s:
        terms["rt60"] = (np.log(c.rt60_s / pred["rt60_s"]) / cfg["sigma_log_rt60"]) ** 2
    if c.height_m is not None:
        dev = max(pred["height_min_m"] - c.height_m, 0.0, c.height_m - pred["height_max_m"])
        terms["height"] = (dev / cfg["sigma_height_m"]) ** 2
    if len(c.nearest_walls_m) >= 2:
        m = c.nearest_wall_median_m
        t = (np.log(m / pred["nearest_wall_median_m"]) / cfg["sigma_log_wall"]) ** 2
        # A nearest wall farther away than anywhere in this room allows = room too small.
        over = max(m - pred["nearest_wall_max_m"] - 0.5, 0.0)
        terms["wall"] = float(min(t, 4.0) + (over / 0.5) ** 2)
    if c.spans_m and cfg.get("use_spans", False):
        L, W = room.bbox_dims()
        sig = cfg.get("sigma_log_span", 0.25)
        terms["span"] = float(sum(min(min(abs(np.log(sp / L)), abs(np.log(sp / W))) / sig, 2.0) ** 2
                                  for sp in c.spans_m))
    caps = cfg.get("term_cap", {})
    terms = {k: float(min(v, caps.get(k, np.inf))) for k, v in terms.items()}
    cost = float(sum(terms.values()))
    return {"room": room, "cost": cost, "score": float(np.exp(-cost / 2)), "terms": terms, "predicted": pred}


def estimate_dims(c: Combined, cfg: Dict[str, Any] = DEFAULT_MATCHING) -> Optional[Dict[str, float]]:
    """Rough room size, labelled by evidence:
    - height: ceiling echo (else assumed 4.0 m);
    - length/width: wall-to-wall spans from echoes when found;
    - otherwise floor area by inverting Eyring at a typical absorption, plus the
      range for absorption 0.12-0.30 (RT60 alone pins size only loosely)."""
    if not c.rt60_s:
        return None
    H = c.height_m or 4.0
    k = cfg["assumed_aspect"]

    def area_for(alpha: float) -> float:
        def rt_for(area: float) -> float:
            L, W = np.sqrt(area * k), np.sqrt(area / k)
            return eyring_rt60(area * H, 2 * area + 2 * (L + W) * H, alpha)
        lo, hi = 4.0, 5000.0
        if rt_for(hi) < c.rt60_s:
            return hi
        if rt_for(lo) > c.rt60_s:
            return lo
        for _ in range(60):
            mid = np.sqrt(lo * hi)
            lo, hi = (mid, hi) if rt_for(mid) < c.rt60_s else (lo, mid)
        return float(np.sqrt(lo * hi))

    alpha = float(np.median(list(cfg["absorption_by_kind"].values()))) * cfg.get("absorption_scale", 1.0)
    area = area_for(alpha)
    out = {"height": round(float(H), 2),
           "floor_area_m2": round(area, 0),
           "floor_area_min_m2": round(area_for(0.12), 0),
           "floor_area_max_m2": round(area_for(0.30), 0)}
    if not cfg.get("use_spans", False):
        out["length"], out["width"] = round(float(np.sqrt(area * k)), 1), round(float(np.sqrt(area / k)), 1)
    elif len(c.spans_m) >= 2:
        out["length"], out["width"] = max(c.spans_m), min(c.spans_m)
    elif len(c.spans_m) == 1:
        out["length"] = c.spans_m[0]
        out["width"] = round(min(area / c.spans_m[0], c.spans_m[0]), 1)
    else:
        out["length"], out["width"] = round(float(np.sqrt(area * k)), 1), round(float(np.sqrt(area / k)), 1)
    return out


def non_room_models(cfg: Dict[str, Any]) -> List[Room]:
    out = []
    for m in cfg.get("non_room_models", []):
        L, W = m["length_m"], m["width_m"]
        lo, hi = m["ceiling_m"]
        out.append(Room(f"non-room:{m['id']}", "*", [], m["label"], "non_room",
                        [(0, 0), (L, 0), (L, W), (0, W)], (lo + hi) / 2, (lo, hi),
                        absorption=m["absorption"], meta={"non_room": True}))
    return out


def rank(positions: Sequence[PositionMeasurement], rooms: Sequence[Room],
         cfg: Dict[str, Any] = DEFAULT_MATCHING) -> Dict[str, Any]:
    """Returns a dict ready to become a room.estimate payload (minus floor fields)."""
    max_h = (max(r.ceiling_range_m[1] for r in rooms) + cfg.get("max_ceiling_margin_m", 1.0)) if rooms else None
    c = combine(positions, cfg, max_h)
    base = {"method": "echo-physics-vs-floorplan v1 (Eyring RT60 + ceiling echo + nearest wall)",
            "supporting_measurement_ids": [p.measurement_id for p in positions],
            "n_positions": c.n_positions,
            "measured": {"rt60_s": c.rt60_s, "ceiling_distance_m": c.ceiling_distance_m,
                         "height_m": None if c.height_m is None else round(c.height_m, 2),
                         "nearest_walls_m": [round(w, 2) for w in c.nearest_walls_m],
                         "spans_m": c.spans_m}}
    if not positions or not rooms or c.rt60_s is None:
        return {**base, "status": "listening", "candidates": [], "estimated_dims_m": None}

    results = sorted((room_cost(c, r, cfg) for r in rooms), key=lambda x: x["cost"])
    nulls = sorted((room_cost(c, r, cfg) for r in non_room_models(cfg)), key=lambda x: x["cost"])
    best_null = nulls[0] if nulls else None
    cands = [{"room_id": r["room"].room_id, "label": r["room"].label, "score": round(r["score"], 4),
              "cost_terms": {k: round(float(v), 2) for k, v in r["terms"].items()},
              "predicted_rt60_s": round(r["predicted"]["rt60_s"], 2)} for r in results]

    best = results[0]
    non_room = None if best_null is None else {
        "best": best_null["room"].label, "score": round(best_null["score"], 4),
        "cost_terms": {k: round(float(v), 2) for k, v in best_null["terms"].items()}}
    if best["cost"] > cfg["no_match_cost"]:
        status = "no_match"
    elif best_null is not None and best_null["score"] > best["score"]:
        status = "no_match"   # sounds more like a corridor / open area than any room
    elif c.n_positions < cfg["min_positions_supported"]:
        status = "candidate"
    elif len(results) > 1 and results[1]["score"] >= cfg["ambiguous_ratio"] * best["score"]:
        status = "ambiguous"
    else:
        status = "supported"
    dims = estimate_dims(c, cfg)
    return {**base, "status": status, "candidates": cands, "non_room": non_room,
            "estimated_dims_m": dims,
            "dims_note": "; ".join(x for x in [
                None if c.height_m else "height assumed 4.0 m (no consistent ceiling echo yet)",
                "length/width from wall-to-wall echoes" if (c.spans_m and cfg.get("use_spans", False))
                else "length/width from RT60 only (rough; see floor_area_min/max)"] if x)}
