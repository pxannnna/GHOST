"""One cancellable audio capture process. No network access or Hub publishing."""
import json
from pathlib import Path
import sys

import numpy as np
import sounddevice as sd
from scipy.signal import hilbert

from shared.config import load_config
from .measure import measure_position


def capture(settings):
    for kind in ('input', 'output'):
        actual = sd.query_devices(settings[kind]['id'])
        host = sd.query_hostapis(actual['hostapi'])['name']
        if actual['name'] != settings[kind]['name'] or host != settings[kind]['api']:
            raise RuntimeError('Audio devices changed. Refresh the device list before measuring.')
    sd.default.device = (settings['input']['id'], settings['output']['id'])
    if settings['input']['api'] == 'Windows WASAPI':
        sd.default.extra_settings = (sd.WasapiSettings(exclusive=True), sd.WasapiSettings(exclusive=True))
    cfg = load_config()['echolocation']
    cfg.update(input_device=None, output_device=None, output_gain=settings['gain'],
               mic_height_m=settings['mic_height_m'], speaker_mic_m=settings['speaker_mic_m'])
    def progress(index, total):
        print(json.dumps({'progress': index, 'total': total}), flush=True)
    result = measure_position(settings['position'], 'web-' + settings['session'], repeats=3,
                              mic_height=settings['mic_height_m'], cfg=cfg, progress=progress)
    envelope = np.abs(hilbert(result.ir))
    direct = int(np.argmax(np.abs(result.ir)))
    end = min(len(envelope), direct + int(.06 * result.fs))
    # Fixed dB scale and actual delay axis; no per-measurement graph stretching.
    t = np.arange(direct, end)
    bins = np.array_split(t, min(600, len(t)))
    chart = [[round(float((b[0]-direct)/result.fs*1000), 3),
              round(float(max(-80, 20*np.log10(max(envelope[b].max()/max(envelope[direct],1e-12),1e-4)))), 2)] for b in bins]
    payload = {'measurement': result.payload(), 'info': result.info, 'chart': chart,
               'recording_dir': str(result.out_dir.relative_to(Path(__file__).resolve().parents[2])),
               'mic_height_m': result.mic_height_m, 'settings': settings}
    (result.out_dir/'web_capture.json').write_text(json.dumps(payload, allow_nan=False), encoding='utf-8')
    return payload


if __name__ == '__main__':
    job = Path(sys.argv[1])
    try:
        result = capture(json.loads(job.read_text(encoding='utf-8')))
        job.with_suffix('.result.json').write_text(json.dumps(result, allow_nan=False), encoding='utf-8')
    except Exception as exc:
        print(json.dumps({'error': str(exc)}), flush=True)
        sys.exit(1)
