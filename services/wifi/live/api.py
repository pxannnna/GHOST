"""Local browser adapter; official firmware owns motion decisions.

Wire parser and serial transport originate from GHOST_csi 290ac0a.
Calibration is followed by continuous detection, without timed trials.
"""
import asyncio
from collections import deque
import math
import queue
import time
from dataclasses import asdict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .protocol import Pulse, wifi_command
from .transport import SerialWorker
from .transport import candidates, identity
from serial.tools import list_ports
from . import firmware

CALIBRATION = {'await_start', 'calibrating', 'await_stop', 'wait_status', 'settling'}

class MotionSession:
    def __init__(self):
        self.stage = 'idle'
        self.deadline = 0
        self.threshold = None
        self.status = None
        self.status_at = None
        self.report = None
        self.report_at = None
        self.device_ms = None
        self.status_ms = None
        self.port = None
        self.opened_at = None
        self.ports = []
        self.trace = deque(maxlen=1800)
        self.pulse = Pulse()
        self.message = 'Connect the receiver to begin.'
        self.commands = []

    def send(self, command):
        self.commands.append(command)

    def fail(self, message):
        if self.stage in CALIBRATION:
            self.send('radar --train_stop')
        self.stage = 'error'
        self.threshold = None
        self.pulse.invalidate()
        self.message = message

    def healthy(self, now):
        return bool(self.port and self.status and self.status.compatible and self.status.wifi
                    and self.status_at is not None and now-self.status_at < 7)

    def fresh(self, now):
        return self.report_at is not None and now-self.report_at < 2

    def calibrate(self, now):
        if self.stage in CALIBRATION:
            raise ValueError('Calibration is already running.')
        if not self.healthy(now) or not self.fresh(now):
            raise ValueError('Connect the hotspot and wait for fresh radar data before calibration.')
        self.threshold = None
        self.trace.clear()
        self.pulse = Pulse()
        self.stage = 'await_start'
        self.deadline = now+5
        self.message = 'Starting calibration. Keep the devices fixed and the area still.'
        self.send('radar --train_start')

    def stop(self):
        if self.stage in CALIBRATION:
            self.send('radar --train_stop')
        self.stage = 'idle'
        self.threshold = None
        self.pulse.invalidate()
        self.trace.clear()
        self.message = 'Detection stopped. Calibrate to start again.'

    def event(self, kind, value, now):
        if kind == 'devices':
            self.ports = value
        elif kind == 'opened':
            self.port = value
            self.opened_at = now
            self.status = None
            self.status_at = self.report_at = None
            self.status_ms = self.device_ms = None
            self.message = 'Receiver connected. Checking firmware.'
        elif kind == 'discovery' and not self.port:
            self.message = value
        elif kind in ('closed', 'connection_error'):
            self.port = None
            self.status = None
            self.report_at = None
            self.fail('Receiver unavailable. Close the standalone CSI app or other serial monitor, then reconnect.')
        elif kind in ('wifi_lost', 'reboot'):
            self.status = None
            self.report_at = None
            self.fail('Connection changed. Reconnect and calibrate again.')
        elif kind == 'status':
            if self.status_ms is not None and value.uptime_ms < self.status_ms:
                self.fail('Receiver restarted. Calibrate again.')
            self.status_ms = value.uptime_ms
            self.status = value
            self.status_at = now
            if not value.compatible:
                self.fail('Compatible GHOST CSI firmware required. Open Device & hotspot to install it.')
                return
            if not value.wifi:
                if self.stage in CALIBRATION or self.stage == 'detecting':
                    self.fail('Hotspot disconnected. Reconnect and calibrate again.')
                else:
                    self.message = 'Firmware verified. Connect your 2.4 GHz hotspot.'
                return
            if self.stage == 'wait_status' and value.calibrated and not value.training:
                if min(value.motion_threshold, value.presence_threshold) <= 0:
                    self.fail('Calibration returned invalid reference values. Please retry.')
                else:
                    self.threshold = value.motion_threshold
                    self.stage = 'settling'
                    self.deadline = now+3
                    self.message = 'Calibration complete. Waiting for fresh detector reports.'
            elif self.stage == 'idle':
                self.message = 'Hotspot connected. Ready to calibrate.'
        elif kind == 'report' and self.status and self.status.compatible:
            if self.device_ms is not None and value.device_ms < self.device_ms:
                self.fail('Device clock restarted. Calibrate again.')
            self.device_ms = value.device_ms
            self.report, self.report_at = value, now
            self.trace.append((now, .2*value.jitter, value.jitter_median))
            if self.stage == 'detecting' and self.healthy(now):
                self.pulse.update(value.motion, now)
        elif kind == 'training' and self.stage in CALIBRATION:
            event, code = value
            if event == 'ERROR' or code:
                self.fail('Calibration failed. Keep the area still and retry.')
            elif event == 'STARTED' and self.stage == 'await_start':
                self.stage = 'calibrating'
                self.deadline = now+30
                self.message = 'Calibrating. Keep both devices fixed and avoid movement nearby.'
            elif event == 'DONE' and self.stage == 'await_stop':
                self.stage = 'wait_status'
                self.deadline = now+6
                self.send('ghost_status')

    def tick(self, now):
        if self.port and self.status is None and self.opened_at is not None and now-self.opened_at > 8:
            self.message = 'No firmware response. Try Restart receiver first; reinstall only if needed.'
        if self.stage in CALIBRATION or self.stage == 'detecting':
            if not self.healthy(now):
                self.fail('Receiver status lost. Reconnect and calibrate again.')
                return
        if not self.fresh(now):
            self.pulse.invalidate()
        if now < self.deadline:
            return
        if self.stage == 'calibrating':
            self.stage = 'await_stop'
            self.deadline = now+6
            self.send('radar --train_stop')
            self.message = 'Finishing calibration.'
        elif self.stage in ('await_start', 'await_stop', 'wait_status'):
            self.fail('Calibration acknowledgement timed out. Check the connection and retry.')
        elif self.stage == 'settling':
            if self.fresh(now):
                self.stage = 'detecting'
                self.message = 'Continuous motion detection is active.'
                self.pulse = Pulse()
            elif now > self.deadline+10:
                self.fail('No radar data after calibration. Check the hotspot.')

    def snapshot(self, now):
        ready = self.healthy(now)
        fresh = ready and self.fresh(now)
        detecting = self.stage == 'detecting' and self.threshold is not None
        return {'mode': 'live', 'stage': self.stage, 'port': self.port, 'ports': self.ports,
                'compatible': bool(self.status and self.status.compatible),
                'firmware_unresponsive': bool(self.port and self.status is None and self.opened_at is not None and now-self.opened_at > 8),
                'wifi': bool(self.status and self.status.wifi), 'fresh': fresh,
                'message': self.message, 'threshold': self.threshold,
                'calibration_remaining_s': max(0, math.ceil(self.deadline-now)) if self.stage == 'calibrating' else None,
                'calibration_progress': max(0, min(1, 1-(self.deadline-now)/30)) if self.stage == 'calibrating' else None,
                'can_calibrate': ready and fresh and self.stage not in CALIBRATION,
                'green': bool(detecting and fresh and now < self.pulse.until),
                'motion': self.report.motion if detecting and fresh else None,
                'pulses': self.pulse.count, 'age_s': round(now-self.report_at, 2) if self.report_at is not None else None,
                'report': asdict(self.report) if fresh and self.report else None,
                'trace': [[round(t-now, 3), jitter, median] for t,jitter,median in self.trace if 0 <= now-t < 15] if self.threshold else []}

