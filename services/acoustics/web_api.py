"""Local measurement sessions around Anna's room-location algorithm (7c4d09d)."""
import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from shared.config import ROOT, DATA_DIR, load_config
from shared.schema import utc_now_iso
from .match import DEFAULT_MATCHING, PositionMeasurement, rank
from .rooms import load_rooms, rooms_on_floor


def devices():
    import sounddevice as sd
    apis = sd.query_hostapis()
    all_devices = sd.query_devices()
    def entries(kind):
        key = 'max_' + kind + '_channels'
        return [{'id': i, 'name': d['name'], 'api': apis[d['hostapi']]['name']}
                for i, d in enumerate(all_devices) if d[key] > 0
                and (sys.platform != 'win32' or apis[d['hostapi']]['name'] == 'Windows WASAPI')]
    ins, outs = entries('input'), entries('output')
    def preferred(items, index):
        default = sd.default.device[index]
        name = all_devices[default]['name'] if default >= 0 else None
        return next((d['id'] for d in items if d['name'] == name), items[0]['id'] if items else None)
    return {'inputs': ins, 'outputs': outs, 'default_input': preferred(ins, 0), 'default_output': preferred(outs, 1)}


def quality(data):
    m = data['measurement']
    checks = data['info'].get('capture_checks', [data['info']])
    reasons = []
    if any(c.get('clipped') for c in checks): reasons.append('Recording clipped. Lower the playback gain.')
    if any(c.get('too_quiet') for c in checks): reasons.append('Recording too quiet. Check the microphone and audio processing.')
    if m.get('snr_db') is None or m['snr_db'] < 40: reasons.append('Signal-to-noise ratio below 40 dB.')
    if not m.get('rt60_s'): reasons.append('No usable reverberation decay was found.')
    return reasons


