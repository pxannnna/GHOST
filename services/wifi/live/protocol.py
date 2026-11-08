"""Parse the actual wire format, not the upstream console's outdated header."""
from dataclasses import asdict, dataclass
import math
import re

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
FIRMWARE_ID = 'ghost-radar-1'
PROTOCOL = 1


@dataclass
class Report:
    sequence: int
    device_ms: int
    wander: float
    wander_average: float
    presence_threshold_scaled: float
    presence: int
    jitter: float
    jitter_median: float
    rolling_motion_reference: float
    motion: int

    def values(self):
        return asdict(self)


@dataclass
class Status:
    protocol: int
    firmware: str
    uptime_ms: int
    wifi: bool
    training: bool
    calibrated: bool
    presence_threshold: float
    motion_threshold: float

    @property
    def compatible(self):
        return self.protocol == PROTOCOL and self.firmware == FIRMWARE_ID


def parse(line):
    """Return (kind, value) or None. Nine-field training rows are not reports."""
    line = ANSI.sub('', line)
    for marker in ('GHOST_STATUS,', 'GHOST_TRAIN,', 'RADAR_DADA,'):
        if marker not in line:
            continue
        fields = line[line.index(marker):].strip().split(',')
        try:
            if marker == 'RADAR_DADA,' and len(fields) == 11:
                vals = [float(v) for v in fields[1:]]
                if not all(math.isfinite(v) for v in vals):
                    return None
                if fields[6] not in ('0','1') or fields[10] not in ('0','1'):
                    return None
                return 'report', Report(int(fields[1]),int(fields[2]),*vals[2:5],
                                        int(fields[6]),*vals[6:9],int(fields[10]))
            if marker == 'GHOST_STATUS,' and len(fields) == 9:
                if any(v not in ('0','1') for v in fields[4:7]):
                    return None
                thresholds = [float(v) for v in fields[7:9]]
                if not all(math.isfinite(v) and v >= 0 for v in thresholds):
                    return None
                return 'status', Status(int(fields[1]), fields[2], int(fields[3]),
                                        *(v=='1' for v in fields[4:7]), *thresholds)
            if marker == 'GHOST_TRAIN,' and len(fields) == 3:
                return 'training', (fields[1], int(fields[2]))
        except (ValueError, OverflowError):
            return None
    return None


def quote_argument(value):
    # Espressif's console supports quoted strings, but control characters must
    # never become extra commands. Restrict ambiguous escapes at the boundary.
    if any(ord(c) < 32 or c in '\\"' for c in value):
        raise ValueError('Hotspot names/passwords cannot contain quotes, backslashes or control characters in this demo.')
    return '"'+value+'"'


def wifi_command(ssid, password):
    if not 1 <= len(ssid.encode('utf-8')) <= 32:
        raise ValueError('SSID must contain 1 to 32 UTF-8 bytes.')
    if not 8 <= len(password.encode('utf-8')) <= 63:
        raise ValueError('Use a WPA2 hotspot password of 8 to 63 UTF-8 bytes.')
    return 'wifi_config --ssid '+quote_argument(ssid)+' --password '+quote_argument(password)


class Pulse:
    """A new positive episode lights for one second, without extending it."""
    def __init__(self):
        self.previous = False
        self.until = 0.0
        self.count = 0

    def update(self, motion, now):
        rising = bool(motion) and not self.previous
        self.previous = bool(motion)
        if rising and now >= self.until:
            self.until = now + 1
            self.count += 1
            return True
        return False

    def invalidate(self):
        self.previous = False
        self.until = 0
