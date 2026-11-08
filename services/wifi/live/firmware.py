"""Local, checksummed ESP32-C6 firmware installation and reset-only recovery."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

import serial

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path(os.environ.get('GHOST_FIRMWARE_MANIFEST',
                              ROOT / 'firmware/xiao/.artifacts/manifest.json'))


def flash_args(manifest=MANIFEST):
    """Validate all images before opening a serial port or starting esptool."""
    manifest = Path(manifest)
    spec = json.loads(manifest.read_text(encoding='utf-8'))
    if (spec.get('target'), spec.get('firmware_id'), spec.get('protocol')) != ('esp32c6', 'ghost-radar-1', 1):
        raise ValueError('A GHOST ESP32-C6 protocol 1 firmware package is required.')
    if (spec.get('flash_mode'), spec.get('flash_freq'), spec.get('flash_size')) != ('dio', '80m', '4MB'):
        raise ValueError('Unsupported firmware flash configuration.')
    # Only these partition locations are part of the tested package. Keep NVS intact.
    limits = {0x0: 0x8000, 0x8000: 0x9000, 0x1d000: 0x1f000, 0x20000: 0x1ea000}
    seen, result = set(), []
    for item in spec['images']:
        image = (manifest.parent / item['file']).resolve()
        if not image.is_relative_to(manifest.parent.resolve()) or not image.is_file():
            raise ValueError('Missing or unsafe firmware image path.')
        address = int(item['address'], 0)
        size = image.stat().st_size
        if address not in limits or address in seen or not 0 < size <= limits[address] - address:
            raise ValueError('Firmware image has an invalid or overlapping flash range.')
        if hashlib.sha256(image.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Firmware checksum mismatch. Rebuild the firmware package.')
        seen.add(address)
        result += [hex(address), str(image)]
    if seen != set(limits):
        raise ValueError('Firmware package is incomplete.')
    return result


def package_info():
    try:
        if importlib.util.find_spec('esptool') is None:
            raise ValueError('Install the esptool dependency in the Hub environment.')
        flash_args()
        return {'available': True, 'id': 'ghost-radar-1', 'message': 'Verified local ESP32-C6 package.'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'available': False, 'id': 'ghost-radar-1',
                'message': 'Firmware package or esptool unavailable. See services/wifi/WEB.md.'}


def restart(port):
    """Run the USB reset used after flashing, without changing flash contents."""
    from esptool.reset import HardReset
    device = serial.Serial(port=None, baudrate=115200, timeout=.2, write_timeout=1)
    device.dtr = device.rts = False
    device.port = port
    try:
        device.open()
        HardReset(device, uses_usb=True)()
    finally:
        device.close()


def install(port, notify, manifest=MANIFEST, timeout=120):
    images = flash_args(manifest)
    command = [sys.executable, '-m', 'esptool', '--chip', 'esp32c6', '--port', port,
               '--baud', '460800', '--before', 'default_reset', '--after', 'hard_reset',
               'write_flash', '--flash_mode', 'dio', '--flash_freq', '80m', '--flash_size', '4MB', *images]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    lines = queue.Queue()

    def read_output():
        for line in process.stdout:
            lines.put(line.strip())
        lines.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    try:
        while True:
            if time.monotonic() > deadline:
                raise RuntimeError('Firmware installation timed out. Check USB and retry.')
            try:
                line = lines.get(timeout=.2)
            except queue.Empty:
                continue
            if line is None:
                break
            # Do not expose hardware MAC addresses or unbounded process output.
            if any(word in line for word in ('Writing at', 'Hash of data', 'Connecting', 'Error', 'error', 'failed')):
                notify(line[:240])
        if process.wait(timeout=5) != 0:
            raise RuntimeError('Installation failed. Check USB; if needed, hold BOOT while reconnecting and retry.')
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        reader.join(2)
        process.stdout.close()
