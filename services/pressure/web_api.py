"""Local Web controls around Anna's USB reader and floor estimator."""
import asyncio
import math
import time
import uuid
from collections import deque
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from serial.tools import list_ports

from shared.config import load_config
from shared.schema import utc_now_iso
from .board import BoardClient
from .floor import FloorEstimator


def devices():
    result = []
    for p in list_ports.comports():
        name = ' '.join(str(getattr(p, k, '') or '') for k in ('manufacturer', 'product', 'description')).lower()
        result.append({'port': p.device, 'description': p.description or p.device,
                       'serial_number': p.serial_number, 'vid': p.vid, 'pid': p.pid,
                       'recommended': ('ardupilot' in name or 'stellarh7' in name
                                       or (p.vid, p.pid) == (0x1209, 0x5741))})
    return result


def select_device(ports, requested=None, identity=None):
    if identity:
        matches = [p for p in ports if (p['vid'], p['pid'], p['serial_number']) == identity]
    elif requested:
        matches = [p for p in ports if p['port'] == requested]
    else:
        matches = [p for p in ports if p['recommended']]
    if len(matches) > 1:
        raise ValueError('Multiple pressure boards found. Select a port explicitly.')
    if not matches:
        raise ValueError('Pressure board not found. Connect it or select its serial port.')
    return matches[0]


