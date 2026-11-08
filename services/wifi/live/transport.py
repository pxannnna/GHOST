"""USB discovery and serial I/O stay off the GUI thread."""
import queue
import threading
import time

import serial
from serial.tools import list_ports

from .protocol import parse


def candidates(ports):
    return [p for p in ports if (p.vid, p.pid) == (0x303A, 0x1001)]


def identity(port):
    return port.serial_number or port.location or port.device


class SerialWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.events = queue.Queue()
        self.commands = queue.Queue()
        self.stopping = threading.Event()
        self.selected = None
        self.remembered = None
        self.port = None
        self.training_requested = False
        self.pending = b''
        self.next_scan = self.next_status = 0

    def emit(self, kind, value=None):
        self.events.put((kind, value))

    def send(self, command):
        self.commands.put(('send', command))

    def close_port(self):
        if self.port is not None:
            self.port.close()
            self.port = None
        self.pending = b''

    def write(self, command):
        if self.port is None:
            raise RuntimeError('No USB device is connected.')
        self.port.write((command+'\r\n').encode('utf-8'))
        if command == 'radar --train_start':
            self.training_requested = True
        elif command == 'radar --train_stop':
            self.training_requested = False

    def discover(self, now):
        ports = candidates(list_ports.comports())
        self.emit('devices', [p.device for p in ports])
        if self.port is not None:
            return
        matching = [p for p in ports if p.device == self.selected] if self.selected else ports
        if not self.selected and self.remembered:
            matching = [p for p in matching if identity(p) == self.remembered]
        if len(matching) != 1:
            self.emit('discovery', 'Select a device: multiple supported USB devices found.' if len(matching)>1
                      else 'Waiting for a supported ESP32 USB device (303A:1001).')
            return
        chosen = matching[0]
        port = serial.Serial(port=None, baudrate=115200, timeout=.05, write_timeout=.5)
        port.dtr = port.rts = False
        port.port = chosen.device
        port.open()
        self.port = port
        self.remembered = identity(chosen)
        # Follow this physical board if Windows assigns it a different COM port.
        self.selected = None
        self.port.reset_input_buffer()
        self.next_status = now
        self.emit('opened', chosen.device)

    def run(self):
        try:
            while not self.stopping.is_set():
                try:
                    while not self.commands.empty():
                        kind, value = self.commands.get_nowait()
                        if kind == 'select':
                            if self.training_requested and self.port:
                                self.write('radar --train_stop')
                            self.close_port()
                            self.selected = value
                            self.remembered = None
                            self.next_scan = 0
                            self.emit('closed')
                        elif kind == 'send':
                            self.write(value)
                    now = time.monotonic()
                    if now >= self.next_scan:
                        self.next_scan = now+1.5
                        self.discover(now)
                    if self.port is not None:
                        if now >= self.next_status:
                            self.write('ghost_status')
                            self.next_status = now+2
                        data = self.port.read(min(16384, max(1, self.port.in_waiting)))
                        if data:
                            self.emit('serial_alive', now)
                            lines = (self.pending+data).split(b'\n')
                            self.pending = lines.pop()[-16384:]
                            for raw in lines:
                                line = raw.decode('utf-8', errors='replace')
                                parsed = parse(line)
                                if parsed:
                                    self.emit(*parsed)
                                elif 'Timestamp delta out of range' in line:
                                    self.emit('window_reset')
                                elif 'ESP-ROM:' in line or 'rst:' in line:
                                    self.emit('reboot')
                                elif 'Wi-Fi disconnected' in line:
                                    self.emit('wifi_lost')
                    else:
                        self.stopping.wait(.1)
                except (OSError, RuntimeError, ValueError, serial.SerialException) as exc:
                    self.close_port()
                    self.next_scan = time.monotonic()+3
                    self.emit('connection_error', str(exc))
                    self.stopping.wait(.2)
        finally:
            if self.training_requested and self.port:
                try:
                    self.write('radar --train_stop')
                except (OSError, RuntimeError, serial.SerialException):
                    pass
            self.close_port()
