"""One echolocation measurement at one position.

    make echo-measure ROOM=nuc-2-rowan POS=P1
    python -m services.acoustics.measure --room nuc-2-rowan --position P1 [--mic-height 0.75]
    python -m services.acoustics.measure --simulate nuc-2-rowan --position P1   # mode=simulated
    python -m services.acoustics.measure --list-devices
    python -m services.acoustics.measure --mic-check   # 2 s of room sound, nothing played or saved

Plays the sweep `repeats` times, records on the DJI mic, builds the averaged
impulse response, extracts RT60 + reflections, saves everything under
data/echo/<room>/<position>_<time>/ and sends `acoustic.measurement` to the hub.
`--room` is only a label for the saved data (ground truth for validation);
the matcher never sees it.

Protocol: laptop on a table, DJI clipped ~10 cm from the speaker grille, both
>= 1 m from any wall, nobody moving within 1 m. 3-4 positions spread across
the room. Same volume every time.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from shared.config import DATA_DIR, ROOT, load_config
from services.acoustics import features as F
from services.acoustics.sweep import Sweep, ir_from_recordings, make_sweep


@dataclass
class MeasurementResult:
    measurement_id: str
    position_label: str
    features: F.IRFeatures
    ir: np.ndarray
    fs: int
    mic_height_m: float
    mode: str
    info: Dict[str, Any]
    out_dir: Optional[Path] = None

    def payload(self) -> Dict[str, Any]:
        f = self.features
        return {
            "measurement_id": self.measurement_id,
            "position_label": self.position_label,
            "rt60_s": f.rt60_s,
            "reflection_distances_m": [r.distance_m for r in f.reflections],
            "snr_db": f.snr_db,
            "impulse_response_preview": F.ir_preview(self.ir, self.fs),
            # extra diagnostics (schema allows extra fields)
            "rt60_bands_s": f.rt60_bands_s,
            "rt60_method": f.rt60_method,
            "edt_s": f.edt_s,
            "decay_range_db": f.decay_range_db,
            "reflections": [r.__dict__ for r in f.reflections],
            "mic_height_m": self.mic_height_m,
            "warnings": [k for k in ("clipped", "too_quiet") if self.info.get(k)],
        }


def echo_cfg() -> Dict[str, Any]:
    return load_config()["echolocation"]


def sweep_from_cfg(cfg: Dict[str, Any]) -> Sweep:
    s = cfg["sweep"]
    return make_sweep(cfg["samplerate"], s["f_start_hz"], s["f_end_hz"], s["duration_s"])


def _simulated_recordings(room_id: str, sweep: Sweep, cfg: Dict[str, Any], repeats: int,
                          mic_height: float, seed: Optional[int]):
    """Shoebox approximation of a room from rooms.json (bbox x ceiling).
    Returns (recordings, truth): `truth` is the geometry the simulation used, saved with the
    recording so plots can show where the surfaces really are."""
    from services.acoustics.match import DEFAULT_MATCHING, absorption_for
    from services.acoustics.rooms import load_rooms
    from services.acoustics.simulate import field_ir, simulate_recording
    room = next(r for r in load_rooms(ROOT / cfg["rooms_file"]) if r.room_id == room_id)
    L, W = room.bbox_dims()
    H = room.ceiling_height_m
    rng = np.random.default_rng(seed)
    src = (rng.uniform(1.2, L - 1.2), rng.uniform(1.2, W - 1.2), mic_height)
    mic = (src[0] + cfg["speaker_mic_m"], src[1], src[2])
    a = absorption_for(room, {**DEFAULT_MATCHING, **cfg.get("matching", {})})
    ir = field_ir((L, W, H), src, mic, a, sweep.fs, length_s=cfg["ir_length_s"], seed=seed)
    recs = [simulate_recording(ir, sweep, latency_s=0.02 + 0.007 * k, noise_rms=2e-3,
                               tail_s=cfg["sweep"]["silence_after_s"], seed=None if seed is None else seed + k)
            for k in range(repeats)]
    truth = {"simulated": True, "room_id": room_id, "room_dims_m": [round(L, 2), round(W, 2), round(H, 2)],
             "source_xyz_m": [round(float(v), 2) for v in src],
             "surfaces_one_way_m": {"wall": [round(float(src[0]), 2), round(float(L - src[0]), 2),
                                             round(float(src[1]), 2), round(float(W - src[1]), 2)],
                                    "floor": round(float(src[2]), 2), "ceiling": round(float(H - src[2]), 2)}}
    return recs, truth


def measure_position(position: str, room_tag: Optional[str] = None, repeats: Optional[int] = None,
                     mic_height: Optional[float] = None, simulate: Optional[str] = None,
                     save: bool = True, seed: Optional[int] = None,
                     cfg: Optional[Dict[str, Any]] = None) -> MeasurementResult:
    cfg = cfg or echo_cfg()
    sweep = sweep_from_cfg(cfg)
    repeats = repeats or cfg["sweep"]["repeats"]
    mic_height = cfg["mic_height_m"] if mic_height is None else mic_height
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tag = room_tag or (f"sim-{simulate}" if simulate else "unlabelled")
    mid = f"{tag}/{position}/{stamp}"
    recs: List[np.ndarray] = []
    info: Dict[str, Any] = {}
    if simulate:
        recs, truth = _simulated_recordings(simulate, sweep, cfg, repeats, mic_height, seed)
        info = {"sim_truth": truth}
        mode = "simulated"
    else:
        from services.acoustics.audio_io import play_and_record
        for k in range(repeats):
            y, info = play_and_record(sweep.signal, sweep.fs, cfg["input_device"], cfg["output_device"],
                                      gain=cfg["output_gain"], tail_s=cfg["sweep"]["silence_after_s"])
            recs.append(y)
            print(f"  sweep {k + 1}/{repeats}: peak {info['peak']:.3f} ({info['stream']})"
                  + ("  CLIPPED - lower output_gain" if info["clipped"] else "")
                  + ("  TOO QUIET - raise volume / move mic closer" if info["too_quiet"] else ""))
            time.sleep(0.3)
        mode = "live"
    ir = ir_from_recordings(recs, sweep, length_s=cfg["ir_length_s"])
    feats = F.extract(ir, sweep.fs, c=cfg["speed_of_sound_mps"], speaker_mic_m=cfg["speaker_mic_m"],
                      max_distance_m=cfg["max_reflection_distance_m"])
    res = MeasurementResult(mid, position, feats, ir, sweep.fs, mic_height, mode, info)
    if save:
        res.out_dir = _save(res, recs, sweep, tag, position, stamp)
    return res


def _save(res: MeasurementResult, recs: List[np.ndarray], sweep: Sweep, tag: str, position: str, stamp: str) -> Path:
    import soundfile as sf
    d = DATA_DIR / "echo" / tag / f"{position}_{stamp}"
    d.mkdir(parents=True, exist_ok=True)
    for k, y in enumerate(recs):
        sf.write(d / f"rec_{k}.wav", y.astype(np.float32), sweep.fs, subtype="FLOAT")
    sf.write(d / "ir.wav", (res.ir / max(np.max(np.abs(res.ir)), 1e-12)).astype(np.float32), sweep.fs, subtype="FLOAT")
    meta = {"measurement_id": res.measurement_id, "room_tag": tag, "position": position, "mode": res.mode,
            "mic_height_m": res.mic_height_m, "fs": sweep.fs,
            "sweep": {"f1": sweep.f1, "f2": sweep.f2, "duration_s": sweep.duration_s},
            "info": res.info, "features": res.features.to_dict()}
    (d / "measurement.json").write_text(json.dumps(meta, indent=1, default=float))
    return d


def print_result(res: MeasurementResult) -> None:
    f = res.features
    print(f"RT60 {f.rt60_s} s ({f.rt60_method}; bands {f.rt60_bands_s})  SNR {f.snr_db} dB  "
          f"decay range {f.decay_range_db} dB")
    print("reflections (m):", ", ".join(f"{r.distance_m:.2f} [{r.strength_db:+.0f}dB]" for r in f.reflections) or "none")
    if res.out_dir:
        print("saved", res.out_dir.relative_to(ROOT))


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--room", help="room_id label for the saved data (ground truth)")
    ap.add_argument("--position", default="P1")
    ap.add_argument("--repeats", type=int)
    ap.add_argument("--mic-height", type=float, help="mic height above floor, m (default config mic_height_m)")
    ap.add_argument("--simulate", metavar="ROOM_ID", help="simulate this room instead of recording (mode=simulated)")
    ap.add_argument("--no-emit", action="store_true", help="don't send to the hub")
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--mic-check", action="store_true", help="record 2 s of room sound and report the level")
    a = ap.parse_args(argv)
    if a.mic_check:
        from services.acoustics.audio_io import mic_check
        cfg = echo_cfg()
        r = mic_check(cfg["input_device"], cfg["samplerate"])
        print(f"input: {r['device']}   level {r['rms_dbfs']} dBFS   peak {r['peak']}")
        if r["silent"]:
            print("SILENT: allow microphone access for your terminal/IDE in System Settings > "
                  "Privacy & Security > Microphone, then restart the terminal.")
        elif r["rms_dbfs"] > -30:
            print("Loud room (> -30 dBFS): echoes will be noisy; find a quieter moment or room.")
        else:
            print("OK: the mic is working.")
        return
    if a.list_devices:
        from services.acoustics.audio_io import list_devices
        print(list_devices())
        return
    res = measure_position(a.position, a.room, a.repeats, a.mic_height, a.simulate)
    print_result(res)
    if not a.no_emit:
        from shared.client import EventClient
        client = EventClient("acoustics", mode=res.mode)
        client.emit("acoustic.measurement", res.payload())
        client.close()


if __name__ == "__main__":
    main()
