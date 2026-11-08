"""Room geometry from assets/building/rooms.json (polygons in metres)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from shared.config import ROOT

Point = Tuple[float, float]


def polygon_area(poly: Sequence[Point]) -> float:
    p = np.asarray(poly, float)
    x, y = p[:, 0], p[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def polygon_perimeter(poly: Sequence[Point]) -> float:
    p = np.asarray(poly, float)
    return float(np.sum(np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1)))


def points_in_polygon(pts: np.ndarray, poly: Sequence[Point]) -> np.ndarray:
    """Vectorised even-odd ray casting. pts: (N, 2)."""
    p = np.asarray(poly, float)
    x, y = pts[:, 0:1], pts[:, 1:2]
    x1, y1 = p[:, 0], p[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    crosses = (y1 > y) != (y2 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xint = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
    return (np.sum(crosses & (x < xint), axis=1) % 2) == 1


def distance_to_edges(pts: np.ndarray, poly: Sequence[Point]) -> np.ndarray:
    """Distance from each point to the nearest polygon edge. pts: (N, 2)."""
    p = np.asarray(poly, float)
    a = p[None, :, :]
    b = np.roll(p, -1, axis=0)[None, :, :]
    q = pts[:, None, :]
    ab = b - a
    t = np.clip(np.sum((q - a) * ab, axis=2) / np.maximum(np.sum(ab * ab, axis=2), 1e-12), 0, 1)
    proj = a + t[..., None] * ab
    return np.min(np.linalg.norm(q - proj, axis=2), axis=1)


@dataclass
class Room:
    room_id: str
    floor_id: str
    floor_ids: List[str]
    label: str
    kind: str
    polygon_m: List[Point]
    ceiling_height_m: float
    ceiling_range_m: Tuple[float, float]
    absorption: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    _wall_cache: Optional[np.ndarray] = field(default=None, repr=False)

    @property
    def area_m2(self) -> float:
        return polygon_area(self.polygon_m)

    @property
    def perimeter_m(self) -> float:
        return polygon_perimeter(self.polygon_m)

    @property
    def volume_m3(self) -> float:
        return self.area_m2 * self.ceiling_height_m

    @property
    def surface_m2(self) -> float:
        return 2 * self.area_m2 + self.perimeter_m * self.ceiling_height_m

    def nearest_wall_distances(self, min_from_wall_m: float = 1.0, n: int = 4000,
                               seed: int = 0) -> np.ndarray:
        """Distances to the nearest wall from random positions inside the room that are
        at least `min_from_wall_m` from any wall (our measurement protocol)."""
        if self._wall_cache is None:
            rng = np.random.default_rng(seed)
            p = np.asarray(self.polygon_m, float)
            lo, hi = p.min(axis=0), p.max(axis=0)
            pts = rng.uniform(lo, hi, size=(n, 2))
            pts = pts[points_in_polygon(pts, self.polygon_m)]
            d = distance_to_edges(pts, self.polygon_m)
            d = d[d >= min_from_wall_m]
            self._wall_cache = d if d.size else distance_to_edges(pts, self.polygon_m)
        return self._wall_cache

    def bbox_dims(self) -> Tuple[float, float]:
        p = np.asarray(self.polygon_m, float)
        L, W = p.max(axis=0) - p.min(axis=0)
        return float(max(L, W)), float(min(L, W))


def default_rooms_path() -> Path:
    return ROOT / "assets" / "building" / "rooms.json"


def load_rooms(path: Optional[Path] = None) -> List[Room]:
    data = json.loads(Path(path or default_rooms_path()).read_text())
    rooms = []
    for r in data["rooms"]:
        rng = r.get("ceiling_height_range_m") or [r["ceiling_height_m"]] * 2
        meta = {k: v for k, v in r.items() if k not in {
            "room_id", "floor_id", "floor_ids", "label", "kind", "polygon_m",
            "ceiling_height_m", "ceiling_height_range_m", "absorption"}}
        rooms.append(Room(
            room_id=r["room_id"], floor_id=str(r["floor_id"]),
            floor_ids=[str(f) for f in r.get("floor_ids", [r["floor_id"]])],
            label=r.get("label", r["room_id"]), kind=r.get("kind", "room"),
            polygon_m=[tuple(p) for p in r["polygon_m"]],
            ceiling_height_m=float(r["ceiling_height_m"]),
            ceiling_range_m=(float(rng[0]), float(rng[1])),
            absorption=r.get("absorption"), meta=meta))
    return rooms


def rooms_on_floor(rooms: Sequence[Room], floor_id: Optional[str]) -> List[Room]:
    if floor_id is None:
        return list(rooms)
    return [r for r in rooms if str(floor_id) in r.floor_ids]