class PressureController:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.task = None
        self.stop = asyncio.Event()
        self.publisher = None
        self.session_id = 'web-pressure-' + uuid.uuid4().hex[:12]
        self.sequence = 0
        self.fallback_port = None
        self.requested = None
        self.identity = None
        self.port = None
        self.stage = 'disconnected'
        self.message = 'Waiting for the barometer. Startup calibration uses floor 3.'
        self.history = deque(maxlen=300)
        self.last_at = None
        self.pressure = None
        self.temperature = None
        self.estimate = None
        self.calibration_floor = None
        self.reset_estimator()

    def reset_estimator(self):
        cfg = load_config()['pressure']
        self.estimator = FloorEstimator(cfg['survey'], cfg['pa_per_m'], cfg['dwell_s'], cfg['hysteresis_m'])
        self.estimate = None
        self.calibration_floor = None

    def snapshot(self):
        age = None if self.last_at is None else time.monotonic() - self.last_at
        fresh = self.stage == 'connected' and age is not None and age < 3
        return {'stage': self.stage, 'message': self.message, 'port': self.port,
                'requested_port': self.requested, 'connected': self.stage == 'connected',
                'fresh': fresh, 'sample_age_s': age, 'pressure_hpa': self.pressure if fresh else None,
                'temperature_c': self.temperature if fresh else None,
                'estimate': self.estimate if fresh else None, 'history_hpa': list(self.history),
                'calibration_floor': self.calibration_floor,
                'can_calibrate': fresh and len(self.estimator.window) >= 10
                and self.estimator.window[-1][0] - self.estimator.window[0][0] >= 2.8}

    async def emit(self, kind, payload):
        if self.publisher:
            self.sequence += 1
            await self.publisher({'session_id': self.session_id, 'source': 'pressure', 'mode': 'live',
                                  'type': kind, 'sequence': self.sequence, 'timestamp_utc': utc_now_iso(),
                                  'payload': payload})

    async def status(self, state):
        await self.emit('source.status', {'component': 'barometer', 'state': state, 'detail': self.message})

    async def start(self):
        """Wait for a board even when USB is plugged in after server startup."""
        async with self.lock:
            if self.task and not self.task.done():
                return
            self.stop = asyncio.Event()
            self.identity = None
            self.fallback_port = None
            self.requested = None
            self.stage, self.message = 'connecting', 'Looking for the pressure board…'
            self.task = asyncio.create_task(self.run())

    async def connect(self, requested):
        async with self.lock:
            device = select_device(await asyncio.to_thread(devices), requested)
            await self.close()
            self.requested = requested
            # USB serial number survives a Windows COM-number change. Never switch to a different board.
            self.identity = ((device['vid'], device['pid'], device['serial_number'])
                             if device['serial_number'] else None)
            self.fallback_port = device['port']
            self.stop = asyncio.Event()
            self.history.clear()
            self.last_at = None
            self.reset_estimator()
            self.stage, self.message = 'connecting', 'Connecting to the pressure board…'
            self.task = asyncio.create_task(self.run())

    async def run(self):
        while not self.stop.is_set():
            client = None
            try:
                device = select_device(await asyncio.to_thread(devices), self.fallback_port, self.identity)
                if self.identity is None and device['serial_number']:
                    self.identity = (device['vid'], device['pid'], device['serial_number'])
                self.fallback_port = device['port']
                self.port = device['port']
                client = BoardClient(self.port, rate_hz=5)
                await self.status('starting')
                await asyncio.to_thread(client.connect, timeout=5, settle_s=1.5)
                if self.stop.is_set():
                    break
                self.reset_estimator()
                self.history.clear()
                self.stage, self.message = 'connected', 'Calibrating automatically on floor 3. Keep the board still…'
                await self.status('calibrating')
                previous_time = None
                while not self.stop.is_set():
                    sample = await asyncio.to_thread(client.read, timeout=2)
                    if self.stop.is_set():
                        break
                    if sample is None:
                        raise TimeoutError('No pressure data for 2 seconds.')
                    bt, hpa, temp = sample
                    if not all(math.isfinite(v) for v in sample) or not 300 < hpa < 1200:
                        raise ValueError('Invalid pressure reading.')
                    if previous_time is not None and bt <= previous_time:
                        raise ValueError('Board clock restarted or repeated; reconnecting.')
                    previous_time = bt
                    self.pressure, self.temperature, self.last_at = hpa, temp, time.monotonic()
                    self.history.append(hpa)
                    if self.calibration_floor is None and self.ready_to_zero(hpa * 100):
                        self.zero_on_third_floor()
                        await self.status('ok')
                    self.estimate = asdict(self.estimator.update(bt, hpa * 100))
                    await self.emit('pressure.sample', {'pressure_pa': hpa * 100, 'sensor_timestamp': bt,
                                    'relative_height_m': self.estimate['relative_height_m']})
                    await self.emit('floor.estimate', {**self.estimate, 'reference_floor': self.estimator.reference_floor})
            except Exception as exc:
                self.stage, self.message = 'reconnecting', f'{exc} Waiting for the same board to reconnect.'
                self.last_at = None
                self.reset_estimator()
                await self.status('offline')
            finally:
                if client:
                    await asyncio.to_thread(client.close)
            if not self.stop.is_set():
                try:
                    await asyncio.wait_for(self.stop.wait(), 1)
                except asyncio.TimeoutError:
                    pass

    def ready_to_zero(self, current_pa=None):
        if not self.snapshot()['can_calibrate']:
            return False
        values = [p for _, p in self.estimator.window]
        if current_pa is not None:
            values.append(current_pa)
        return max(values) - min(values) <= 6

    def zero_on_third_floor(self):
        self.estimator.zero_from_window('3')
        self.calibration_floor = '3'
        self.message = 'Automatically calibrated on floor 3. Measuring continuously.'

    async def close(self):
        self.stop.set()
        if self.task:
            await self.task
        self.task = None
        self.port = None
        self.last_at = None
        self.history.clear()
        self.reset_estimator()
        self.stage, self.message = 'disconnected', 'Pressure board disconnected.'
        await self.status('offline')

    async def shutdown(self):
        async with self.lock:
            await self.close()


class Connection(BaseModel):
    port: str | None = None


controller = PressureController()
router = APIRouter(prefix='/pressure', tags=['Pressure measurement'])


@router.get('/devices')
async def inventory():
    return {'devices': await asyncio.to_thread(devices)}


@router.get('/state')
async def state():
    return controller.snapshot()


@router.post('/connect')
async def connect(body: Connection):
    try:
        await controller.connect(body.port)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return controller.snapshot()


@router.post('/disconnect')
async def disconnect():
    await controller.shutdown()
    return controller.snapshot()
