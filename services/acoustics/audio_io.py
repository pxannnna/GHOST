"""Play the sweep on the Mac speakers and record it on the DJI Mic Mini.

Devices are picked by name substring from config (echolocation.input_device /
output_device), so it keeps working when device indices change.
Before measuring: on the DJI turn OFF noise cancelling and low-cut; on the
Mac set Mic Mode to Standard and output volume to a fixed level.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np


def _sd():
    import sounddevice as sd  # imported lazily so tests/analysis run without audio
    return sd


def find_device(name: Optional[str], kind: str) -> Optional[int]:
    """kind: 'input' or 'output'. None -> system default."""
    if not name:
        return None
    sd = _sd()
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    matches = [i for i, d in enumerate(sd.query_devices())
               if name.lower() in d["name"].lower() and d[key] > 0]
    if not matches:
        names = [d["name"] for d in sd.query_devices() if d[key] > 0]
        raise RuntimeError(f"no {kind} device matching {name!r}; available: {names}")
    return matches[0]


def list_devices() -> str:
    return str(_sd().query_devices())


def mic_check(input_device: Optional[str], fs: int = 48000, seconds: float = 2.0) -> dict:
    """Record a few seconds of room sound (nothing is played or saved) and report the level.
    Exact digital silence almost always means macOS has not granted microphone access."""
    sd = _sd()
    i_dev = find_device(input_device, "input")
    rec = sd.rec(int(seconds * fs), samplerate=fs, channels=1, device=i_dev, dtype="float32")
    sd.wait()
    y = rec[:, 0].astype(np.float64)
    rms = float(np.sqrt(np.mean(y ** 2)))
    name = sd.query_devices(i_dev if i_dev is not None else sd.default.device[0])["name"]
    return {"device": name, "rms_dbfs": round(20 * np.log10(max(rms, 1e-12)), 1),
            "peak": round(float(np.max(np.abs(y))), 4), "silent": rms < 1e-7}


def play_and_record(signal: np.ndarray, fs: int, input_device: Optional[str], output_device: Optional[str],
                    gain: float = 0.5, pre_s: float = 0.3, tail_s: float = 3.0) -> Tuple[np.ndarray, dict]:
    """Returns (mono recording float64, info). Latency is NOT compensated here:
    the deconvolution aligns on the direct sound instead."""
    sd = _sd()
    i_dev, o_dev = find_device(input_device, "input"), find_device(output_device, "output")
    out = np.concatenate([np.zeros(int(pre_s * fs)), signal * gain, np.zeros(int(tail_s * fs))]).astype(np.float32)
    o_ch = min(2, sd.query_devices(o_dev if o_dev is not None else sd.default.device[1])["max_output_channels"])
    out2 = np.repeat(out[:, None], o_ch, axis=1)
    try:
        rec = sd.playrec(out2, samplerate=fs, channels=1, device=(i_dev, o_dev), dtype="float32")
        sd.wait()
        how = "duplex"
    except Exception:  # some USB/wireless receivers refuse a shared duplex stream
        rec = sd.rec(len(out2), samplerate=fs, channels=1, device=i_dev, dtype="float32")
        sd.play(out2, samplerate=fs, device=o_dev)
        sd.wait()
        how = "separate-streams"
    y = rec[:, 0].astype(np.float64)
    peak = float(np.max(np.abs(y)))
    info = {"stream": how, "peak": round(peak, 4), "clipped": peak >= 0.99,
            "too_quiet": peak < 0.01, "input_device": input_device, "output_device": output_device}
    return y, info
