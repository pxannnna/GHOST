"""Shoebox image-source room simulator (Allen & Berkley 1979), numpy only.

Used for tests and for `--simulate` runs, which are always labelled mode
"simulated". Never present its output as measured.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from services.acoustics.sweep import Sweep


def shoebox_ir(dims: Sequence[float], src: Sequence[float], mic: Sequence[float], absorption: float,
               fs: int = 48000, length_s: float = 1.5, c: float = 343.0,
               max_images_time_s: Optional[float] = None) -> np.ndarray:
    """Impulse response of a rectangular room with uniform absorption."""
    L = np.asarray(dims, float)
    s = np.asarray(src, float)
    m = np.asarray(mic, float)
    beta = np.sqrt(1.0 - absorption)
    tmax = max_images_time_s or length_s
    rmax = tmax * c
    h = np.zeros(int(length_s * fs))
    N = [int(np.ceil(rmax / (2 * l))) + 1 for l in L]
    ax = []
    for k in range(3):
        n = np.arange(-N[k], N[k] + 1)
        parts = []
        for q in (0, 1):
            pos = (1 - 2 * q) * s[k] + 2 * n * L[k]
            refl = np.abs(n - q) + np.abs(n)
            parts.append((pos - m[k], refl))
        d = np.concatenate([p[0] for p in parts])
        r = np.concatenate([p[1] for p in parts])
        ax.append((d, r))
    dx, rx = ax[0]
    dy, ry = ax[1]
    dz, rz = ax[2]
    # Loop over x to bound memory; vectorise y,z.
    DY, DZ = np.meshgrid(dy, dz, indexing="ij")
    RY, RZ = np.meshgrid(ry, rz, indexing="ij")
    dyz2 = (DY ** 2 + DZ ** 2).ravel()
    ryz = (RY + RZ).ravel()
    for xi in range(len(dx)):
        dist = np.sqrt(dx[xi] ** 2 + dyz2)
        ok = dist < rmax
        if not ok.any():
            continue
        dist = np.maximum(dist[ok], 0.05)
        amp = beta ** (rx[xi] + ryz[ok]) / dist
        idx = np.round(dist / c * fs).astype(int)
        keep = idx < len(h)
        np.add.at(h, idx[keep], amp[keep])
    return h


def hybrid_ir(dims: Sequence[float], src: Sequence[float], mic: Sequence[float], absorption: float,
              fs: int = 48000, length_s: float = 2.5, c: float = 343.0, early_s: float = 0.08,
              seed: Optional[int] = None) -> np.ndarray:
    """Image-source early reflections + a diffuse exponential tail at the Eyring RT60.

    A pure specular shoebox decays too slowly (floor-ceiling flutter never
    scatters); real rooms scatter. This is the usual hybrid model."""
    rng = np.random.default_rng(seed)
    early = shoebox_ir(dims, src, mic, absorption, fs, length_s=early_s + 0.01, c=c)
    L = np.asarray(dims, float)
    V = float(np.prod(L))
    S = 2 * (L[0] * L[1] + L[0] * L[2] + L[1] * L[2])
    rt = -0.161 * V / (S * np.log(1 - absorption))
    n = int(length_s * fs)
    h = np.zeros(n)
    ne = int(early_s * fs)
    h[:ne] = early[:ne]
    t = np.arange(n - ne) / fs
    # Match the tail's starting energy to the early part's last 20 ms.
    ref = early[ne - int(0.02 * fs): ne]
    lvl = np.sqrt(np.mean(ref ** 2)) if ref.size else 1e-3
    h[ne:] = rng.normal(0, lvl, n - ne) * 10 ** (-3 * t / rt)
    return h


def simulate_recording(ir: np.ndarray, sweep: Sweep, latency_s: float = 0.03, noise_rms: float = 1e-4,
                       tail_s: float = 2.0, seed: Optional[int] = None) -> np.ndarray:
    """What the mic would capture: latency + sweep*IR + background noise."""
    from scipy.signal import fftconvolve
    rng = np.random.default_rng(seed)
    y = fftconvolve(sweep.signal.astype(float), ir)
    n = int(latency_s * sweep.fs) + len(sweep.signal) + int(tail_s * sweep.fs)
    out = np.zeros(n)
    a = int(latency_s * sweep.fs)
    seg = y[: n - a]
    out[a: a + len(seg)] = seg
    out /= max(np.max(np.abs(out)), 1e-12) * 2.0
    return out + rng.normal(0, noise_rms, n)
