"""Clock-driven experiment workflow. No sleeps, serial access or GUI calls."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Timing:
    countdown: float = 5
    calibration: float = 30
    recording: float = 60
    settling: float = 3


class Experiment:
    def __init__(self, timing=None):
        self.timing = timing or Timing()
        self.stage = 'idle'
        self.deadline = 0
        self.actions = []
        self.rows = {'empty': [], 'walking': []}
        self.last_report = None
        self.last_device_ms = None
        self.last_status_ms = None
        self.thresholds = None
        self.error = ''
        self.record_start = 0

    def enter(self, stage, now, duration=0):
        self.stage, self.deadline = stage, now+duration
        self.actions.append(('phase', stage))

    def command(self, command):
        self.actions.append(('command', command))

    def drain(self):
        actions, self.actions = self.actions, []
        return actions

    def start_empty(self, now):
        if self.stage not in ('idle','error','complete'):
            raise ValueError('Finish or stop the current experiment first.')
        self.rows = {'empty': [], 'walking': []}
        self.thresholds = None
        self.error = ''
        self.enter('countdown_empty', now, self.timing.countdown)

    def start_walking(self, now):
        if self.stage != 'waiting_walk':
            raise ValueError('An empty-room recording is required first.')
        self.enter('countdown_walk', now, self.timing.countdown)

    def abort(self, message, now):
        if self.stage in ('await_start','calibrating','await_stop','wait_status'):
            self.command('radar --train_stop')
        self.error = message
        self.thresholds = None
        self.enter('error', now)

    def on_training(self, value, now):
        event, code = value
        if self.stage not in ('await_start','calibrating','await_stop','wait_status'):
            return
        if event == 'ERROR' or code != 0:
            self.abort('Firmware calibration failed. Keep the area empty and retry.', now)
        elif event == 'STARTED' and self.stage == 'await_start':
            self.enter('calibrating', now, self.timing.calibration)
        elif event == 'DONE' and self.stage == 'await_stop':
            self.enter('wait_status', now, 6)
            self.command('ghost_status')

    def on_status(self, status, now):
        if self.last_status_ms is not None and status.uptime_ms < self.last_status_ms:
            self.abort('Board restarted. Reconnect the hotspot and recalibrate.', now)
        self.last_status_ms = status.uptime_ms
        if self.stage == 'wait_status' and status.calibrated and not status.training:
            if min(status.presence_threshold, status.motion_threshold) <= 0:
                self.abort('Calibration produced zero thresholds; collect a new baseline.', now)
                return
            self.thresholds = {'presence': status.presence_threshold, 'motion': status.motion_threshold}
            self.enter('settling', now, self.timing.settling)
        if not status.wifi and self.stage not in ('idle','error'):
            self.abort('Hotspot disconnected. Reconnect and restart calibration.', now)

    def on_report(self, report, now):
        if self.last_device_ms is not None and report.device_ms < self.last_device_ms:
            self.abort('Device clock restarted. Recalibration is required.', now)
        self.last_device_ms = report.device_ms
        self.last_report = now
        if self.stage in self.rows:
            row = {'host_elapsed_s': now-self.record_start, **report.values()}
            self.rows[self.stage].append(row)
            self.actions.append(('row', (self.stage, row)))

    def tick(self, now):
        if now < self.deadline:
            return
        if self.stage == 'countdown_empty':
            self.command('radar --train_start')
            self.enter('await_start', now, 5)
        elif self.stage == 'calibrating':
            self.command('radar --train_stop')
            self.enter('await_stop', now, 6)
        elif self.stage in ('await_start','await_stop','wait_status'):
            self.abort('No calibration acknowledgement. Check the connection and retry.', now)
        elif self.stage == 'settling':
            if self.last_report is not None and now-self.last_report < 2:
                self.record_start = now
                self.enter('empty', now, self.timing.recording)
            elif now > self.deadline+10:
                self.abort('No radar results after calibration. Check the hotspot.', now)
        elif self.stage == 'empty':
            if len(self.rows['empty']) < 2:
                self.abort('No usable empty-room recording. Please retry.', now)
            else:
                self.enter('waiting_walk', now)
        elif self.stage == 'countdown_walk':
            if self.last_report is None or now-self.last_report > 2:
                self.abort('Radar results are stale. Restart the experiment after recovery.', now)
            else:
                self.record_start = now
                self.enter('walking', now, self.timing.recording)
        elif self.stage == 'walking':
            if len(self.rows['walking']) < 2:
                self.abort('No usable walking recording. Restart the experiment.', now)
            else:
                self.enter('complete', now)
