import asyncio
import copy
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch, AsyncMock

from fastapi import HTTPException
from services.acoustics import web_api as api

IN = {'id': 9, 'name': 'Test microphone', 'api': 'Windows WASAPI'}
OUT = {'id': 8, 'name': 'Test speaker', 'api': 'Windows WASAPI'}


def recording(label='P1'):
    return {'measurement': {'measurement_id': 'test/'+label, 'position_label': label,
                            'rt60_s': .36, 'snr_db': 70, 'reflection_distances_m': [1.1, 1.7],
                            'reflections': [{'strength_db': 8}, {'strength_db': 9}]},
            'mic_height_m': .75, 'chart': [[0,0],[20,-45]],
            'info': {'capture_checks': [{'clipped': False, 'too_quiet': False}]},
            'settings': {'input': IN, 'output': OUT, 'gain': .1, 'mic_height_m': .75, 'speaker_mic_m': .1}}


class AcousticWebTests(unittest.IsolatedAsyncioTestCase):
    async def test_automatic_reference_preserves_ranking_and_refreshes_after_filter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'data' / 'echo' / ('web-' + self.s.session_id) / 'P1_20261108-090000'
            folder.mkdir(parents=True)
            data = recording(); data['recording_dir'] = str(folder.relative_to(root))
            self.s.accepted = [data]; self.s.last = data; self.s.rerank(); self.s.stage = 'ready'
            before = copy.deepcopy(self.s.result)
            manifest = root / 'web' / 'acoustic-plots' / folder.parent.name / folder.name / 'manifest.json'
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({'revision': 'new'}))
            proc = unittest.mock.Mock(returncode=0)
            proc.communicate = AsyncMock(return_value=(b'', None))
            with patch.object(api, 'ROOT', root), patch.object(api, 'DATA_DIR', root/'data'), patch.object(api, 'controller', self.s), patch.object(api.asyncio, 'create_subprocess_exec', AsyncMock(return_value=proc)):
                await self.s.refresh_plots()
                reference = json.loads((folder.parent/'plot_reference.json').read_text())
                self.assertEqual(reference['room_id'], 'nuc-3-studyroom')
                self.assertEqual(reference['ceiling_height_m'], 2.45)
                self.assertEqual(self.s.result, before)
                self.assertEqual(self.s.last['plot_revision'], 'new')
                self.assertEqual(self.s.stage, 'ready')
                await api.floor(api.Settings(floor_id='2'))
                reference = json.loads((folder.parent/'plot_reference.json').read_text())
                self.assertNotEqual(reference['room_id'], 'nuc-3-studyroom')
                self.assertEqual(self.s.accepted, [data])
                self.s.result = {'status': 'no_match', 'candidates': before['candidates']}
                await self.s.refresh_plots()
                self.assertIsNone(json.loads((folder.parent/'plot_reference.json').read_text())['ceiling_height_m'])

    async def test_plot_failure_keeps_recordings_and_restores_stage(self):
        self.s.accepted = [recording()]; self.s.last = self.s.accepted[0]
        self.s.rerank(); self.s.stage = 'ready'
        self.s.last['recording_dir'] = 'outside-session'
        before = copy.deepcopy(self.s.result)
        await self.s.refresh_plots()
        self.assertEqual(self.s.stage, 'ready')
        self.assertEqual(self.s.result, before)
        self.assertIn('plot_error', self.s.last)

    def setUp(self):
        self.s = api.Session()
        self.s.publisher = AsyncMock()
        self.inventory = patch.object(api, 'devices', return_value={'inputs':[IN], 'outputs':[OUT]})
        self.inventory.start()
        self.addCleanup(self.inventory.stop)

    def body(self, **kwargs):
        return api.Capture(input_id=9, output_id=8, floor_id='3', **kwargs)

    async def test_measurement_and_floor_filter_reuse_same_data(self):
        with patch.object(api, 'capture_process', return_value=recording()) as capture:
            await self.s.start(self.body())
            await self.s.task
            self.assertEqual(self.s.stage,'ready')
            self.assertEqual(len(self.s.result['candidates']),2)
            self.assertEqual(self.s.result['candidates'][0]['room_id'],'nuc-3-studyroom')
            with patch.object(api, 'controller', self.s):
                await api.floor(api.Settings(floor_id=None))
            self.assertEqual(len(self.s.result['candidates']),14)
            self.assertEqual(capture.call_count,1)
            self.assertEqual(len(self.s.accepted),1)

    async def test_no_double_capture_or_filter_change_while_recording(self):
        self.s.stage='measuring'
        with patch.object(api,'capture_process') as capture, patch.object(api,'controller',self.s):
            for action in (self.s.start(self.body()), api.floor(api.Settings(floor_id='2')), api.reset()):
                with self.assertRaises(HTTPException): await action
            capture.assert_not_called()

    async def test_rejected_recording_does_not_change_accepted_ranking(self):
        self.s.accepted=[recording()];self.s.floor_id='3';self.s.rerank()
        before=copy.deepcopy(self.s.result)
        bad=recording('P2');bad['info']['capture_checks'][0]['too_quiet']=True
        with patch.object(api,'capture_process',return_value=bad):
            await self.s.start(self.body(new_position=True));await self.s.task
        self.assertEqual(self.s.stage,'rejected');self.assertEqual(len(self.s.accepted),1)
        self.assertEqual(self.s.result,before);self.assertTrue(self.s.last['quality_issues'])
        self.s.publisher.assert_not_awaited()

    async def test_movement_and_consistent_setup_required(self):
        self.s.accepted=[recording()]
        with self.assertRaises(HTTPException):await self.s.start(self.body())
        with self.assertRaises(HTTPException):await self.s.start(self.body(new_position=True,gain=.2))
        self.assertIsNone(self.s.task)

    async def test_cancel_discards_result_even_if_process_finishes(self):
        def cancelled_capture(*args):
            self.s.cancelled.set()
            return recording()
        with patch.object(api,'capture_process',side_effect=cancelled_capture):
            await self.s.start(self.body());await self.s.task
        self.assertEqual(self.s.stage,'cancelled');self.assertFalse(self.s.accepted)
        self.s.publisher.assert_not_awaited()

    async def test_failed_device_does_not_start_capture(self):
        with self.assertRaises(HTTPException):
            await self.s.start(api.Capture(input_id=99,output_id=8))
        self.assertIsNone(self.s.task)

    def test_quality_checks_each_sweep(self):
        data=recording();data['info']['capture_checks']=[{'clipped':True},{'clipped':False}]
        self.assertTrue(api.quality(data))
        data=recording();data['measurement']['snr_db']=30
        self.assertTrue(api.quality(data))


if __name__ == '__main__': unittest.main()
