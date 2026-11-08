"""Exponential sine sweep (Farina 2000) -> room impulse response.

The DJI Mic Mini is wireless and on a different clock/device from the Mac
speaker, so the playback->capture latency is unknown and changes between runs.
We therefore never trust absolute time: time zero is the *direct sound* peak
in the impulse response (mic a few cm from the speaker), and every distance is
measured relative to it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import numpy as np
from scipy.signal import fftconvolve


@dataclass(frozen=True)
class Sweep:
    fs: int
    f1: float
    f2: float
    duration_s: float
    signal: np.ndarray      # float32, peak 1.0 (scale at playback)
    inverse: np.ndarray     # inverse filter, normalised so sweep * inverse peaks at 1


def make_sweep(fs: int = 48000, f1: float = 200.0, f2: float = 20000.0,
               duration_s: float = 3.0, fade_s: float = 0.02) -> Sweep:
    n = int(round(duration_s * fs))
    t = np.arange(n) / fs
    R = np.log(f2 / f1)
    x = np.sin(2 * np.pi * f1 * duration_s / R * (np.exp(t * R / duration_s) - 1.0))
    nf = int(fade_s * fs)
    if nf > 0:
        w = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, nf))
        x[:nf] *= w
        x[-nf:] *= w[::-1]
    # Inverse filter: time-reversed sweep with a -6 dB/octave envelope so the
    # combined magnitude response is flat.
    inv = x[::-1] * np.exp(-t * R / duration_s)
    peak = np.max(np.abs(fftconvolve(x, inv)))
    inv = inv / peak
    return Sweep(fs, f1, f2, duration_s, x.astype(np.float32), inv.astype(np.float64))


def deconvolve(recording: np.ndarray, sweep: Sweep) -> np.ndarray:
    """Full linear deconvolution. The linear IR starts at index len(sweep)-1 + latency;
    harmonic-distortion products land *before* it and are discarded by `trim_ir`."""
    y = np.asarray(recording, float)
    if y.ndim > 1:
        y = y.mean(axis=1)
    return fftconvolve(y, sweep.inverse)


def find_direct(ir: np.ndarray, start: int = 0) -> int:
    """Index of the direct-sound peak (largest |h| at or after `start`)."""
    return int(start + np.argmax(np.abs(ir[start:])))


def trim_ir(ir_full: np.ndarray, sweep: Sweep, pre_s: float = 0.005, length_s: float = 2.5) -> np.ndarray:
    """Cut the causal IR so the direct peak sits at `pre_s` seconds."""
    fs = sweep.fs
    # Linear part starts where the sweep and inverse fully overlap.
    start = len(sweep.signal) - 1 - int(0.05 * fs)  # allow small negative latency jitter
    d = find_direct(ir_full, max(start, 0))
    a = max(d - int(pre_s * fs), 0)
    b = min(d + int(length_s * fs), len(ir_full))
    out = np.zeros(int(pre_s * fs) + int(length_s * fs))
    seg = ir_full[a:b]
    out[: len(seg)] = seg
    return out


def average_aligned(irs: Sequence[np.ndarray]) -> np.ndarray:
    """Average repeat IRs after aligning their direct peaks (they're already
    trimmed so this only corrects small residual offsets)."""
    if len(irs) == 1:
        return np.asarray(irs[0], float)
    ref = int(np.argmax(np.abs(irs[0])))
    acc: List[np.ndarray] = []
    for h in irs:
        k = int(np.argmax(np.abs(h)))
        acc.append(np.roll(h, ref - k))
    # Polarity can flip between devices/runs: match sign of the direct peak.
    signs = [np.sign(a[ref]) or 1.0 for a in acc]
    return np.mean([a * s * signs[0] for a, s in zip(acc, signs)], axis=0)


def ir_from_recordings(recordings: Sequence[np.ndarray], sweep: Sweep,
                       pre_s: float = 0.005, length_s: float = 2.5) -> np.ndarray:
    return average_aligned([trim_ir(deconvolve(r, sweep), sweep, pre_s, length_s) for r in recordings])
