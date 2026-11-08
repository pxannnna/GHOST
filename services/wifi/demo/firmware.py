"""Validate and install only the locally built, checksummed C6 package."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT/'firmware/xiao/.artifacts/manifest.json'


def flash_args(manifest=MANIFEST):
    spec = json.loads(manifest.read_text(encoding='utf-8'))
    if spec.get('target') != 'esp32c6' or spec.get('firmware_id') != 'ghost-radar-1':
        raise ValueError('This is not a compatible GHOST ESP32-C6 firmware package.')
    result = []
    for item in spec['images']:
        image = (manifest.parent/item['file']).resolve()
        if not image.is_relative_to(manifest.parent.resolve()) or not image.is_file():
            raise ValueError('Missing or unsafe firmware image path.')
        if hashlib.sha256(image.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Firmware checksum mismatch. Rebuild the firmware package.')
        address = int(item['address'], 0)
        if address < 0 or address+image.stat().st_size > 4*1024*1024:
            raise ValueError('Firmware image exceeds the 4 MB flash range.')
        result += [hex(address), str(image)]
    if not result:
        raise ValueError('Firmware package has no images.')
    return result


def install(port, notify, manifest=MANIFEST):
    images = flash_args(manifest)
    command = [sys.executable, '-m', 'esptool', '--chip', 'esp32c6', '--port', port,
               '--baud', '460800', '--before', 'default_reset', '--after', 'hard_reset',
               'write_flash', '--flash_mode', 'dio', '--flash_freq', '80m', '--flash_size', '4MB', *images]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace',
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    for line in process.stdout:
        # Only expose progress, not hardware MAC addresses, in app records.
        if any(word in line for word in ('Writing at', 'Hash of data', 'Connecting', 'error', 'Error', 'failed')):
            notify(line.strip())
    if process.wait() != 0:
        raise RuntimeError('Firmware installation failed. Check USB; hold BOOT while reconnecting if needed, then retry.')
