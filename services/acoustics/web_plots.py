"""Local PNG presentation of browser recordings using Anna's plotting helpers.

Keeps plot.py intact. The coloured position traces follow Anna's study-room
figures; agreement, decay and recording figures use her original functions.
Run with a saved web recording directory to regenerate without playing audio.
"""
import json
import math
from pathlib import Path
import re
import sys
import time

import numpy as np

from shared.config import ROOT, load_config
from . import plot as anna


def usable(data):
    m = data['measurement']
    checks = data['info'].get('capture_checks', [data['info']])
    return (not any(c.get('clipped') or c.get('too_quiet') for c in checks)
            and m.get('snr_db') is not None and m['snr_db'] >= 40 and bool(m.get('rt60_s')))


def select_recordings(current):
    """Each earlier P number was accepted before the server allocated the next.

    Retries retain their P number; take its newest usable capture before this one.
    Session folders prevent recordings of another room entering the comparison.
    """
    current_data = json.loads((current / 'web_capture.json').read_text(encoding='utf-8'))
    number = int(current_data['measurement']['position_label'][1:])
    chosen = {}
    for file in current.parent.glob('P*_*/web_capture.json'):
        if file.parent.name.split('_', 1)[1] > current.name.split('_', 1)[1]:
            continue
        data = json.loads(file.read_text(encoding='utf-8'))
        n = int(data['measurement']['position_label'][1:])
        if n >= number or not usable(data):
            continue
        if n not in chosen or file.parent.name > chosen[n].name:
            chosen[n] = file.parent
    if usable(current_data):
        chosen[number] = current
    return [chosen[n] for n in sorted(chosen)], current_data


def reference_ceiling(config):
    """A post-ranking plotting reference, never used as evidence by the matcher."""
    value = config.get('web_plot_reference', {}).get('ceiling_height_m')
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value) or not 0 < value <= 20:
        raise ValueError('Plot reference ceiling height must be between 0 and 20 m.')
    return value


def mark_reference(ax, mic_height, ceiling):
    if ceiling is None or ceiling <= mic_height:
        return None
    distance = ceiling - mic_height
    if distance <= 8:
        ax.axvline(distance, color=anna.INK2, linestyle='--', lw=1.2, zorder=3)
        ax.text(distance + .05 if distance < 5 else distance - .05, -12,
                f'expected ceiling echo {distance:.2f} m',
                ha='left' if distance < 5 else 'right', color=anna.INK2, fontsize=9,
                bbox=dict(fc=anna.SURFACE, ec='none', alpha=.85, pad=1))
    return distance


def traces(ps, cfg, out, ceiling=None):
    fig, axes = anna.plt.subplots(len(ps), 1, figsize=(11, 2.8 * len(ps) + .7),
                                  sharex=True, facecolor=anna.SURFACE)
    for ax, p in zip(np.atleast_1d(axes), ps):
        dist, db = anna.echo_curve(p, cfg, 8.0)
        colour = anna._colour(p['label'])
        ax.plot(dist, db, color=colour, lw=1)
        peaks = p['feats'].reflections
        ax.scatter([r.distance_m for r in peaks], [r.level_db for r in peaks],
                   s=30, color=colour, edgecolors=anna.SURFACE, linewidths=.7, zorder=4)
        anna._style(ax, 'level vs direct (dB)')
        ax.set_ylim(-80, 3)
        ax.set_xlim(0, 8)
        mark_reference(ax, p['mic_h'], ceiling)
        ax.set_title(f"{p['label']}   RT60 {p['feats'].rt60_s} s   mic height {p['mic_h']} m",
                     loc='left', color=anna.INK, fontsize=11)
    np.atleast_1d(axes)[-1].set_xlabel('distance from the laptop to the reflecting surface (m)   —   dots = detected echoes',
                                    color=anna.INK2, fontsize=9)
    np.atleast_1d(axes)[0].text(.3, -6, '← direct sound (speaker to mic)', color=anna.INK2, fontsize=9,
                              zorder=5, bbox=dict(fc=anna.SURFACE, ec='none', alpha=.95, pad=1))
    title = 'Echo traces: sound reflected back to the microphone'
    if ceiling is not None:
        title += f'\nDashed line = candidate reference ceiling {ceiling:.2f} m − microphone height (not a detected peak)'
    fig.suptitle(title, x=.01, ha='left', color=anna.INK, fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, .96))
    anna._save(fig, out, ps)
    anna.plt.close(fig)


def render_capture(directory):
    current = Path(directory).resolve()
    base = (ROOT / 'data' / 'echo').resolve()
    if (not current.is_relative_to(base) or not re.fullmatch(r'web-[0-9a-f]+', current.parent.name)
            or not re.fullmatch(r'P[1-8]_\d{8}-\d{6}', current.name)):
        raise ValueError('Expected a local browser capture directory.')
    dirs, data = select_recordings(current)
    config = load_config()
    reference_file = current.parent / 'plot_reference.json'
    reference = json.loads(reference_file.read_text(encoding='utf-8')) if reference_file.exists() else {}
    ceiling = reference_ceiling({'web_plot_reference': reference})
    cfg = config['echolocation'].copy()
    cfg.update(speaker_mic_m=data['settings']['speaker_mic_m'], mic_height_m=data['mic_height_m'])
    ps = [anna.load_position(d, cfg) for d in dirs]
    latest = next((p for p in ps if p['dir'] == current), None) or anna.load_position(current, cfg)
    out = ROOT / 'web' / 'acoustic-plots' / current.parent.name / current.name
    out.mkdir(parents=True, exist_ok=True)
    # Rejected captures get their own trace, without entering accepted comparisons.
    displayed = ps if usable(data) else [latest]
    traces(displayed, cfg, out / 'traces.png', ceiling)
    anna.fig_recording(latest, out / 'recording.png')
    if ps:
        anna.fig_decay(ps, out / 'decay.png')
    if len(ps) >= 2:
        anna.fig_agreement(ps, cfg, ceiling, out / 'agreement.png')
    manifest = {'measurement_id': data['measurement']['measurement_id'],
                'revision': str(time.time_ns()),
                'reference_ceiling_height_m': ceiling,
                'reference_room_id': reference.get('room_id'),
                'reference_room_label': reference.get('label'),
                'microphone_heights_m': {p['label']: p['mic_h'] for p in displayed},
                'positions': [p['label'] for p in displayed],
                'accepted_positions': [p['label'] for p in ps],
                'plots': ['traces', 'recording'] + (['decay'] if ps else []) + (['agreement'] if len(ps) >= 2 else [])}
    # Written last so the browser never sees a half-generated set.
    (out / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    print(json.dumps(render_capture(sys.argv[1])))
