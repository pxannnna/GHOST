"""Phone barometer -> floor, streamed to the hub.

    make pressure-live                                  # the USB barometer board (pressure.source "board")
    python -m services.pressure.live --source phyphox   # the phone instead (pressure.phone_url)
    python -m services.pressure.live --zero-floor 0     # zero on G as soon as readings settle
    python -m services.pressure.live --csv walk.csv     # replay a phyphox CSV export (mode=replay)

While running, type a command + Enter:
    z      zero here, on the reference floor (G)
    z2     zero here, on floor 2
    t2     "I am standing on floor 2 now": logs the true floor so the detector can be scored (type t0..t3
           once you are standing still; the log is data/pressure/walks/walk_<time>.csv)
    q      quit (prints how often the detector had the right floor)
The calibration is saved to data/pressure/calibration.json and reloaded on
restart (its age is printed: re-zero if it's more than ~1 hour old).
"""
from __future__ import annotations

import argparse
import csv
import json
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from shared.config import DATA_DIR, ROOT, load_config
from services.pressure import walkscore
from services.pressure.floor import FloorEstimator, FloorState
from services.pressure.phyphox import PhyphoxClient, read_csv

CAL_FILE = DATA_DIR / "pressure" / "calibration.json"


def save_cal(est: FloorEstimator) -> None:
    CAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    CAL_FILE.write_text(json.dumps({"p_ref_pa": est.p_ref_pa, "calibration_id": est.calibration_id,
                                    "calibrated_at": est.calibrated_at}))


def load_cal(est: FloorEstimator) -> None:
    if CAL_FILE.exists():
        c = json.loads(CAL_FILE.read_text())
        est.set_reference(c["p_ref_pa"], c["calibration_id"], c["calibrated_at"])
        age_min = (time.time() - c["calibrated_at"]) / 60
        print(f"loaded calibration {c['calibration_id']} ({age_min:.0f} min old"
              + (" - consider re-zeroing: weather drift" if age_min > 60 else "") + ")")


def stdin_commands() -> "queue.Queue[str]":
    q: "queue.Queue[str]" = queue.Queue()

    def run() -> None:
        for line in sys.stdin:
            q.put(line.strip().lower())
    threading.Thread(target=run, daemon=True).start()
    return q


def phyphox_samples(url: str, poll_hz: float, client_status) -> Iterator[Tuple[float, float, float]]:
    """Yields (laptop_unix_time, phone_time_s, pressure_hPa)."""
    ph = PhyphoxClient(url)
    started = False
    while True:
        try:
            if not started:
                ph.start()
                started = True
            samples, measuring = ph.read_new()
            if not measuring:
                ph.start()
            now = time.time()
            for t, p in samples:
                yield now, t, p
        except Exception as e:  # phone asleep / Wi-Fi hiccup: keep trying
            client_status("offline", f"phyphox: {e.__class__.__name__}: {e}")
            started = False
            time.sleep(1.0)
        time.sleep(1.0 / poll_hz)