class Controller:
    def __init__(self):
        self.session = MotionSession()
        self.worker = None
        self.task = None
        self.lock = asyncio.Lock()
        self.maintenance_task = None
        self.maintenance = {'status': 'idle', 'action': None, 'port': None, 'message': '', 'logs': []}
        self.package = firmware.package_info()

    def ensure_available(self):
        if self.maintenance['status'] == 'running':
            raise HTTPException(409, 'Receiver maintenance is in progress. Wait for it to finish.')

    def start_worker(self, port=None, remembered=None):
        self.session = MotionSession()
        self.worker = SerialWorker()
        self.worker.selected = port
        self.worker.remembered = remembered
        self.worker.start()
        self.task = asyncio.create_task(self.run())

    async def connect(self, port):
        self.ensure_available()
        async with self.lock:
            self.ensure_available()
            await self.close()
            self.start_worker(port)

    async def maintain(self, action, port):
        self.ensure_available()
        async with self.lock:
            self.ensure_available()
            if self.session.stage in CALIBRATION or self.session.stage == 'detecting':
                raise HTTPException(409, 'Stop calibration or detection before receiver maintenance.')
            supported = await asyncio.to_thread(lambda: candidates(list_ports.comports()))
            target = port or self.session.port
            matches = [p for p in supported if p.device == target] if target else supported
            if len(matches) != 1:
                raise HTTPException(409, 'Select one connected ESP32-C6 receiver before continuing.')
            if action == 'install':
                self.package = await asyncio.to_thread(firmware.package_info)
                if not self.package['available']:
                    raise HTTPException(409, self.package['message'])
            chosen = matches[0]
            self.maintenance = {'status': 'running', 'action': action, 'port': chosen.device,
                                'message': 'Releasing the receiver port…', 'logs': []}
            self.maintenance_task = asyncio.create_task(self.run_maintenance(action, chosen.device, identity(chosen)))

    async def run_maintenance(self, action, port, remembered):
        async with self.lock:
            try:
                await self.close()
                if action == 'install':
                    self.maintenance['message'] = 'Installing firmware. Keep the receiver plugged in.'
                    loop = asyncio.get_running_loop()
                    await asyncio.to_thread(firmware.install, port,
                                            lambda line: loop.call_soon_threadsafe(self.progress, line))
                else:
                    self.maintenance['message'] = 'Restarting the receiver. Firmware is unchanged.'
                    await asyncio.to_thread(firmware.restart, port)
                self.maintenance['message'] = 'Reconnecting and verifying firmware…'
                self.start_worker(remembered=remembered)
                for _ in range(80):
                    await asyncio.sleep(.25)
                    if self.session.status and self.session.status.compatible:
                        self.maintenance.update(status='success', message=
                            ('Firmware installed and verified.' if action == 'install' else 'Receiver restarted; existing firmware verified.')
                            + ' Connect the hotspot and calibrate again.')
                        return
                raise RuntimeError('No firmware response after reconnecting. Check USB and try Restart receiver.')
            except Exception as exc:
                self.maintenance.update(status='error', message=str(exc))

    def progress(self, line):
        self.maintenance['logs'] = (self.maintenance['logs'] + [line])[-12:]

    async def shutdown(self):
        # Do not cancel a firmware write during a normal server shutdown.
        if self.maintenance_task:
            await self.maintenance_task
        await self.close()

    async def close(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        if self.worker:
            self.worker.stopping.set()
            await asyncio.to_thread(self.worker.join, 2)
            self.worker = None
        self.session = MotionSession()

    async def run(self):
        while True:
            now = time.monotonic()
            for _ in range(1000):
                try:
                    kind,value = self.worker.events.get_nowait()
                except queue.Empty:
                    break
                self.session.event(kind,value,now)
            self.session.tick(now)
            commands,self.session.commands = self.session.commands,[]
            for command in commands:
                self.worker.send(command)
            await asyncio.sleep(.04)

controller = Controller()
router = APIRouter(prefix='/wifi', tags=['Wi-Fi motion'])

class Device(BaseModel):
    port: str | None = Field(default=None, pattern=r'^COM[0-9]+$')
class Hotspot(BaseModel):
    ssid: str
    password: str
class Calibration(BaseModel):
    confirmed: bool = Field(strict=True)
class Installation(Device):
    confirmed: bool = Field(strict=True)

@router.get('/state')
async def state():
    result = controller.session.snapshot(time.monotonic())
    result['connected'] = controller.worker is not None
    result['firmware_package'] = controller.package
    result['maintenance'] = controller.maintenance
    return result

@router.post('/device')
async def device(body: Device):
    await controller.connect(body.port)
    return await state()

@router.post('/disconnect')
async def disconnect():
    controller.ensure_available()
    async with controller.lock:
        controller.ensure_available()
        await controller.close()
    return await state()

@router.post('/hotspot')
async def hotspot(body: Hotspot):
    controller.ensure_available()
    s=controller.session
    if not controller.worker or not s.status or not s.status.compatible or s.stage in CALIBRATION or s.stage == 'detecting':
        raise HTTPException(409, 'Connect a compatible receiver and stop detection before changing the hotspot.')
    try:
        command=wifi_command(body.ssid,body.password)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    controller.worker.send(command)
    return {'accepted': True}

@router.post('/calibrate')
async def calibrate(body: Calibration):
    controller.ensure_available()
    if not body.confirmed:
        raise HTTPException(422,'Confirm that the devices are fixed and the area is still.')
    try:
        controller.session.calibrate(time.monotonic())
    except ValueError as exc:
        raise HTTPException(409,str(exc))
    return await state()

@router.post('/stop')
async def stop():
    controller.ensure_available()
    controller.session.stop()
    return await state()

@router.post('/restart')
async def restart(body: Device):
    await controller.maintain('restart', body.port)
    return await state()

@router.post('/firmware')
async def install_firmware(body: Installation):
    if not body.confirmed:
        raise HTTPException(422, 'Confirm replacement of the selected receiver firmware.')
    await controller.maintain('install', body.port)
    return await state()
