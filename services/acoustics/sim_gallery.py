"""A gallery of SIMULATED rooms: recordings, plots and a small data file. Never measured data.

    python -m services.acoustics.sim_gallery
    python -m services.acoustics.sim_gallery --rooms nuc-2-rowan nuc-0-elm --positions 4

For each room it simulates N positions with `simulate.field_ir` (a shoebox of the room's bounding
box and measured ceiling height, calibrated against the real study-room recordings), pushes the
simulated recordings through the SAME analysis as real ones, runs the matcher, and writes:

  data/echo/sim-<room>/P*/          the simulated recordings (git-ignored, like real ones)
  docs/figures/simulated/<room>/    plots, every one stamped "SIMULATED DATA"
  docs/figures/simulated/simulated_rooms.json   features + true surface distances + matcher result

What it can show: what the method should look like in other kinds of room. What it cannot show:
that the method works in them. The simulation and the matcher share the same physics, so a good
match here is partly built in.
"""
from __future__ import annotations

import argparse
import json
import zlib
from typing import Any, Dict, List, Optional

from shared.config import ROOT, load_config
from services.acoustics import plot as P
from services.acoustics.live import build_estimate
from services.acoustics.match import DEFAULT_MATCHING, absorption_for
from services.acoustics.measure import measure_position
from services.acoustics.reanalyze import latest_per_position
from services.acoustics.rooms import load_rooms

# One room of each kind, flat-floor approximations (the real Elm/Larch/Yew floors are raked).
DEFAULT_ROOMS = ["nuc-2-studyroom-se", "nuc-2-rowan", "nuc-0-elm", "nuc-1-larch", "nuc-3-chemlab"]
MIC_HEIGHT = 0.6


def run_room(room_id: str, n_pos: int, rooms, ecfg: Dict[str, Any], matching: Dict[str, Any], out_root) -> Dict[str, Any]:
    room = next(r for r in rooms if r.room_id == room_id)
    tag = f"sim-{room_id}"
    base = zlib.crc32(room_id.encode()) % 1000 * 10
    for k in range(1, n_pos + 1):
        measure_position(f"P{k}", room_tag=tag, simulate=room_id, seed=base + k, mic_height=MIC_HEIGHT, save=True)
    dirs = latest_per_position(tag)[-n_pos:]
    ps = [P.load_position(d, ecfg) for d in dirs]
    out = out_root / room_id
    out.mkdir(parents=True, exist_ok=True)
    L, W = room.bbox_dims()
    ceiling = room.ceiling_height_m
    max_dist = 12.0 if max(L, W) > 12 else 8.0
    if room_id == DEFAULT_ROOMS[0]:
        P.fig_recording(ps[0], out / "1_recording.png")
    P.fig_traces(ps, ecfg, ceiling, max_dist, out / "2_echo_traces.png")
    P.fig_concept(ps[0], ecfg, absorption_for(room, matching), out / "0_ideal_vs_realistic.png", max_dist=min(max_dist, 8.0))
    P.fig_story(ps[0], ecfg, ceiling, out / "5_where_it_hits.png")
    agree = P.fig_agreement(ps, ecfg, ceiling, out / "3_agreement.png")
    P.fig_decay(ps, out / "4_decay.png")

    from services.acoustics.match import PositionMeasurement
    pm = [PositionMeasurement(p["dir"].name, p["feats"].rt60_s, [r.distance_m for r in p["feats"].reflections],
                              p["mic_h"], p["label"], [r.strength_db for r in p["feats"].reflections]) for p in ps]
    est = build_estimate(pm, room.floor_ids[0], "manual", matching, rooms)
    true_ceiling_echo = round(ceiling - MIC_HEIGHT, 2)
    return {
        "room_id": room_id, "label": room.label, "kind": room.kind, "floor": room.floor_ids[0],
        "simulated_as_box_m": [round(L, 1), round(W, 1), ceiling], "mic_height_m": MIC_HEIGHT,
        "true_ceiling_echo_m": true_ceiling_echo,
        "positions_where_all_agree_m": [round(float((a + b) / 2), 2) for a, b in agree],
        "matcher": {"status": est["status"], "measured": est["measured"],
                    "top3": [{"room_id": c["room_id"], "score": c["score"]} for c in est["candidates"][:3]]},
        "positions": [{"label": p["label"], "true_surfaces_one_way_m": p["truth"]["surfaces_one_way_m"],
                       "source_xyz_m": p["truth"]["source_xyz_m"], "features": p["feats"].to_dict()} for p in ps],
    }


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rooms", nargs="+", default=DEFAULT_ROOMS)
    ap.add_argument("--positions", type=int, default=4)
    ap.add_argument("--out", default=str(ROOT / "docs" / "figures" / "simulated"))
    a = ap.parse_args(argv)
    from pathlib import Path
    out_root = Path(a.out)
    out_root.mkdir(parents=True, exist_ok=True)
    ecfg = load_config()["echolocation"]
    matching = {**DEFAULT_MATCHING, **ecfg.get("matching", {})}
    rooms = load_rooms(ROOT / ecfg["rooms_file"])
    results = []
    for rid in a.rooms:
        r = run_room(rid, a.positions, rooms, ecfg, matching, out_root)
        results.append(r)
        m = r["matcher"]
        print(f"{rid:20s} box {r['simulated_as_box_m']}  true ceiling echo {r['true_ceiling_echo_m']} m | "
              f"all-agree at {r['positions_where_all_agree_m']} | measured height {m['measured']['height_m']} "
              f"(true {r['simulated_as_box_m'][2]}) RT60 {m['measured']['rt60_s']} | {m['status']} "
              f"top: {[c['room_id'] for c in m['top3']]}")
    (out_root / "simulated_rooms.json").write_text(json.dumps({
        "_comment": "SIMULATED, not measured. Generated by services.acoustics.sim_gallery (field_ir model calibrated on the "
                    "real study-room recordings). Ground truth (true_surfaces_one_way_m) is known because it is a simulation.",
        "mode": "simulated", "rooms": results}, indent=1, default=float) + "\n")
    print(f"wrote plots + simulated_rooms.json to {out_root}")


if __name__ == "__main__":
    main()