def csv_samples(path: Path, speed: float) -> Iterator[Tuple[float, float, float]]:
    t0_wall, t0 = time.time(), None
    for t, p in read_csv(path):
        t0 = t if t0 is None else t0
        if speed > 0:
            time.sleep(max(0.0, (t - t0) / speed - (time.time() - t0_wall)))
        yield (t0_wall + (t - t0) / speed) if speed > 0 else t, t, p


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["board", "phyphox"], help="pressure source (default: config pressure.source)")
    ap.add_argument("--serial", help="serial port of the board (default: found automatically)")
    ap.add_argument("--url", help="phyphox URL (default config pressure.phone_url)")
    ap.add_argument("--csv", type=Path, help="replay a phyphox CSV export instead (mode=replay)")
    ap.add_argument("--speed", type=float, default=1.0, help="CSV replay speed (0 = as fast as possible)")
    ap.add_argument("--zero-floor", help="zero on this floor once the first readings settle")
    ap.add_argument("--fresh", action="store_true", help="ignore the saved calibration")
    ap.add_argument("--no-emit", action="store_true")
    a = ap.parse_args(argv)

    cfg = load_config()["pressure"]
    est = FloorEstimator(cfg["survey"], cfg["pa_per_m"], cfg["dwell_s"], cfg["hysteresis_m"])
    if not a.fresh and a.zero_floor is None and not a.csv:
        load_cal(est)

    mode = "replay" if a.csv else "live"
    client = None
    if not a.no_emit:
        from shared.client import EventClient
        client = EventClient("pressure", mode=mode)

    def status(state: str, detail: str = "") -> None:
        if client:
            client.status("barometer", state, detail)
        if state != "ok":
            print(f"[{state}] {detail}")

    source = "board" if a.serial else (a.source or ("phyphox" if a.url else cfg.get("source", "board")))
    if a.csv:
        samples = csv_samples(a.csv, a.speed)
    elif source == "board":
        from services.pressure import board
        port = a.serial or cfg.get("serial_port")
        if not board.find_port(port):
            sys.exit("no barometer board found: plug it in (check `ls /dev/cu.*`), or use --source phyphox")
        samples = board.samples(port, cfg.get("board_rate_hz", 5.0), status)
    else:
        url = a.url or cfg.get("phone_url")
        if not url:
            sys.exit("set pressure.phone_url in config/local.json or pass --url http://<phone-ip>:8080")
        samples = phyphox_samples(url, cfg["poll_hz"], status)

    cmds = stdin_commands() if sys.stdin.isatty() else queue.Queue()
    pending_zero = a.zero_floor
    status("calibrating" if est.p_ref_pa is None else "ok", "waiting for zero" if est.p_ref_pa is None else "")
    last_emit_sample, last_floor_emit, last_key = 0.0, 0.0, None
    min_dt = 1.0 / cfg["poll_hz"]

    log_path = log_file = log_writer = None
    true_floor = ""
    if not a.csv:
        log_path = DATA_DIR / "pressure" / "walks" / f"walk_{time.strftime('%Y%m%d-%H%M%S')}.csv"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "w", newline="")
        log_writer = csv.writer(log_file)
        log_writer.writerow(walkscore.COLUMNS)
        print(f"logging to {log_path.relative_to(ROOT)}  (type t0, t1, t2 or t3 when you stand still on a floor)")

    def finish() -> None:
        if log_file:
            log_file.close()
            print("\n" + walkscore.format_summary(walkscore.summarize(log_path)))
        if client:
            client.close()

    for now, t_phone, hpa in samples:
        pa = hpa * 100.0
        # Estimator runs on the phone's clock (correct speeds even in fast replay);
        # wall-clock `now` is only used to pace the events we send.
        st: FloorState = est.update(t_phone, pa)

        while not cmds.empty():
            c = cmds.get()
            if c == "q":
                finish()
                return
            if c.startswith("z"):
                f = c[1:].strip() or est.reference_floor
                print("zeroed:", est.zero_from_window(f))
                save_cal(est)
                status("ok", f"zeroed on floor {f}")
                true_floor = f
            if c.startswith("t") and c[1:].strip().isdigit():
                true_floor = c[1:].strip()
                print(f"true floor set to {true_floor}")
        if pending_zero is not None and len(est.window) >= 3 and \
                est.window[-1][0] - est.window[0][0] >= 0.8 * est.dwell_s:
            print("zeroed:", est.zero_from_window(pending_zero))
            if not a.csv:
                save_cal(est)
            status("ok", f"zeroed on floor {pending_zero}")
            true_floor = pending_zero
            pending_zero = None
            st = est.update(t_phone, pa)
        if log_writer:
            log_writer.writerow([round(now, 3), round(t_phone, 3), round(hpa, 4), st.floor_id or "", st.status,
                                 "" if st.relative_height_m is None else round(st.relative_height_m, 2), true_floor])
            log_file.flush()

        if client and now - last_emit_sample >= min_dt:
            client.emit("pressure.sample", {"pressure_pa": round(pa, 2), "sensor_timestamp": t_phone,
                                            "relative_height_m": None if st.relative_height_m is None
                                            else round(st.relative_height_m, 2)})
            last_emit_sample = now
        key = (st.floor_id, st.status)
        if key != last_key or now - last_floor_emit >= 1.0:
            payload = {"floor_id": st.floor_id, "reference_floor": est.reference_floor,
                       "calibration_id": st.calibration_id, "status": st.status,
                       "relative_height_m": None if st.relative_height_m is None else round(st.relative_height_m, 2),
                       "distance_to_floor_m": None if st.distance_to_floor_m is None else round(st.distance_to_floor_m, 2)}
            if client:
                client.emit("floor.estimate", payload)
            if key != last_key:
                h = "-" if st.relative_height_m is None else f"{st.relative_height_m:+.2f} m"
                print(f"{time.strftime('%H:%M:%S')}  floor {st.floor_id}  [{st.status}]  height {h}  "
                      f"({hpa:.3f} hPa)")
            last_key, last_floor_emit = key, now
    finish()


if __name__ == "__main__":
    main()
