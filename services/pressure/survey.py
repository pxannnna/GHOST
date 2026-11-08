"""Re-survey the floors with the barometer board, so the floor detector uses THIS sensor's readings.

    python -m services.pressure.survey                 # G, 1, 2, 3, 2, 1, G; 20 s each; writes config/local.json
    python -m services.pressure.survey --seconds 30 --dry-run

Carry the laptop with the board plugged in. At each prompt stand still where the device will be during the demo and
press Enter. Going up and back down means slow weather drift averages out (it moves every floor's reading the same
way on the way up and the way down). Only the DIFFERENCES between floors are used by the detector; the absolute value
does not matter. The result goes into config/local.json (git-ignored), overriding the committed survey.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.config import CONFIG_DIR, load_config


def visit_order(floor_ids: List[str], round_trip: bool = True) -> List[str]:
    return list(floor_ids) + (list(floor_ids[-2::-1]) if round_trip else [])


def combine_visits(visits: Dict[str, List[float]]) -> Dict[str, float]:
    """Mean of the per-visit medians for each floor (hPa)."""
    return {f: round(statistics.mean(v), 3) for f, v in visits.items()}


def write_survey(local_path: Path, readings_hpa: Dict[str, float], reference_floor: str, note: str) -> Dict[str, Any]:
    """Merge the new survey into config/local.json, keeping everything else in it."""
    cfg: Dict[str, Any] = json.loads(local_path.read_text()) if local_path.exists() else {}
    survey = cfg.setdefault("pressure", {}).setdefault("survey", {})
    survey.update({"_comment": note, "reference_floor": reference_floor, "readings_hpa": readings_hpa})
    local_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return cfg


def collect(client, seconds: float) -> List[float]:
    """Fresh readings for `seconds`. Anything buffered while we waited at the prompt is discarded first,
    otherwise the first seconds on a new floor would still be the previous floor's pressure."""
    client.flush(settle_s=0.5)
    vals, t_end = [], time.time() + seconds
    while time.time() < t_end:
        r = client.read(timeout=2.0)
        if r is not None:
            vals.append(r[1])
    return vals


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=20.0, help="how long to record on each floor")
    ap.add_argument("--no-round-trip", action="store_true", help="only go up (weather drift will not cancel)")
    ap.add_argument("--serial", help="serial port of the board (default: found automatically)")
    ap.add_argument("--dry-run", action="store_true", help="show the result but do not write config/local.json")
    a = ap.parse_args(argv)

    from services.pressure import board
    cfg = load_config()
    pcfg, floors = cfg["pressure"], [f["id"] for f in cfg["building"]["floors"]]
    port = a.serial or pcfg.get("serial_port")
    if not board.find_port(port):
        raise SystemExit("no barometer board found: plug it in and check `ls /dev/cu.*`")
    client = board.BoardClient(port, pcfg.get("board_rate_hz", 5.0)).connect()
    print(f"board on {client.port}")
    labels = {f["id"]: f["label"] for f in cfg["building"]["floors"]}
    visits: Dict[str, List[float]] = {}
    order = visit_order(floors, not a.no_round_trip)
    for i, fid in enumerate(order, 1):
        input(f"\n[{i}/{len(order)}] Go to floor {fid} ({labels[fid]}), stand still, press Enter > ")
        vals = collect(client, a.seconds)
        if not vals:
            raise SystemExit("no readings from the board: is it still plugged in?")
        med, spread = statistics.median(vals), (max(vals) - min(vals)) * 100
        print(f"   {len(vals)} readings, median {med:.3f} hPa, spread {spread:.1f} Pa"
              + ("   <- large spread: were you moving? repeat this survey" if spread > 6 else ""))
        visits.setdefault(fid, []).append(med)
    client.close()
    readings = combine_visits(visits)
    ref = pcfg["survey"]["reference_floor"]
    old = pcfg["survey"]["readings_hpa"]
    print("\nfloor | new hPa | step from the floor below (Pa) | old survey step (Pa)")
    prev = None
    for fid in floors:
        step = "" if prev is None else f"{(readings[prev] - readings[fid]) * 100:6.1f}"
        old_step = "" if prev is None else f"{(old[prev] - old[fid]) * 100:6.1f}"
        print(f"  {fid}   | {readings[fid]:.3f} | {step:>30} | {old_step:>20}")
        prev = fid
    if a.dry_run:
        print("\n--dry-run: nothing written")
        return
    note = f"Surveyed with the barometer board on {time.strftime('%Y-%m-%d %H:%M')} ({a.seconds:.0f} s per floor)."
    write_survey(CONFIG_DIR / "local.json", readings, ref, note)
    print("\nwritten to config/local.json (git-ignored)")


if __name__ == "__main__":
    main()