def capture_process(job, cancelled, notify):
    proc = subprocess.Popen([sys.executable, '-u', '-m', 'services.acoustics.web_worker', str(job)],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace',
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    lines = queue.Queue()
    def read():
        for line in proc.stdout: lines.put(line)
        lines.put(None)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    deadline, error = time.monotonic()+90, None
    try:
        while True:
            if cancelled.is_set(): raise RuntimeError('Measurement cancelled.')
            if time.monotonic() > deadline: raise RuntimeError('Audio capture timed out. Check the devices.')
            try: line = lines.get(timeout=.1)
            except queue.Empty: continue
            if line is None: break
            try: event = json.loads(line)
            except ValueError: continue
            if 'error' in event: error = event['error']
            if 'progress' in event: notify(event['progress'])
        if cancelled.is_set(): raise RuntimeError('Measurement cancelled.')
        if proc.wait(timeout=5) != 0: raise RuntimeError(error or 'Audio capture failed. Check the selected devices.')
        return json.loads(job.with_suffix('.result.json').read_text(encoding='utf-8'))
    finally:
        if proc.poll() is None: proc.kill()
        proc.wait()
        reader.join(2)
        proc.stdout.close()


class Settings(BaseModel):
    floor_id: Literal['0', '1', '2', '3'] | None = None


class Capture(Settings):
    input_id: int = Field(ge=0)
    output_id: int = Field(ge=0)
    mic_height_m: float = Field(default=.75, ge=.1, le=2.5, allow_inf_nan=False)
    speaker_mic_m: float = Field(default=.1, ge=.01, le=1, allow_inf_nan=False)
    gain: float = Field(default=.1, ge=.01, le=.3, allow_inf_nan=False)
    new_position: bool = False


class Session:
    def __init__(self):
        self.session_id = uuid.uuid4().hex[:12]
        self.floor_id = '3'
        self.accepted = []
        self.last = None
        self.stage = 'idle'
        self.message = 'Select a floor or search all floors, then measure your first position.'
        self.progress = 0
        self.result = None
        self.task = None
        self.cancelled = threading.Event()
        self.lock = asyncio.Lock()
        self.publisher = None
        self.sequence = 0
        self.rooms = load_rooms()
        self.matching = {**DEFAULT_MATCHING, **load_config()['echolocation'].get('matching', {})}

    def available(self):
        if self.stage in ('measuring', 'cancelling', 'plotting'):
            raise HTTPException(409, 'A measurement is already running. Wait or cancel it first.')

    def rerank(self):
        ps = []
        for data in self.accepted:
            m = data['measurement']
            ps.append(PositionMeasurement(m['measurement_id'], m['rt60_s'], m['reflection_distances_m'],
                                         data['mic_height_m'], m['position_label'],
                                         [r['strength_db'] for r in m['reflections']]))
        result = rank(ps, rooms_on_floor(self.rooms, self.floor_id), self.matching)
        if self.floor_id is None and result['status'] == 'supported': result['status'] = 'candidate'
        lookup = {r.room_id: r for r in self.rooms}
        for c in result['candidates']: c['floor_ids'] = lookup[c['room_id']].floor_ids
        result.update(floor_id=self.floor_id, floor_source='manual')
        self.result = result

    def plot_reference(self):
        result = self.result or {}
        candidates = result.get('candidates', [])
        if result.get('status') not in ('supported', 'candidate', 'ambiguous') or not candidates:
            return {'ceiling_height_m': None, 'room_id': None, 'label': None}
        room = next((r for r in self.rooms if r.room_id == candidates[0]['room_id']), None)
        if room is None:
            return {'ceiling_height_m': None, 'room_id': None, 'label': None}
        return {'ceiling_height_m': room.ceiling_height_m, 'room_id': room.room_id, 'label': room.label}

    async def refresh_plots(self):
        """Annotate only after ranking; the reference is never a matcher input."""
        if not self.last or not self.last.get('recording_dir'):
            return
        directory = (ROOT / self.last['recording_dir']).resolve()
        session_dir = (DATA_DIR / 'echo' / ('web-' + self.session_id)).resolve()
        if directory.parent != session_dir or not directory.is_dir():
            self.last['plot_error'] = 'This session has no saved recording directory.'
            return
        previous_stage, previous_message = self.stage, self.message
        self.stage, self.message = 'plotting', 'Updating figures from the room ranking…'
        proc = None
        try:
            (session_dir / 'plot_reference.json').write_text(json.dumps(self.plot_reference()), encoding='utf-8')
            proc = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'services.acoustics.web_plots', str(directory), cwd=ROOT,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            await asyncio.wait_for(proc.communicate(), timeout=45)
            if proc.returncode != 0:
                raise RuntimeError('Figure generation failed.')
            manifest = ROOT / 'web' / 'acoustic-plots' / session_dir.name / directory.name / 'manifest.json'
            self.last['plot_revision'] = json.loads(manifest.read_text(encoding='utf-8'))['revision']
            self.last.pop('plot_error', None)
        except Exception as exc:
            self.last['plot_error'] = str(exc) or 'Figure generation timed out.'
        finally:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            self.stage, self.message = previous_stage, previous_message

    def snapshot(self):
        return {'stage': self.stage, 'message': self.message, 'progress': self.progress,
                'floor_id': self.floor_id, 'session_id': self.session_id, 'mode': 'live',
                'settings': self.accepted[0]['settings'] if self.accepted else None,
                'positions': [{'label': d['measurement']['position_label'], 'rt60_s': d['measurement']['rt60_s'],
                               'snr_db': d['measurement']['snr_db']} for d in self.accepted],
                'last': self.last, 'result': self.result}

    async def publish(self, kind, payload):
        if self.publisher:
            self.sequence += 1
            await self.publisher({'session_id': 'web-acoustics-'+self.session_id, 'source': 'acoustics',
                                  'type': kind, 'mode': 'live', 'timestamp_utc': utc_now_iso(),
                                  'sequence': self.sequence, 'payload': payload})

    async def start(self, body):
        self.available()
        async with self.lock:
            self.available()
            if self.accepted and not body.new_position:
                raise HTTPException(422, 'Confirm that you moved to a different position before adding it.')
            if len(self.accepted) >= 8:
                raise HTTPException(409, 'Eight positions recorded. Start a new session to measure another room.')
            inventory = await asyncio.to_thread(devices)
            inp = next((d for d in inventory['inputs'] if d['id'] == body.input_id), None)
            out = next((d for d in inventory['outputs'] if d['id'] == body.output_id), None)
            if not inp or not out or inp['api'] != out['api']:
                raise HTTPException(422, 'Choose an available microphone and speaker on the same audio interface.')
            # Do not combine recordings made with different devices or speaker/mic geometry.
            if self.accepted:
                previous = self.accepted[0]['settings']
                if any(previous[k] != v for k,v in [('input',inp),('output',out),('gain',body.gain),
                                                   ('mic_height_m',body.mic_height_m),('speaker_mic_m',body.speaker_mic_m)]):
                    raise HTTPException(409, 'Audio settings changed. Start a new session before measuring.')
            self.floor_id = body.floor_id
            self.rerank()
            settings = {'input': inp, 'output': out, 'gain': body.gain, 'mic_height_m': body.mic_height_m,
                        'speaker_mic_m': body.speaker_mic_m, 'position': f'P{len(self.accepted)+1}',
                        'session': self.session_id}
            folder = DATA_DIR / 'echo-web-jobs'
            folder.mkdir(parents=True, exist_ok=True)
            job = folder / (uuid.uuid4().hex + '.json')
            job.write_text(json.dumps(settings), encoding='utf-8')
            self.cancelled = threading.Event()
            self.stage, self.progress = 'measuring', 0
            self.message = f"Measuring {settings['position']}. Keep the laptop still; three short sweeps will play."
            self.task = asyncio.create_task(self.run(job))

    async def run(self, job):
        try:
            loop = asyncio.get_running_loop()
            data = await asyncio.to_thread(capture_process, job, self.cancelled,
                                          lambda n: loop.call_soon_threadsafe(self.set_progress, n))
            if self.cancelled.is_set(): raise RuntimeError('Measurement cancelled.')
            data['quality_issues'] = quality(data)
            self.last = data
            self.progress = 3
            if data['quality_issues']:
                self.stage = 'rejected'
                self.message = 'Recording excluded from ranking. ' + ' '.join(data['quality_issues'])
                await self.refresh_plots()
                return
            self.accepted.append(data)
            self.rerank()
            self.stage = 'ready'
            self.message = f"{len(self.accepted)} position(s) measured. Move to another position to add evidence."
            await self.refresh_plots()
            await self.publish('acoustic.measurement', data['measurement'])
            await self.publish('room.estimate', self.result)
        except Exception as exc:
            self.stage = 'cancelled' if self.cancelled.is_set() else 'error'
            self.message = str(exc)

    def set_progress(self, n):
        self.progress = n
        if self.stage == 'measuring': self.message = f'Sweep {n+1} of 3 — keep the laptop still.'

    async def shutdown(self):
        self.cancelled.set()
        if self.task: await self.task


controller = Session()
router = APIRouter(prefix='/acoustics', tags=['Room measurement'])

@router.get('/devices')
async def audio_devices():
    controller.available()
    try: return await asyncio.to_thread(devices)
    except Exception as exc: raise HTTPException(503, str(exc))

@router.get('/state')
async def state(): return controller.snapshot()

@router.post('/measure')
async def measure(body: Capture):
    await controller.start(body)
    return controller.snapshot()

@router.post('/floor')
async def floor(body: Settings):
    controller.available()
    async with controller.lock:
        controller.available()
        controller.floor_id = body.floor_id
        controller.rerank()
        await controller.refresh_plots()
        await controller.publish('room.estimate', controller.result)
        return controller.snapshot()

@router.post('/cancel')
async def cancel():
    if controller.stage == 'measuring':
        controller.stage = 'cancelling'
        controller.message = 'Stopping playback and recording…'
        controller.cancelled.set()
    return controller.snapshot()


@router.post('/reset')
async def reset():
    controller.available()
    async with controller.lock:
        controller.available()
        controller.accepted = []
        controller.last = None
        controller.session_id = uuid.uuid4().hex[:12]
        controller.stage, controller.progress = 'idle', 0
        controller.message = 'New session. Previous recordings remain saved locally.'
        controller.rerank()
        await controller.publish('room.estimate', controller.result)
        return controller.snapshot()
