import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from services.wifi.live import api, firmware
from services.wifi.live.protocol import Status


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        images = []
        for offset in (0, 0x8000, 0x1d000, 0x20000):
            name = f'{offset}.bin'
            (self.root / name).write_bytes(b'firmware-test')
            images.append({'address': hex(offset), 'file': name,
                           'sha256': hashlib.sha256(b'firmware-test').hexdigest()})
        self.spec = dict(target='esp32c6', firmware_id='ghost-radar-1', protocol=1,
                         flash_mode='dio', flash_freq='80m', flash_size='4MB', images=images)
        self.manifest = self.root / 'manifest.json'

    def save(self):
        self.manifest.write_text(json.dumps(self.spec))
        return self.manifest

    def test_complete_package(self):
        args = firmware.flash_args(self.save())
        self.assertEqual(args[::2], ['0x0', '0x8000', '0x1d000', '0x20000'])

    def test_corruption_never_starts_writer(self):
        self.save()
        (self.root / '0.bin').write_bytes(b'corrupted')
        with patch.object(firmware.subprocess, 'Popen') as process:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                firmware.install('COM5', lambda _: None, self.manifest)
            process.assert_not_called()

    def test_invalid_chip_missing_images_paths_and_ranges(self):
        original = json.dumps(self.spec)
        for change in ('chip', 'missing', 'path', 'duplicate', 'nvs'):
            with self.subTest(change=change):
                self.spec = json.loads(original)
                if change == 'chip': self.spec['target'] = 'esp32'
                if change == 'missing': self.spec['images'].pop()
                if change == 'path': self.spec['images'][0]['file'] = '../outside.bin'
                if change == 'duplicate': self.spec['images'][1]['address'] = '0x0'
                if change == 'nvs': self.spec['images'][1]['address'] = '0xd000'
                with self.assertRaises(ValueError): firmware.flash_args(self.save())


class MaintenanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.controller = api.Controller()
        self.board = SimpleNamespace(device='COM5', serial_number='board-1', location='usb', vid=0x303a, pid=0x1001)
        self.ports = patch.object(api.list_ports, 'comports', return_value=[self.board])
        self.ports.start()
        self.addCleanup(self.ports.stop)

    async def test_restart_releases_port_and_verifies_without_writing(self):
        events = []
        async def close(): events.append('close')
        def reconnect(**kwargs):
            events.append('reconnect')
            self.assertEqual(kwargs['remembered'], 'board-1')
            self.controller.session.status = Status(1, 'ghost-radar-1', 1000, False, False, False, 0, 0)
        with patch.object(self.controller, 'close', side_effect=close), patch.object(self.controller, 'start_worker', side_effect=reconnect), \
             patch.object(firmware, 'restart', side_effect=lambda _: events.append('restart')), patch.object(firmware, 'install') as install:
            await self.controller.maintain('restart', 'COM5')
            # A second request must be rejected, not queued to run later.
            with self.assertRaises(HTTPException) as exc: await self.controller.connect('COM5')
            self.assertEqual(exc.exception.status_code, 409)
            with self.assertRaises(HTTPException): await self.controller.maintain('restart', 'COM5')
            await self.controller.maintenance_task
            install.assert_not_called()
        self.assertEqual(events, ['close', 'restart', 'reconnect'])
        self.assertEqual(self.controller.maintenance['status'], 'success')

    async def test_install_failure_is_visible_and_controls_unlock(self):
        with patch.object(self.controller, 'close', new_callable=AsyncMock), \
             patch.object(firmware, 'package_info', return_value={'available': True}), \
             patch.object(firmware, 'install', side_effect=RuntimeError('USB disconnected')):
            await self.controller.maintain('install', 'COM5')
            await self.controller.maintenance_task
        self.assertEqual(self.controller.maintenance['status'], 'error')
        self.assertIn('USB disconnected', self.controller.maintenance['message'])
        self.controller.ensure_available()

    async def test_reset_without_firmware_response_is_not_success(self):
        with patch.object(self.controller, 'close', new_callable=AsyncMock), \
             patch.object(self.controller, 'start_worker'), patch.object(firmware, 'restart'), \
             patch.object(api.asyncio, 'sleep', new_callable=AsyncMock):
            await self.controller.maintain('restart', 'COM5')
            await self.controller.maintenance_task
        self.assertEqual(self.controller.maintenance['status'], 'error')
        self.assertIn('No firmware response', self.controller.maintenance['message'])

    async def test_busy_detection_or_wrong_device_rejected(self):
        self.controller.session.stage = 'detecting'
        with self.assertRaises(HTTPException): await self.controller.maintain('restart', 'COM5')
        self.controller.session.stage = 'idle'
        with self.assertRaises(HTTPException): await self.controller.maintain('install', 'COM99')
        self.assertIsNone(self.controller.maintenance_task)

    async def test_install_requires_explicit_confirmation(self):
        with patch.object(api, 'controller', self.controller), patch.object(self.controller, 'maintain', new_callable=AsyncMock) as maintain:
            with self.assertRaises(HTTPException) as exc:
                await api.install_firmware(api.Installation(port='COM5', confirmed=False))
            self.assertEqual(exc.exception.status_code, 422)
            maintain.assert_not_awaited()

    def test_missing_firmware_response_is_actionable(self):
        session = api.MotionSession()
        session.event('opened', 'COM5', 0)
        session.tick(9)
        self.assertTrue(session.snapshot(9)['firmware_unresponsive'])
        self.assertIn('Restart receiver', session.message)


if __name__ == '__main__':
    unittest.main()
