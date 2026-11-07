"""Plots of saved echolocation measurements: see the sound, the echoes and the decay.

    python -m services.acoustics.plot --room nuc-3-studyroom
    python -m services.acoustics.plot --room nuc-3-studyroom --ceiling-height 2.45 --since 20261107-22

Reads data/echo/<room>/P*_*/ (newest recording per position) and writes four PNGs to
data/echo/<room>/plots/:

  1_recording.png    what the microphone heard during one sweep (waveform + spectrogram)
  2_echo_traces.png  one echo trace per position: loudness against distance to the reflecting surface
  3_agreement.png    positions stacked: an echo at the SAME distance in every row (a vertical stripe) is the ceiling
  4_decay.png        how fast the sound dies away (reverberation), per position

If --ceiling-height is not given it is read from data/echo/<room>/room_notes.json when present.
The predicted ceiling echo is drawn at (ceiling height - mic height) so you can see whether the
real echo lands there. No audio hardware is needed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")  # write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from scipy.ndimage import maximum_filter1d  # noqa: E402
from scipy.signal import hilbert  # noqa: E402

from shared.config import DATA_DIR, load_config  # noqa: E402
from services.acoustics import features as F  # noqa: E402
from services.acoustics.reanalyze import latest_per_position  # noqa: E402
from services.acoustics.sweep import ir_from_recordings, make_sweep  # noqa: E402

# Validated categorical slots 1-8 (dataviz reference palette, light mode). A position keeps its
# colour (P1 = blue, P2 = orange, ...) in every figure.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]  # sequential
LW = 1.5  # ~2 px


def _style(ax, ylabel: str = "", xlabel: str = "") -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)


def _colour(label: str) -> str:
    return SERIES[(int(label[1:]) - 1) % len(SERIES)]


def load_position(d: Path, ecfg: Dict[str, Any]) -> Dict[str, Any]:
    meta = json.loads((d / "measurement.json").read_text())
    fs, s = meta["fs"], meta["sweep"]
    sweep = make_sweep(fs, s["f1"], s["f2"], s["duration_s"])
    recs = [sf.read(p)[0] for p in sorted(d.glob("rec_*.wav"))]
    ir = ir_from_recordings(recs, sweep, length_s=ecfg["ir_length_s"])
    feats = F.extract(ir, fs, c=ecfg["speed_of_sound_mps"], speaker_mic_m=ecfg["speaker_mic_m"],
                      max_distance_m=ecfg["max_reflection_distance_m"])
    return {"label": d.name.split("_")[0], "dir": d, "fs": fs, "recs": recs, "ir": ir, "feats": feats,
            "mic_h": float(meta.get("mic_height_m", ecfg["mic_height_m"])), "sweep": sweep}


def echo_curve(p: Dict[str, Any], ecfg: Dict[str, Any], max_dist: float, compensate: bool = False):
    """(distance_m, level_dB) of the echo envelope. Level is relative to the direct sound; with
    `compensate` it is also corrected for 1/r spreading, so a flat reflector sits near 0 dB at any
    distance (this is what the detector uses)."""
    fs, c, sm = p["fs"], ecfg["speed_of_sound_mps"], ecfg["speaker_mic_m"]
    env = np.abs(hilbert(F._band(p["ir"], fs, 1000.0, 12000.0)))
    d = int(np.argmax(env))
    n = int((2 * max_dist - sm) / c * fs)
    seg = env[d: d + n]
    db = 20 * np.log10(np.maximum(seg / env[d], 1e-9))
    dist = ((np.arange(len(seg)) / fs) * c + sm) / 2
    if compensate:
        db = db + 20 * np.log10(np.maximum(2 * dist, sm) / sm)
    return dist, db


def schroeder_curve(p: Dict[str, Any], fc: float = 1000.0, skip_ms: float = 3.0):
    """Backward-integrated decay of the `fc` octave band, as used for the RT60 (see features.py)."""
    fs = p["fs"]
    hb = F._band(p["ir"], fs, fc / np.sqrt(2), fc * np.sqrt(2))
    d = int(np.argmax(np.abs(hb))) + int(skip_ms * 1e-3 * fs)
    e = hb[d:] ** 2
    noise = float(np.mean(e[-int(0.15 * len(e)):]))
    blk = int(0.01 * fs)
    env = e[: (len(e) // blk) * blk].reshape(-1, blk).mean(axis=1)
    below = np.nonzero(env <= noise * 10 ** 0.5)[0]
    cut = max((below[0] if below.size else len(env)) * blk, 10 * blk)
    edc = np.cumsum(np.clip(e[:cut] - noise, 0, None)[::-1])[::-1]
    return np.arange(len(edc)) / fs, 10 * np.log10(np.maximum(edc / edc[0], 1e-12))


def fig_recording(p: Dict[str, Any], out: Path) -> None:
    fs, x = p["fs"], p["recs"][0]
    t = np.arange(len(x)) / fs
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True, facecolor=SURFACE,
                                 gridspec_kw={"height_ratios": [1, 2]})
    a1.plot(t, x, color=SERIES[0], lw=0.6)
    _style(a1, "microphone signal")
    a1.set_title(f"What the microphone heard during one sweep ({p['label']})", loc="left", color=INK, fontsize=12)
    a1.text(0.62, 0.93, "<- the chirp, played by the laptop (louder where\n    the speaker and room are strongest)", transform=a1.transAxes,
            color=INK2, fontsize=9, va="top")
    cmap = LinearSegmentedColormap.from_list("blues", BLUES)
    Pxx, freqs, bins, im = a2.specgram(x, NFFT=2048, Fs=fs, noverlap=1536, cmap=cmap, scale="dB")
    im.set_clim(np.nanmax(10 * np.log10(Pxx + 1e-20)) - 90, np.nanmax(10 * np.log10(Pxx + 1e-20)))
    a2.set_yscale("log")
    a2.set_ylim(150, 22000)
    a2.set_yticks([200, 500, 1000, 2000, 5000, 10000, 20000])
    a2.set_yticklabels(["200", "500", "1k", "2k", "5k", "10k", "20k"])
    _style(a2, "frequency (Hz)", "time (s)")
    a2.grid(False)
    a2.text(0.62, 0.40, "faint parallel lines ABOVE the chirp = the small\nspeaker's own distortion (the analysis discards it)\n\nhaze BELOW the line = the room ringing on",
            transform=a2.transAxes, color=INK, fontsize=9, va="top", bbox=dict(fc=SURFACE, ec="none", alpha=0.85, pad=2))
    a2.text(0.01, 0.95, "the chirp rises from 200 Hz to 20 kHz",
            transform=a2.transAxes, color=INK, fontsize=9, va="top",
            bbox=dict(fc=SURFACE, ec="none", alpha=0.85, pad=2))
    fig.tight_layout()
    fig.savefig(out, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def fig_traces(ps: List[Dict[str, Any]], ecfg: Dict[str, Any], ceiling: Optional[float], max_dist: float,
               out: Path) -> None:
    fig, axes = plt.subplots(len(ps), 1, figsize=(11, 2.35 * len(ps) + 0.9), sharex=True, facecolor=SURFACE)
    axes = np.atleast_1d(axes)
    for ax, p in zip(axes, ps):
        col = _colour(p["label"])
        dist, db = echo_curve(p, ecfg, max_dist)
        ax.plot(dist, db, color=col, lw=1.0)
        refl = p["feats"].reflections
        ax.plot([r.distance_m for r in refl], [r.level_db for r in refl], "o", ms=6, mfc=col, mec=SURFACE, mew=1.5)
        if ceiling is not None:
            x = ceiling - p["mic_h"]
            ax.axvline(x, color=INK2, lw=1.2, ls="--")
            ax.text(x + 0.05, -8, f"expected ceiling echo {x:.2f} m", color=INK2, fontsize=8, va="top")
        _style(ax, "level vs direct (dB)")
        ax.set_ylim(-80, 3)
        rt = p["feats"].rt60_s
        ax.set_title(f"{p['label']}   RT60 {rt} s   mic height {p['mic_h']} m", loc="left", color=INK, fontsize=10)
    axes[0].text(0.3, -3, "<- direct sound (speaker to mic)", color=INK2, fontsize=8, va="top")
    axes[-1].set_xlim(0, max_dist)
    axes[-1].set_xlabel("distance from the laptop to the reflecting surface (m)   -   dots = echoes the tool picked", color=INK2, fontsize=9)
    fig.suptitle("Echo traces: each spike is a surface sound bounced off", x=0.01, ha="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def fig_agreement(ps: List[Dict[str, Any]], ecfg: Dict[str, Any], ceiling: Optional[float], out: Path,
                  lo: float = 0.5, hi: float = 4.5, threshold_db: float = -16.0, win_m: float = 0.06) -> List[tuple]:
    """Top: one strip per position (darker = stronger echo). Bottom: at each distance, how many
    positions have an echo there. The ceiling stays at the same distance wherever you stand, so it
    shows as a vertical stripe across the rows and a plateau at the maximum count; walls move."""
    grid = np.arange(lo, hi, 0.01)
    rows = []
    for p in ps:
        dist, db = echo_curve(p, ecfg, hi + 0.5, compensate=True)
        size = max(int(win_m / (ecfg["speed_of_sound_mps"] / (2 * p["fs"]))), 1)
        rows.append(np.interp(grid, dist, maximum_filter1d(db, size=size)))
    rows = np.array(rows)
    n = len(ps)
    count = (rows >= threshold_db).sum(axis=0)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 5.8), sharex=True, facecolor=SURFACE,
                                 gridspec_kw={"height_ratios": [2, 1.2]})
    cmap = LinearSegmentedColormap.from_list("blues", BLUES)
    im = a1.imshow(rows, aspect="auto", extent=[lo, hi, n - 0.5, -0.5], cmap=cmap, vmin=-30, vmax=-8,
                   interpolation="nearest")
    a1.set_yticks(range(n))
    a1.set_yticklabels([p["label"] for p in ps])
    _style(a1, "position")
    a1.grid(False)
    cax = fig.add_axes([0.945, 0.56, 0.012, 0.31])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label("echo strength (dB)", color=INK2, fontsize=9)
    cb.ax.tick_params(colors=INK2, labelsize=8)
    a2.fill_between(grid, count, step="mid", color=BLUES[4], lw=0)
    _style(a2, "positions with an echo here", "distance from the laptop to the reflecting surface (m)")
    a2.set_yticks(range(n + 1))
    a2.set_ylim(0, n + 0.6)
    full = []
    start = None
    for g, c_ in zip(grid, count):
        if c_ == n and start is None:
            start = g
        if c_ < n and start is not None:
            full.append((start, g)); start = None
    if start is not None:
        full.append((start, grid[-1]))
    agree = [f"{(x0 + x1) / 2:.2f} m" for x0, x1 in full if (x0 + x1) / 2 > 1.0]
    a2.text(0.99, 0.93, "all %d positions have an echo at: %s" % (n, ", ".join(agree) if agree else "nowhere (apart from the laptop itself)"),
            transform=a2.transAxes, ha="right", va="top", color=INK, fontsize=9)
    if ceiling is not None:
        xs = [ceiling - p["mic_h"] for p in ps]
        for ax in (a1, a2):
            ax.axvspan(min(xs) - 0.05, max(xs) + 0.05, facecolor="none", edgecolor=INK2, lw=1.2, ls="--")
        a1.text(np.mean(xs), -0.62, f"expected ceiling echo {np.mean(xs):.2f} m  ({ceiling} m - mic height)", ha="center",
                va="bottom", color=INK2, fontsize=9)
    a1.set_xlim(lo, hi)
    fig.suptitle("Is there an echo at the same distance from every position?  (dashed box = where the ceiling should be)",
                 x=0.01, ha="left", color=INK, fontsize=11)
    fig.subplots_adjust(top=0.9, left=0.07, right=0.92, bottom=0.1, hspace=0.12)
    fig.savefig(out, dpi=140, facecolor=SURFACE)
    plt.close(fig)
    return full


def fig_decay(ps: List[Dict[str, Any]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.2), facecolor=SURFACE)
    for p in ps:
        col = _colour(p["label"])
        t, db = schroeder_curve(p)
        rt = p["feats"].rt60_bands_s.get("1000")
        ax.plot(t, db, color=col, lw=LW, label=f"{p['label']}   RT60 {rt} s (1 kHz band)")
    for y in (-5, -25):
        ax.axhline(y, color=INK2, lw=0.9, ls=":")
    ax.text(0.99, -5, "RT60 is read from the slope between these two lines", transform=ax.get_yaxis_transform(),
            ha="right", va="bottom", color=INK2, fontsize=8)
    ax.text(0.99, -25, "-25 dB", transform=ax.get_yaxis_transform(), ha="right", va="bottom", color=INK2, fontsize=8)
    ax.text(0.99, 0.04, "the sharp drop at the end = the background noise has been reached; ignore it",
            transform=ax.transAxes, ha="right", va="bottom", color=INK2, fontsize=8)
    _style(ax, "sound energy still left (dB)", "time after the direct sound (s)")
    ax.set_ylim(-65, 3)
    ax.set_xlim(0, max(0.3, ax.get_xlim()[1]))
    leg = ax.legend(loc="lower left", frameon=False, fontsize=9)
    for t_ in leg.get_texts():
        t_.set_color(INK2)
    ax.set_title("How fast the sound dies away. A steep line = a 'dead' room; a long slow slope = a ringing room",
                 loc="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--room", required=True, help="folder under data/echo/")
    ap.add_argument("--since", help="only recordings with timestamp >= this prefix, e.g. 20261107-22")
    ap.add_argument("--ceiling-height", type=float, help="true ceiling height (m); default from room_notes.json")
    ap.add_argument("--max-dist", type=float, default=8.0, help="how far to plot the echo traces (m)")
    ap.add_argument("--out", type=Path, help="output folder (default data/echo/<room>/plots)")
    a = ap.parse_args(argv)

    ecfg = load_config()["echolocation"]
    dirs = latest_per_position(a.room, a.since)
    if not dirs:
        sys.exit(f"no recordings found in data/echo/{a.room}/")
    notes = DATA_DIR / "echo" / a.room / "room_notes.json"
    ceiling = a.ceiling_height
    if ceiling is None and notes.exists():
        ceiling = json.loads(notes.read_text()).get("ceiling_height_m")
    out = a.out or (DATA_DIR / "echo" / a.room / "plots")
    out.mkdir(parents=True, exist_ok=True)
    ps = [load_position(d, ecfg) for d in dirs]
    fig_recording(ps[0], out / "1_recording.png")
    fig_traces(ps, ecfg, ceiling, a.max_dist, out / "2_echo_traces.png")
    full = fig_agreement(ps, ecfg, ceiling, out / "3_agreement.png")
    print("distances where ALL positions have an echo (m):", ", ".join(f"{x0:.2f}-{x1:.2f}" for x0, x1 in full) or "none")
    fig_decay(ps, out / "4_decay.png")
    print(f"wrote 4 plots for {len(ps)} positions to {out}")
    for p in ps:
        print(f"  {p['label']}: {p['dir'].name}")


if __name__ == "__main__":
    main()
