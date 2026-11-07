"""Features from one room impulse response: RT60, early reflections, SNR.

All times are relative to the direct-sound peak (see sweep.py for why).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
from scipy.signal import butter, find_peaks, hilbert, sosfiltfilt


@dataclass
class Reflection:
    distance_m: float   # one-way distance to the reflecting surface (speaker+mic ~ co-located)
    delay_ms: float     # after the direct sound
    level_db: float     # relative to the direct sound
    strength_db: float = 0.0  # level corrected for 1/r spreading (0 dB ~ perfect reflector)


@dataclass
class IRFeatures:
    rt60_s: Optional[float]
    rt60_bands_s: Dict[str, Optional[float]]
    rt60_method: str                      # "T20", "T10" or "none"
    edt_s: Optional[float]
    snr_db: float
    decay_range_db: float
    reflections: List[Reflection] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


def _band(h: np.ndarray, fs: int, lo: float, hi: float) -> np.ndarray:
    sos = butter(4, [lo, min(hi, 0.45 * fs)], btype="band", fs=fs, output="sos")
    return sosfiltfilt(sos, h)


def _noise_energy(e: np.ndarray, tail_frac: float = 0.15) -> float:
    n = max(int(len(e) * tail_frac), 1)
    return float(np.mean(e[-n:]))


def schroeder_rt60(h: np.ndarray, fs: int, skip_direct_ms: float = 3.0
                   ) -> tuple[Optional[float], str, Optional[float], float]:
    """RT60 via Schroeder backward integration with noise compensation and
    truncation where the decay meets the noise floor (simplified Lundeby).

    The mic sits ~10 cm from the speaker, so the direct sound is far louder than
    the room's response and would dominate the decay curve. Integration therefore
    starts `skip_direct_ms` after the direct peak: we measure the room's decay only.
    Returns (rt60, method, edt, usable_decay_range_db)."""
    d = int(np.argmax(np.abs(h))) + int(skip_direct_ms * 1e-3 * fs)
    e = h[d:] ** 2
    noise = _noise_energy(e)
    blk = max(int(0.01 * fs), 1)
    nb = len(e) // blk
    if nb < 10:
        return None, "none", None, 0.0
    env = e[: nb * blk].reshape(nb, blk).mean(axis=1)
    peak = env.max()
    rng_db = 10 * np.log10(peak / max(noise, 1e-30))
    # Truncate where the smoothed envelope first falls to 5 dB above noise.
    above = np.nonzero(env <= noise * 10 ** 0.5)[0]
    cut = (above[0] if above.size else nb) * blk
    cut = max(cut, 10 * blk)
    ec = np.clip(e[:cut] - noise, 0, None)
    edc = np.cumsum(ec[::-1])[::-1]
    if edc[0] <= 0:
        return None, "none", None, float(rng_db)
    edc_db = 10 * np.log10(np.maximum(edc / edc[0], 1e-12))
    t = np.arange(len(edc_db)) / fs

    def fit(lo: float, hi: float) -> Optional[float]:
        m = (edc_db <= lo) & (edc_db >= hi)
        if m.sum() < int(0.005 * fs):
            return None
        slope = np.polyfit(t[m], edc_db[m], 1)[0]
        return float(-60.0 / slope) if slope < 0 else None

    edt = fit(0.0, -10.0)
    if edc_db.min() <= -25 and rng_db >= 35:
        rt, method = fit(-5.0, -25.0), "T20"
    elif edc_db.min() <= -15 and rng_db >= 25:
        rt, method = fit(-5.0, -15.0), "T10"
    else:
        rt, method = None, "none"
    if rt is None:
        method = "none"
    return rt, method, edt, float(rng_db)


def early_reflections(h: np.ndarray, fs: int, c: float = 343.0, speaker_mic_m: float = 0.1,
                      max_distance_m: float = 15.0, guard_ms: float = 1.5, min_strength_db: float = -16.0,
                      min_contrast_db: float = 6.0, max_n: int = 12, band=(1000.0, 12000.0)) -> List[Reflection]:
    """Strong peaks in the IR envelope after the direct sound.

    Path speaker->surface->mic ~= delay*c + speaker_mic; one-way distance = half.
    A far wall is quieter only because of 1/r spreading, so each peak is
    compensated by 20*log10(path / speaker_mic): `strength_db` is then ~0 dB for
    a perfect flat reflector and lower for weak/diffuse ones, independent of
    distance. Peaks must also be >=10 dB above the noise floor (uncompensated)
    and stand `min_contrast_db` above the local envelope median (a specular
    surface sticks out of the diffuse clutter). The *earliest* `max_n` such peaks
    are returned: first-order surfaces (nearest walls, ceiling) arrive first.
    """
    hb = _band(h, fs, *band)
    env = np.abs(hilbert(hb))
    d = int(np.argmax(env))
    direct = env[d]
    if direct <= 0:
        return []
    env_db = 20 * np.log10(np.maximum(env / direct, 1e-9))
    noise_db = 10 * np.log10(max(_noise_energy(env ** 2) / direct ** 2, 1e-18))
    a = d + int(guard_ms * 1e-3 * fs)
    b = min(d + int((2 * max_distance_m - speaker_mic_m) / c * fs), len(env))
    if b <= a:
        return []
    delay = (np.arange(a, b) - d) / fs
    path = delay * c + speaker_mic_m
    strength = env_db[a:b] + 20 * np.log10(path / max(speaker_mic_m, 1e-3))
    pk, props = find_peaks(strength, height=min_strength_db, distance=max(int(0.0006 * fs), 1),
                           prominence=3.0)
    pk = pk[env_db[a:b][pk] >= noise_db + 10.0]
    win = max(int(0.005 * fs), 1)
    local = np.array([np.median(env_db[max(a + i - win, d + 1): a + i + win]) for i in pk])
    pk = pk[env_db[a:b][pk] - local >= min_contrast_db] if pk.size else pk
    if pk.size == 0:
        return []
    out = []
    for i in pk[:max_n]:
        out.append(Reflection(distance_m=round(float(path[i] / 2), 3),
                              delay_ms=round(float(delay[i] * 1e3), 3),
                              level_db=round(float(env_db[a + i]), 1),
                              strength_db=round(float(strength[i]), 1)))
    return out


def snr_db(h: np.ndarray) -> float:
    e = h ** 2
    return float(10 * np.log10(e.max() / max(_noise_energy(e), 1e-30)))


def extract(h: np.ndarray, fs: int, c: float = 343.0, speaker_mic_m: float = 0.1,
            max_distance_m: float = 15.0, bands: Sequence[float] = (500.0, 1000.0, 2000.0)) -> IRFeatures:
    rts: Dict[str, Optional[float]] = {}
    methods, edts, ranges = [], [], []
    for fc in bands:
        hb = _band(h, fs, fc / np.sqrt(2), fc * np.sqrt(2))
        rt, m, edt, rng = schroeder_rt60(hb, fs)
        rts[str(int(fc))] = None if rt is None else round(rt, 3)
        if rt is not None:
            methods.append(m)
        if edt is not None:
            edts.append(edt)
        ranges.append(rng)
    good = [v for v in rts.values() if v is not None]
    rt60 = float(np.median(good)) if good else None
    method = "T20" if methods and all(m == "T20" for m in methods) else ("T10" if methods else "none")
    return IRFeatures(
        rt60_s=None if rt60 is None else round(rt60, 3), rt60_bands_s=rts, rt60_method=method,
        edt_s=round(float(np.median(edts)), 3) if edts else None,
        snr_db=round(snr_db(h), 1), decay_range_db=round(float(np.median(ranges)), 1),
        reflections=early_reflections(h, fs, c, speaker_mic_m, max_distance_m))


def ir_preview(h: np.ndarray, fs: int, length_s: float = 0.3, points: int = 300) -> List[float]:
    """Downsampled, normalised |h| envelope in dB (0 = direct) for display only."""
    n = min(int(length_s * fs), len(h))
    e = np.abs(h[:n])
    blk = max(n // points, 1)
    m = e[: blk * (n // blk)].reshape(-1, blk).max(axis=1)
    db = 20 * np.log10(np.maximum(m / max(m.max(), 1e-12), 1e-4))
    return [round(float(x), 1) for x in db]
