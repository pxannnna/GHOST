"""Re-run saved recordings through the current analysis pipeline. No audio hardware needed.

    python -m services.acoustics.reanalyze --room nuc-3-studyroom --floor 3
    python -m services.acoustics.reanalyze --room nuc-3-studyroom --floor 3 --since 20261107-22 --mic-height 0.45

Takes the newest recording of each position label (P1, P2, ...) in data/echo/<room>/,
optionally only those whose timestamp is >= --since, and prints the room.estimate after
1, 2, ... N positions, exactly as `live` would have. Use it after changing thresholds or
the floor plan: the recordings never change.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import soundfile as sf

from shared.config import DATA_DIR, ROOT, load_config
from services.acoustics import features as F
from services.acoustics.live import build_estimate, print_estimate
from services.acoustics.match import DEFAULT_MATCHING, PositionMeasurement
from services.acoustics.rooms import load_rooms
from services.acoustics.sweep import ir_from_recordings, make_sweep

_DIR = re.compile(r"^(P\d+)_(\d{8}-\d{6})$")


def latest_per_position(room: str, since: Optional[str] = None) -> List[Path]:
    base = DATA_DIR / "echo" / room
    best: Dict[str, Path] = {}
    for d in sorted(base.iterdir()):          # name order = time order within a label
        m = _DIR.match(d.name)
        if not m or not (d / "measurement.json").exists():
            continue
        label, stamp = m.groups()
        if since and stamp < since:
            continue
        best[label] = d
    return [best[k] for k in sorted(best, key=lambda s: int(s[1:]))]


def analyse_dir(d: Path, ecfg: Dict[str, Any], mic_height: Optional[float]) -> Tuple[F.IRFeatures, float]:
    meta = json.loads((d / "measurement.json").read_text())
    fs, s = meta["fs"], meta["sweep"]
    sweep = make_sweep(fs, s["f1"], s["f2"], s["duration_s"])
    recs = [sf.read(p)[0] for p in sorted(d.glob("rec_*.wav"))]
    ir = ir_from_recordings(recs, sweep, length_s=ecfg["ir_length_s"])
    feats = F.extract(ir, fs, c=ecfg["speed_of_sound_mps"], speaker_mic_m=ecfg["speaker_mic_m"],
                      max_distance_m=ecfg["max_reflection_distance_m"])
    h = mic_height if mic_height is not None else meta.get("mic_height_m", ecfg["mic_height_m"])
    return feats, float(h)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--room", required=True, help="folder name under data/echo/ (the --room label you recorded with)")
    ap.add_argument("--floor", help="floor id to match against (0=G..3); default: all floors")
    ap.add_argument("--since", help="only recordings with timestamp >= this prefix, e.g. 20261107-22")
    ap.add_argument("--mic-height", type=float, help="override the mic height saved with each recording")
    ap.add_argument("--final-only", action="store_true", help="print only the estimate after the last position")
    a = ap.parse_args(argv)

    ecfg = load_config()["echolocation"]
    matching = {**DEFAULT_MATCHING, **ecfg.get("matching", {})}
    rooms = load_rooms(ROOT / ecfg["rooms_file"])
    dirs = latest_per_position(a.room, a.since)
    if not dirs:
        sys.exit(f"no recordings found in data/echo/{a.room}/")
    positions: List[PositionMeasurement] = []
    for i, d in enumerate(dirs, 1):
        feats, h = analyse_dir(d, ecfg, a.mic_height)
        print(f"{d.name}: RT60 {feats.rt60_s} s ({feats.rt60_method}), mic height {h} m, reflections (m): "
              + (", ".join(f"{r.distance_m:.2f}" for r in feats.reflections) or "none"))
        positions.append(PositionMeasurement(d.name, feats.rt60_s, [r.distance_m for r in feats.reflections], h,
                                             d.name.split("_")[0], [r.strength_db for r in feats.reflections]))
        if not a.final_only or i == len(dirs):
            print_estimate(build_estimate(positions, a.floor, "manual", matching, rooms))


if __name__ == "__main__":
    main()
