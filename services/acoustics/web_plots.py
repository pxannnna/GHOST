"""Local PNG presentation of browser recordings using Anna's plotting helpers.

Keeps plot.py intact. The coloured position traces follow Anna's study-room
figures; agreement, decay and recording figures use her original functions.
Run with a saved web recording directory to regenerate without playing audio.
"""
import json
from pathlib import Path
import re
import sys

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


def traces(ps, cfg, out):
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
        ax.set_title(f"{p['label']}   RT60 {p['feats'].rt60_s} s   mic height {p['mic_h']} m",
                     loc='left', color=anna.INK, fontsize=11)
    np.atleast_1d(axes)[-1].set_xlabel('distance from the laptop to the reflecting surface (m)   —   dots = detected echoes',
                                    color=anna.INK2, fontsize=9)
    fig.suptitle('Echo traces by measurement position', x=.01, ha='left', color=anna.INK, fontsize=12)
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
    cfg = load_config()['echolocation'].copy()
    cfg.update(speaker_mic_m=data['settings']['speaker_mic_m'], mic_height_m=data['mic_height_m'])
    ps = [anna.load_position(d, cfg) for d in dirs]
    latest = next((p for p in ps if p['dir'] == current), None) or anna.load_position(current, cfg)
    out = ROOT / 'web' / 'acoustic-plots' / current.parent.name / current.name
    out.mkdir(parents=True, exist_ok=True)
    # Rejected captures get their own trace, without entering accepted comparisons.
    displayed = ps if usable(data) else [latest]
    traces(displayed, cfg, out / 'traces.png')
    anna.fig_recording(latest, out / 'recording.png')
    if ps:
        anna.fig_decay(ps, out / 'decay.png')
    if len(ps) >= 2:
        anna.fig_agreement(ps, cfg, None, out / 'agreement.png')
    manifest = {'measurement_id': data['measurement']['measurement_id'],
                'positions': [p['label'] for p in displayed],
                'accepted_positions': [p['label'] for p in ps],
                'plots': ['traces', 'recording'] + (['decay'] if ps else []) + (['agreement'] if len(ps) >= 2 else [])}
    # Written last so the browser never sees a half-generated set.
    (out / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    print(json.dumps(render_capture(sys.argv[1])))
