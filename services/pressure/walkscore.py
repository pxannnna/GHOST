"""Score a logged floor walk: how often the detector's floor matched the floor you said you were on.

    python -m services.pressure.walkscore                       # the newest walk in data/pressure/walks/
    python -m services.pressure.walkscore data/pressure/walks/walk_20261108-101500.csv

`services.pressure.live` writes one row per reading. You tell it where you really are by typing t0, t1, t2 or t3
(true floor) once you are standing still on that floor. Only rows labelled with a true floor and judged `settled`
are scored; rows while you were walking (`transition`) or unsure are counted separately.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from shared.config import DATA_DIR

COLUMNS = ["unix_time", "board_time_s", "pressure_hpa", "estimated_floor", "status", "height_m", "true_floor"]


def summarize(path: Path) -> Dict[str, Any]:
    per: Dict[str, Dict[str, int]] = {}
    rows = labelled = 0
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows += 1
            t = r["true_floor"]
            if not t:
                continue
            labelled += 1
            d = per.setdefault(t, {"n": 0, "settled": 0, "correct": 0, "transition": 0, "other": 0})
            d["n"] += 1
            if r["status"] == "settled":
                d["settled"] += 1
                d["correct"] += int(r["estimated_floor"] == t)
            elif r["status"] == "transition":
                d["transition"] += 1
            else:
                d["other"] += 1
    return {"rows": rows, "labelled": labelled, "floors": per}


def format_summary(s: Dict[str, Any]) -> str:
    if not s["labelled"]:
        return f"{s['rows']} readings logged, but none labelled: type t0, t1, t2 or t3 when standing on a floor."
    lines = [f"{s['rows']} readings logged, {s['labelled']} labelled with a true floor",
             "true floor | readings | settled | detector right | in transition / unsure"]
    tot_s = tot_c = 0
    for t in sorted(s["floors"]):
        d = s["floors"][t]
        acc = f"{d['correct']}/{d['settled']} ({100 * d['correct'] / d['settled']:.0f}%)" if d["settled"] else "-"
        lines.append(f"     {t}     | {d['n']:8d} | {d['settled']:7d} | {acc:>14} | {d['transition']} / {d['other']}")
        tot_s += d["settled"]
        tot_c += d["correct"]
    if tot_s:
        lines.append(f"overall: {tot_c}/{tot_s} settled readings had the right floor ({100 * tot_c / tot_s:.0f}%)")
    return "\n".join(lines)


def newest(folder: Optional[Path] = None) -> Optional[Path]:
    walks = sorted((folder or DATA_DIR / "pressure" / "walks").glob("walk_*.csv"))
    return walks[-1] if walks else None


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else newest()
    if path is None or not path.exists():
        sys.exit("no walk logs found in data/pressure/walks/")
    print(path)
    print(format_summary(summarize(path)))


if __name__ == "__main__":
    main()
