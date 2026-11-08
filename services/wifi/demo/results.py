"""Local experiment records and descriptive comparisons; no accuracy claims."""
import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import statistics
import time
import uuid

from .protocol import Report


class Session:
    def __init__(self, parent, timing):
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
        self.path = parent/name
        self.path.mkdir(parents=True, exist_ok=False)
        self.start = time.monotonic()
        self.metadata = {'mode':'live', 'started_utc':datetime.now(timezone.utc).isoformat(),
                         'timing': vars(timing), 'firmware':'ghost-radar-1', 'input':'HT-LTF',
                         'status':'in_progress', 'credentials_saved':False,
                         'note':'Device and phone must remain stationary after calibration.'}
        self.streams = {}
        self.writers = {}
        fields = ['host_elapsed_s']+list(Report.__dataclass_fields__)
        for phase in ('empty','walking'):
            stream = (self.path/(phase+'.csv')).open('w', encoding='utf-8', newline='')
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            stream.flush()
            self.streams[phase], self.writers[phase] = stream, writer
        self.events = (self.path/'events.jsonl').open('w', encoding='utf-8')
        self.update()

    def event(self, kind, detail):
        self.events.write(json.dumps({'elapsed_s':time.monotonic()-self.start, 'event':kind, 'detail':detail})+'\n')
        self.events.flush()

    def row(self, phase, row):
        self.writers[phase].writerow(row)
        self.streams[phase].flush()

    def update(self, **kwargs):
        self.metadata.update(kwargs)
        (self.path/'session.json').write_text(json.dumps(self.metadata, indent=2), encoding='utf-8')

    def close(self):
        for stream in self.streams.values():
            stream.close()
        self.events.close()


def summarize(rows):
    if len(rows) < 2:
        raise ValueError('At least two radar reports are needed per condition.')
    times = [r['device_ms']/1000 for r in rows]
    gaps = [b-a for a,b in zip(times,times[1:])]
    if any(d <= 0 for d in gaps):
        raise ValueError('Non-monotonic device timestamps; do not combine recordings across a reboot.')
    return {'reports':len(rows), 'report_span_s':times[-1]-times[0],
            'motion_report_fraction':sum(r['motion'] for r in rows)/len(rows),
            'presence_report_fraction':sum(r['presence'] for r in rows)/len(rows),
            'jitter_median':statistics.median(r['jitter'] for r in rows),
            'wander_median':statistics.median(r['wander_average'] for r in rows),
            'max_report_gap_s':max(gaps), 'report_gaps_over_200ms':sum(g>.2 for g in gaps),
            'motion_rising_edges':sum(a['motion']==0 and b['motion']==1 for a,b in zip(rows,rows[1:])),
            'first_report_motion':bool(rows[0]['motion'])}


def export_results(path, rows, thresholds, mode='live'):
    # Imported only when exporting, so discovery and live display remain light.
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    summary = {name:summarize(data) for name,data in rows.items()}
    summary['mode'] = mode
    summary['thresholds'] = thresholds
    summary['notes'] = [
        'One trial per condition. Report fractions are not accuracy or time coverage.',
        'Missing results are unknown, not evidence of no motion.',
        'The detector measures environmental change, not a specific gesture or person count.',
        'CSI packet rate and radar report rate are different quantities.',
        'No raw CSI samples are saved by this demo; CSV files contain official detector outputs.'
    ]
    (path/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    fig = Figure(figsize=(12,8), layout='constrained')
    axes = fig.subplots(3,2,sharex='col',sharey='row')
    for col, name in enumerate(('empty','walking')):
        data = rows[name]
        t = [(r['device_ms']-data[0]['device_ms'])/1000 for r in data]
        def line(ax, key, label, **kw):
            values = [r[key] if i==0 or t[i]-t[i-1]<=.2 else float('nan') for i,r in enumerate(data)]
            ax.plot(t, values, label=label, **kw)
        line(axes[0,col], 'jitter', 'Jitter', lw=.8)
        axes[0,col].axhline(thresholds['motion']/.2, color='#c77912', ls='--', label='Fixed motion reference')
        line(axes[0,col], 'rolling_motion_reference', 'Rolling reference', lw=.7, alpha=.6)
        line(axes[1,col], 'wander_average', 'Smoothed wander', lw=1)
        line(axes[1,col], 'presence_threshold_scaled', 'Presence threshold', ls='--')
        line(axes[2,col], 'motion', 'Motion', drawstyle='steps-post')
        line(axes[2,col], 'presence', 'Presence', alpha=.5, drawstyle='steps-post')
        axes[0,col].set_title(name.title()+f": motion reports {summary[name]['motion_report_fraction']:.1%}")
        axes[2,col].set_xlabel('Seconds from first report')
        axes[2,col].set_ylim(-.1,1.2)
        for row in range(3):
            axes[row,col].grid(alpha=.2)
            axes[row,col].legend(fontsize=7,loc='upper right')
    for i, label in enumerate(('Motion feature','Presence feature','Official decision (0/1)')):
        axes[i,0].set_ylabel(label)
    fig.suptitle('GHOST | official ESP-Radar 0.3.4 | HT-LTF | '+mode)
    fig.savefig(path/'comparison.png', dpi=150)
    table = ''
    for key,label in [('reports','Reports'),('motion_report_fraction','Motion report fraction'),
                      ('presence_report_fraction','Presence report fraction'),('jitter_median','Median jitter'),
                      ('wander_median','Median smoothed wander'),('max_report_gap_s','Longest report gap (s)')]:
        values = [summary[n][key] for n in ('empty','walking')]
        formatted = [f'{v:.1%}' if 'fraction' in key else f'{v:.5g}' for v in values]
        table += '<tr><td>'+label+'</td>'+''.join('<td>'+v+'</td>' for v in formatted)+'</tr>'
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>GHOST experiment results</title>
<style>body{font:17px system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#173044}
table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #ccd6df;text-align:left}img{width:100%}</style>
<h1>Empty room and walking</h1><p>Both trials use one empty-room calibration.</p>
<table><tr><th>Metric</th><th>Empty room</th><th>Walking</th></tr>'''+table+'</table><ul>'
    page += '<li>Data mode: '+html.escape(mode)+'</li>'
    page += ''.join('<li>'+html.escape(note)+'</li>' for note in summary['notes'])
    page += '</ul><img src="comparison.png" alt="Three rows compare motion features, presence features and decisions."></html>'
    (path/'report.html').write_text(page, encoding='utf-8')
    return summary
