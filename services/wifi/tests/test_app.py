"""Window/state smoke checks with a fake transport; never touch a serial port."""
from pathlib import Path
import queue
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from services.wifi.demo.app import App
from services.wifi.demo.protocol import Status, Report


class FakeWorker:
    def __init__(self):
        self.events=queue.Queue(); self.commands=queue.Queue()
        from threading import Event
        self.stopping=Event()
    def start(self): pass
    def join(self, timeout=None): pass
    def send(self, value): self.commands.put(('send',value))


class AppTests(unittest.TestCase):
    def test_start_gate_and_stale_data(self):
        with tempfile.TemporaryDirectory() as folder, patch('services.wifi.demo.app.SerialWorker',FakeWorker):
            root=tk.Tk(); root.withdraw()
            app=App(root,Path(folder))
            root.geometry('880x760')
            root.update_idletasks()
            now=time.monotonic()
            try:
                app.render(now)
                self.assertEqual(str(app.primary['state']),'disabled')
                self.assertLess(app.result_label.winfo_rooty()+app.result_label.winfo_height(),root.winfo_rooty()+760)
                app.handle_event('opened','COM99',now)
                app.handle_event('status',Status(1,'ghost-radar-1',100,True,False,False,0,0),now)
                app.handle_event('report',Report(1,101,.01,.01,.01,0,.01,.01,.05,0),now)
                app.empty_confirm.set(True)
                app.render(now)
                self.assertEqual(str(app.primary['state']),'normal')
                app.render(now+3)
                self.assertEqual(str(app.primary['state']),'disabled')
                self.assertEqual(app.banner['text'],'Waiting for radar results')
                app.handle_event('connection_error','test disconnect',now+4)
                app.render(now+4)
                self.assertFalse(app.compatible)
                self.assertEqual(str(app.primary['state']),'disabled')
            finally:
                app.close()
