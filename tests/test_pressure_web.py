import asyncio
import time
from types import SimpleNamespace

import pytest

from services.pressure import web_api as api
from shared.schema import validate_event


def port(name='COM6', serial='board-a', recommended=True):
    return dict(port=name, serial_number=serial, vid=0x1209, pid=0x5741, recommended=recommended)


def test_generic_windows_usb_is_detected_by_usb_id(monkeypatch):
    monkeypatch.setattr(api.list_ports, 'comports', lambda: [SimpleNamespace(
        device='COM12', description='USB Serial Device', manufacturer=None, product=None,
        serial_number='board-a', vid=0x1209, pid=0x5741)])
    assert api.select_device(api.devices())['port'] == 'COM12'


def test_renumbered_port_follows_same_board_and_ignores_other_receivers():
    identity = (0x1209, 0x5741, 'board-a')
    assert api.select_device([port('COM12'), port('COM6', 'other')], identity=identity)['port'] == 'COM12'
    with pytest.raises(ValueError):
        api.select_device([port('COM6', 'other')], identity=identity)
    with pytest.raises(ValueError):
        api.select_device([port(recommended=False)])
    assert api.select_device([port(recommended=False)], 'COM6')['port'] == 'COM6'
    with pytest.raises(ValueError):
        api.select_device([port(), port('COM7', 'other')])


def test_stale_readings_cannot_keep_a_floor_result_or_allow_calibration():
    c = api.PressureController()
    c.stage = 'connected'; c.last_at = time.monotonic() - 5
    c.estimate = {'floor_id': '3', 'status': 'settled'}; c.pressure = 1006.6
    assert c.snapshot()['estimate'] is None
    assert c.snapshot()['pressure_hpa'] is None
    assert not c.snapshot()['can_calibrate']


def test_auto_calibration_waits_for_stable_samples_and_does_not_force_floor_result():
    c = api.PressureController()
    assert not c.ready_to_zero()
    c.stage = 'connected'; c.last_at = time.monotonic()
    for i in range(16): c.estimator.update(i*.2, 100661.7)
    assert c.ready_to_zero(100661.7)
    assert not c.ready_to_zero(100671.7)
    c.zero_on_third_floor()
    assert c.calibration_floor == '3'
    assert c.estimator.delta_pa['3'] == pytest.approx(200.9)
    assert c.estimator.update(3.2, 100661.7).floor_id == '3'
    # The starting baseline is fixed, not all subsequent floor estimates.
    for i in range(50): result = c.estimator.update(3.4 + i*.2, 100726.1)
    assert result.floor_id == '2'
    assert result.status == 'settled'


def test_startup_waits_for_board_and_automatically_recalibrates_after_com_change(monkeypatch):
    async def scenario():
        current_ports = []
        monkeypatch.setattr(api, 'devices', lambda: current_ports)
        instances = []
        class FakeBoard:
            def __init__(self, port, rate_hz):
                self.port = port; self.tick = 0; self.closed = False; self.fail = False
                instances.append(self)
            def connect(self, **kwargs): pass
            def read(self, **kwargs):
                time.sleep(.01)
                if self.fail: raise OSError('unplugged')
                self.tick += 1
                return self.tick*.2, 1006.617, 13
            def close(self): self.closed = True
        monkeypatch.setattr(api, 'BoardClient', FakeBoard)
        c = api.PressureController()
        async def publish(event): validate_event(event)
        c.publisher = publish
        async def until(predicate):
            for _ in range(400):
                if predicate(): return
                await asyncio.sleep(.01)
            raise AssertionError('Timed out waiting for worker state')
        try:
            await c.start()
            await until(lambda: c.stage == 'reconnecting')
            assert not instances
            current_ports[:] = [port()]
            await until(lambda: c.calibration_floor == '3')
            current_ports[:] = [port('COM12')]
            instances[0].fail = True
            await until(lambda: len(instances) == 2 and c.stage == 'connected')
            assert c.port == 'COM12'
            assert c.calibration_floor is None
            assert instances[0].closed
            await until(lambda: c.calibration_floor == '3')
            assert c.snapshot()['estimate']['floor_id'] == '3'
        finally:
            await c.shutdown()
        assert instances[-1].closed
        assert not c.snapshot()['fresh']
    asyncio.run(scenario())
