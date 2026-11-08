import json
from pathlib import Path
import tempfile
import unittest

from services.acoustics.web_plots import select_recordings, render_capture


class WebPlotSelectionTests(unittest.TestCase):
    def test_retries_rejections_and_future_positions_do_not_pollute_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def save(label, timestamp, valid=True):
                folder = root / f'{label}_{timestamp}'
                folder.mkdir()
                data = {'measurement': {'position_label': label, 'rt60_s': .38, 'snr_db': 70},
                        'info': {'capture_checks': [{'clipped': not valid, 'too_quiet': False}]}}
                (folder / 'web_capture.json').write_text(json.dumps(data), encoding='utf-8')
                return folder
            save('P1', '20261108-090000')
            p1 = save('P1', '20261108-090100')
            save('P1', '20261108-090200', False)
            p2 = save('P2', '20261108-090300')
            save('P1', '20261108-091000')
            save('P3', '20261108-091100')
            self.assertEqual(select_recordings(p2)[0], [p1, p2])
            rejected = save('P3', '20261108-090400', False)
            self.assertEqual(select_recordings(rejected)[0], [p1, p2])

    def test_renderer_rejects_paths_outside_browser_capture_tree(self):
        with self.assertRaises(ValueError):
            render_capture(Path(__file__).parent)
