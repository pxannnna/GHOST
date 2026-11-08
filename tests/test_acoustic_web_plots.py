import json
from pathlib import Path
import tempfile
import unittest

from services.acoustics.web_plots import select_recordings, render_capture, reference_ceiling, mark_reference, anna


class WebPlotSelectionTests(unittest.TestCase):
    def test_reference_marker_uses_actual_mic_height_and_requires_explicit_reference(self):
        self.assertIsNone(reference_ceiling({'echolocation': {'mic_height_m': .75}}))
        ceiling = reference_ceiling({'web_plot_reference': {'ceiling_height_m': 2.45}})
        fig, axes = anna.plt.subplots(2, 1)
        try:
            mark_reference(axes[0], .75, ceiling)
            self.assertIn('1.70 m', axes[0].texts[0].get_text())
            mark_reference(axes[1], .45, 2.5)
            self.assertIn('2.05 m', axes[1].texts[0].get_text())
        finally:
            anna.plt.close(fig)

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
