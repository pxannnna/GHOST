"""Barometer floor + echoes -> ranked rooms, live.

    make room-live                                   # floor from the hub (pressure service)
    python -m services.acoustics.live --floor 2      # floor typed in (floor_source=manual)
    python -m services.acoustics.live --simulate nuc-2-rowan --floor 2 --auto 4   # mode=simulated

At each position press Enter to measure; after every position a new
`room.estimate` is sent with the ranked rooms on that floor.
Commands: Enter = measure here, r = reset (new room), q = quit.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from shared.config import ROOT, load_config
from services.acoustics.match import DEFAULT_MATCHING, PositionMeasurement, rank
from services.acoustics.measure import measure_position, print_result
from services.acoustics.rooms import load_rooms, rooms_on_floor


def floor_from_hub(hub_url: str) -> Tuple[Optional[str], str]:
    """(floor_id, status) from the latest floor.estimate the hub has seen."""
    try:
        with urllib.request.urlopen(f"{hub_url.rstrip('/')}/state", timeout=2) as r:
            st = json.loads(r.read())
        ev = (st.get("latest") or {}).get("floor.estimate")
        if not ev:
            return None, "no floor.estimate yet"
        p = ev["payload"]
        return p.get("floor_id"), p.get("status", "?")
    except Exception as e:  # hub down: keep going without a floor
        return None, f"hub unreachable ({e.__class__.__name__})"


def build_estimate(positions: List[PositionMeasurement], floor_id: Optional[str], floor_source: str,
                   matching: Dict[str, Any], rooms, floor_status: str = "settled") -> Dict[str, Any]:
    cands_rooms = rooms_on_floor(rooms, floor_id)
    out = rank(positions, cands_rooms, matching)
    # Never 'supported' unless the floor is known and settled.
    if out["status"] == "supported" and (floor_id is None or floor_status != "settled"):
        out["status"] = "candidate"
    out["floor_status"] = floor_status
    out["floor_id"] = floor_id
    out["floor_source"] = floor_source
    out["candidates"] = out["candidates"][:5]
    return out


def print_estimate(est: Dict[str, Any]) -> None:
    m = est["measured"]
    print(f"\n== room.estimate [{est['status']}] floor {est['floor_id']} ({est['floor_source']}), "
          f"{est['n_positions']} position(s)")
    print(f"   measured RT60 {m['rt60_s']} s, ceiling height {m['height_m']} m, nearest walls {m['nearest_walls_m']}")
    if est.get("estimated_dims_m"):
        d = est["estimated_dims_m"]
        print(f"   estimated room ~{d['length']} x {d['width']} m, h {d['height']} m"
              + (f"  ({est['dims_note']})" if est.get("dims_note") else ""))
    for i, c in enumerate(est["candidates"], 1):
        print(f"   {i}. {c['label']:42s} score {c['score']:.3f}  pred RT60 {c['predicted_rt60_s']} s  {c['cost_terms']}")


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--floor", help="floor id (0=G..3); default: read from the hub")
    ap.add_argument("--room", help="ground-truth label for saved data (validation only)")
    ap.add_argument("--simulate", metavar="ROOM_ID", help="simulate this room (mode=simulated)")
    ap.add_argument("--auto", type=int, metavar="N", help="measure N positions without prompting")
    ap.add_argument("--mic-height", type=float)
    ap.add_argument("--no-emit", action="store_true")
    a = ap.parse_args(argv)

    cfg = load_config()
    ecfg = cfg["echolocation"]
    matching = {**DEFAULT_MATCHING, **ecfg.get("matching", {})}
    rooms = load_rooms(ROOT / ecfg["rooms_file"])
    hub_url = f"http://{cfg['hub']['host']}:{cfg['hub']['port']}"
    mode = "simulated" if a.simulate else "live"
    client = None
    if not a.no_emit:
        from shared.client import EventClient
        client = EventClient("acoustics", mode=mode)
        client.status("echolocation", "ok", "room-live started")

    positions: List[PositionMeasurement] = []

    def current_floor() -> Tuple[Optional[str], str, str]:
        if a.floor is not None:
            return str(a.floor), "manual", "settled"
        f, st = floor_from_hub(hub_url)
        if f is None:
            print(f"   (no barometer floor: {st}; matching against all floors)")
        elif st != "settled":
            print(f"   (barometer floor {f} is '{st}')")
        return f, "measured", st

    def emit_estimate() -> None:
        floor_id, floor_source, floor_status = current_floor()
        est = build_estimate(positions, floor_id, floor_source, matching, rooms, floor_status)
        print_estimate(est)
        if client:
            client.emit("room.estimate", est)

    emit_estimate()  # 'listening'
    k = 0
    while True:
        if a.auto is not None:
            if k >= a.auto:
                break
            cmd = ""
        else:
            cmd = input(f"\n[P{k + 1}] Enter = measure, r = reset, q = quit > ").strip().lower()
        if cmd == "q":
            break
        if cmd == "r":
            positions.clear()
            k = 0
            emit_estimate()
            continue
        k += 1
        res = measure_position(f"P{k}", a.room, mic_height=a.mic_height, simulate=a.simulate,
                               seed=None if not a.simulate else 100 + k)
        print_result(res)
        if client:
            client.emit("acoustic.measurement", res.payload())
        positions.append(PositionMeasurement(res.measurement_id, res.features.rt60_s,
                                             [r.distance_m for r in res.features.reflections],
                                             res.mic_height_m, res.position_label,
                                             [r.strength_db for r in res.features.reflections]))
        emit_estimate()
    if client:
        client.close()


if __name__ == "__main__":
    main()
