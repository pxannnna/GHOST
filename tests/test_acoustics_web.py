import asyncio
import copy
import unittest
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
