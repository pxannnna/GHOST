"""Guided Windows demo: discovery, setup, calibration, trials and live light."""
import argparse
from collections import deque
import json
import math
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from .firmware import MANIFEST, ROOT, flash_args
from .protocol import Pulse, wifi_command
from .results import Session, export_results
from .transport import SerialWorker
from .workflow import Experiment

BG, PANEL, TEXT, MUTED, GREEN = '#112131', '#1c3247', '#f0f5fa', '#b8cbdc', '#27dc8b'
ACTIVE = {'countdown_empty','await_start','calibrating','await_stop','wait_status','settling',
          'empty','waiting_walk','countdown_walk','walking'}


class App:
    def __init__(self, root, output, status_path=None):
        self.root, self.output, self.status_path = root, output, status_path
        self.worker = SerialWorker()
        self.flow = Experiment()
        self.session = None
        self.status = None
        self.last_status = self.last_serial = self.last_report_time = None
        self.last_report = None
        self.opened_at = None
        self.port = None
        self.compatible = False
        self.installing = False
        self.connecting_until = 0
        self.exporting = False
        self.result_events = queue.Queue()
        self.next_diagnostic = 0
        self.pulse = Pulse()
        self.trace = deque(maxlen=3000)
        self.connection_text = 'Plug in your ESP32-C6 using a USB data cable.'
        self.result_text = 'No experiment has been recorded yet.'
        root.title('GHOST | Wi-Fi motion demo')
        root.geometry('940x800')
        root.minsize(880,760)
        root.configure(bg=BG)
        self.make_ui()
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.worker.start()
        root.after(50,self.poll)

    def label(self, parent, text='', size=11, color=TEXT, **kw):
        return tk.Label(parent,text=text,bg=BG,fg=color,font=('Segoe UI',size),**kw)

    def make_ui(self):
        top = tk.Frame(self.root,bg=BG)
        top.pack(fill='x',padx=24,pady=(16,8))
        self.label(top,'GHOST / Wi-Fi motion',22).pack(side='left')
        self.label(top,'LIVE SENSOR',10,GREEN).pack(side='right')
        self.connection = self.label(self.root, size=10,color=MUTED,anchor='w',wraplength=880)
        self.connection.pack(fill='x',padx=24)
        settings = tk.LabelFrame(self.root,text='Device and hotspot',fg=MUTED,bg=BG,padx=12,pady=10)
        settings.pack(fill='x',padx=24,pady=10)
        self.port_choice = tk.StringVar(value='Automatic')
        self.ports = ttk.Combobox(settings,textvariable=self.port_choice,values=['Automatic'],state='readonly',width=15)
        self.ports.grid(row=0,column=0,padx=5,sticky='w')
        self.ports.bind('<<ComboboxSelected>>', self.select_port)
        self.install_button = ttk.Button(settings,text='Install / update firmware',command=self.install)
        self.install_button.grid(row=0,column=1,padx=5)
        self.label(settings,'2.4 GHz WPA2 hotspot',10,MUTED).grid(row=0,column=2,columnspan=2,sticky='w',padx=8)
        self.ssid, self.password = tk.StringVar(), tk.StringVar()
        self.label(settings,'SSID',10).grid(row=1,column=0,sticky='w',padx=5,pady=(8,0))
        self.label(settings,'Password (not saved)',10).grid(row=1,column=1,sticky='w',padx=5,pady=(8,0))
        ttk.Entry(settings,textvariable=self.ssid,width=22).grid(row=2,column=0,padx=5,pady=4)
        ttk.Entry(settings,textvariable=self.password,show='*',width=26).grid(row=2,column=1,padx=5,pady=4)
        self.connect_button = ttk.Button(settings,text='Connect hotspot',command=self.connect_hotspot)
        self.connect_button.grid(row=2,column=2,padx=8)
        self.label(settings,'Keep the phone and receiver fixed after calibration.',10,MUTED).grid(row=3,column=0,columnspan=4,sticky='w',padx=5)
        self.banner = self.label(self.root,'Waiting for device',27,wraplength=880)
        self.banner.pack(pady=(10,2))
        self.instruction = self.label(self.root,size=12,color=MUTED,wraplength=860,height=2)
        self.instruction.pack(fill='x',padx=24)
        display = tk.Frame(self.root,bg=BG)
        display.pack(fill='x',padx=24,pady=5)
        self.lamp = tk.Canvas(display,width=105,height=105,bg=BG,highlightthickness=0)
        self.lamp.pack(side='left',padx=(10,24))
        self.circle = self.lamp.create_oval(10,10,95,95,fill='#344b5d',outline=MUTED,width=2)
        self.chart = tk.Canvas(display,height=105,bg=PANEL,highlightthickness=0)
        self.chart.pack(side='left',fill='x',expand=True)
        self.metrics = self.label(self.root,size=10,color=MUTED)
        self.metrics.pack(pady=4)
        self.progress = ttk.Progressbar(self.root,maximum=100)
        self.progress.pack(fill='x',padx=30,pady=5)
        self.empty_confirm = tk.BooleanVar(value=False)
        self.check = tk.Checkbutton(self.root,text='The phone and board are fixed, and everyone has left the test area.',
                                   variable=self.empty_confirm,bg=BG,fg=TEXT,selectcolor=PANEL,activebackground=BG,activeforeground=TEXT)
        self.check.pack(pady=5)
        actions = tk.Frame(self.root,bg=BG)
        actions.pack(pady=6)
        self.primary = ttk.Button(actions,text='Start calibration + empty test',command=self.start)
        self.primary.pack(side='left',padx=7)
        self.stop_button = ttk.Button(actions,text='Stop experiment',command=self.stop)
        self.stop_button.pack(side='left',padx=7)
        self.results_button = ttk.Button(actions,text='Open results',command=self.open_results)
        self.results_button.pack(side='left',padx=7)
        self.result_label = self.label(self.root,size=11,color=MUTED,wraplength=870,height=3)
        self.result_label.pack(fill='x',padx=24,pady=(5,0))
        self.label(self.root,'Motion changes the radio channel. This demo does not identify gestures or count people.',10,MUTED).pack(pady=5)

    def select_port(self, _event=None):
        if self.flow.stage in ACTIVE:
            self.flow.abort('Device selection changed. Restart calibration.',time.monotonic())
        self.compatible = False
        self.worker.commands.put(('select',None if self.port_choice.get()=='Automatic' else self.port_choice.get()))

    def install(self):
        if not self.port or self.installing:
            return
        try:
            flash_args()
        except (OSError,ValueError,KeyError) as exc:
            messagebox.showerror('Firmware package unavailable',str(exc)+'\nSee firmware/xiao/README.md to build the package.')
            return
        if not messagebox.askokcancel('Install GHOST firmware',
                f'Install the checked ESP32-C6 firmware on {self.port}?\nThis replaces the current program and restarts the board. Calibration must be repeated.'):
            return
        if self.flow.stage in ACTIVE:
            self.flow.abort('Firmware installation requested.',time.monotonic())
        self.installing = True
        self.compatible = False
        self.pulse.invalidate()
        self.worker.commands.put(('install',self.port))

    def connect_hotspot(self):
        if not self.compatible or self.flow.stage in ACTIVE:
            return
        try:
            command = wifi_command(self.ssid.get(),self.password.get())
        except ValueError as exc:
            messagebox.showerror('Check hotspot settings',str(exc))
            return
        self.worker.send(command)
        self.connecting_until = time.monotonic()+25
        self.connection_text = 'Connecting to hotspot. Keep the hotspot enabled.'

    def start(self):
        now = time.monotonic()
        if self.flow.stage == 'waiting_walk':
            self.flow.start_walking(now)
        elif self.empty_confirm.get():
            if self.session:
                self.session.close()
            self.session = Session(self.output,self.flow.timing)
            self.flow.start_empty(now)
            self.pulse = Pulse()
            self.result_text = 'Recording to '+str(self.session.path)
            self.empty_confirm.set(False)
        self.handle_actions()

    def stop(self):
        self.flow.abort('Experiment stopped by the operator. Partial data has been kept.',time.monotonic())
        self.handle_actions()

    def lost(self, message, now):
        self.status = None
        self.last_report_time = None
        self.pulse.invalidate()
        if self.flow.stage in ACTIVE or self.flow.stage == 'complete':
            self.flow.abort(message,now)
        self.connection_text = message

    def handle_event(self, kind, value, now):
        if kind == 'devices':
            self.ports.configure(values=['Automatic']+value)
        elif kind == 'discovery':
            if self.port is None:
                self.connection_text = value
        elif kind == 'opened':
            self.port = value
            if self.port_choice.get() != 'Automatic':
                self.port_choice.set(value)
            self.opened_at = now
            self.last_status = None
            self.compatible = False
            self.connection_text = f'{value} detected. Checking firmware...'
        elif kind in ('closed','connection_error'):
            self.port = None
            self.compatible = False
            self.installing = False
            self.lost('USB connection unavailable. Close other serial monitors and check the cable.'+(' '+str(value) if value else ''),now)
        elif kind == 'serial_alive':
            self.last_serial = now
        elif kind == 'status':
            self.last_status = now
            self.compatible = value.compatible
            if not self.compatible:
                self.lost('Incompatible firmware. Use Install / update firmware.',now)
                return
            self.status = value
            self.flow.on_status(value,now)
            if value.wifi:
                self.connecting_until = 0
                self.connection_text = f'{self.port} | GHOST firmware verified | Hotspot connected | HT-LTF'
            elif not self.connecting_until:
                self.connection_text = f'{self.port} | Firmware verified. Enter your hotspot settings and connect.'
        elif kind == 'report':
            if not self.compatible:
                return
            self.last_report_time, self.last_report = now,value
            self.trace.append((now,value.jitter,value.jitter_median))
            self.flow.on_report(value,now)
            if self.flow.thresholds and self.flow.stage in ('empty','waiting_walk','walking','complete'):
                self.pulse.update(value.motion,now)
        elif kind == 'training':
            self.flow.on_training(value,now)
        elif kind == 'window_reset':
            if self.session:
                self.session.event('window_reset',self.flow.stage)
        elif kind in ('wifi_lost','reboot'):
            self.lost('Hotspot disconnected; reconnect and recalibrate.' if kind=='wifi_lost'
                      else 'Board restarted; reconnect the hotspot and recalibrate.',now)
        elif kind == 'installing':
            self.installing = True
            self.connection_text = 'Installing firmware. Keep USB connected.'
        elif kind == 'flash_progress':
            self.connection_text = value
        elif kind == 'installed':
            self.installing = False
            self.port = None
            self.opened_at = None
            self.status = None
            self.flow = Experiment()
            self.connection_text = 'Firmware installed. Waiting for the board to reconnect...'

    def handle_actions(self):
        for kind,value in self.flow.drain():
            if kind == 'command':
                self.worker.send(value)
            elif kind == 'row' and self.session:
                self.session.row(*value)
            elif kind == 'phase':
                if self.session:
                    self.session.event('phase',value)
                    self.session.update(status=value,thresholds=self.flow.thresholds,error=self.flow.error)
                if value in ('empty','walking','waiting_walk','complete'):
                    self.root.bell()
                if value == 'complete':
                    self.export()

    def export(self):
        path = self.session.path
        rows = {k:list(v) for k,v in self.flow.rows.items()}
        thresholds = dict(self.flow.thresholds)
        self.exporting = True
        def work():
            try:
                self.result_events.put(('exported',(path,export_results(path,rows,thresholds))))
            except Exception as exc:
                self.result_events.put(('export_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def open_results(self):
        if not self.session:
            return
        report = self.session.path/'report.html'
        if report.exists():
            webbrowser.open(report.as_uri())
        elif os.name == 'nt':
            os.startfile(self.session.path)

    def poll(self):
        now = time.monotonic()
        try:
            # Drain already received lines before advancing timed stages.
            for _ in range(800):
                try:
                    kind,value = self.worker.events.get_nowait()
                except queue.Empty:
                    break
                self.handle_event(kind,value,now)
            if self.compatible and self.last_status is not None and now-self.last_status>7:
                self.compatible = False
                self.lost('Firmware status timed out. Waiting for the device to recover.',now)
            self.flow.tick(now)
            self.handle_actions()
            while not self.result_events.empty():
                kind,value = self.result_events.get_nowait()
                self.exporting = False
                if kind == 'exported':
                    path,result = value
                    self.result_text = (f"Motion reports: empty {result['empty']['motion_report_fraction']:.1%}, "
                                        f"walking {result['walking']['motion_report_fraction']:.1%}. "
                                        'These are report fractions, not accuracy. Open results for gaps and plots.')
                else:
                    self.result_text = 'Plot export failed; CSV files are saved. '+value
            self.render(now)
        except (OSError,ValueError) as exc:
            self.flow.abort('Local recording error: '+str(exc),now)
            self.result_text = str(exc)
        self.root.after(40,self.poll)

    def render(self, now):
        fresh = self.last_report_time is not None and now-self.last_report_time<2
        if not fresh:
            self.pulse.invalidate()
        ready = bool(self.compatible and self.status and self.status.wifi and fresh and not self.installing)
        remaining = max(0,math.ceil(self.flow.deadline-now))
        stage = self.flow.stage
        titles = {
            'countdown_empty':(f'Leave the area: {remaining}', 'Calibration will start automatically. Keep both devices fixed.'),
            'await_start':('Starting calibration','Waiting for the firmware to acknowledge training.'),
            'calibrating':(f'Calibrating: {remaining} s','Keep the room empty. No motion decisions are expected during training.'),
            'await_stop':('Finishing calibration','Waiting for the official library to finish.'),
            'wait_status':('Checking calibration','Verifying nonzero thresholds and firmware status.'),
            'settling':('Preparing empty-room test','Keep the area empty while the detector resumes.'),
            'empty':(f'EMPTY ROOM: {remaining} s','Recording automatically. Keep everyone outside the test area.'),
            'waiting_walk':('Empty test complete','Prepare beside the test area. Click the walking countdown button when ready.'),
            'countdown_walk':(f'Get ready to walk: {remaining}','Wait for START WALKING and the sound. Do not move either device.'),
            'walking':(f'START WALKING / {remaining} s left','Walk naturally back and forth between the devices. Keep walking until STOP.'),
            'complete':('STOP WALKING - test complete','Live motion indicator remains active. Open results to inspect the comparison.'),
            'error':('Experiment stopped',self.flow.error),
            'idle':('Ready for empty-room setup','Fix both devices, leave the test area, tick the confirmation, then start.')}
        title,detail = titles[stage]
        if self.installing:
            title,detail = 'Installing firmware','Keep the USB cable connected. The board will restart automatically.'
        elif not self.compatible:
            title = 'Checking firmware' if self.port else 'Waiting for device'
            if self.port and self.opened_at and now-self.opened_at>5:
                title,detail = 'Firmware setup required','The board is detected. Install this demo firmware to enable the guided workflow.'
            else:
                detail = 'Supported USB devices are detected automatically.'
        elif not self.status or not self.status.wifi:
            title,detail = 'Connect the hotspot','Enter the 2.4 GHz hotspot settings above, then click Connect hotspot.'
        elif not fresh and stage not in ('calibrating','await_start','await_stop','wait_status','settling'):
            title,detail = 'Waiting for radar results','Missing results are unknown, not evidence of no motion. Check the hotspot and USB.'
        lit = fresh and now<self.pulse.until and ready and self.flow.thresholds is not None
        self.lamp.itemconfigure(self.circle,fill=GREEN if lit else '#344b5d')
        self.banner.configure(text=title,fg=GREEN if lit else TEXT)
        self.instruction.configure(text=detail)
        if self.connecting_until and now>self.connecting_until:
            self.connecting_until = 0
            self.connection_text = 'Hotspot connection timed out. Check the name, password and 2.4 GHz setting, then retry.'
        self.connection.configure(text=self.connection_text)
        self.primary.configure(text='Ready: start walking countdown' if stage=='waiting_walk' else 'Start calibration + empty test',
                               state='normal' if ready and not self.exporting and (stage=='waiting_walk' or
                               (stage in ('idle','error','complete') and self.empty_confirm.get())) else 'disabled')
        self.connect_button.configure(state='normal' if self.compatible and stage not in ACTIVE and not self.installing else 'disabled')
        self.install_button.configure(state='normal' if self.port and stage not in ACTIVE and not self.installing else 'disabled')
        self.stop_button.configure(state='normal' if stage in ACTIVE else 'disabled')
        self.results_button.configure(state='normal' if self.session else 'disabled')
        self.ports.configure(state='disabled' if self.installing or stage in ACTIVE else 'readonly')
        duration = self.flow.timing.recording if stage in ('empty','walking') else self.flow.timing.calibration if stage=='calibrating' else self.flow.timing.countdown
        self.progress.configure(value=100*(1-min(remaining,duration)/duration) if stage in ('empty','walking','calibrating','countdown_empty','countdown_walk') else 0)
        metrics = f'Green pulses: {self.pulse.count}  |  Result age: '+(f'{now-self.last_report_time:.1f} s' if self.last_report_time else 'unknown')
        if self.last_report:
            metrics += f'  |  0.2 x Jitter: {0.2*self.last_report.jitter:.5f}  |  Official Motion: {self.last_report.motion}'
        self.metrics.configure(text=metrics)
        self.result_label.configure(text='Saving comparison plots...' if self.exporting else self.result_text)
        self.draw_trace(now)
        if self.status_path and now>=self.next_diagnostic:
            self.status_path.parent.mkdir(parents=True,exist_ok=True)
            self.status_path.write_text(json.dumps({'mode':'live','port':self.port,'compatible':self.compatible,
                'wifi':bool(self.status and self.status.wifi),'stage':stage,'fresh':fresh,'green':lit,
                'triggers':self.pulse.count,'title':title,'session':str(self.session.path) if self.session else None},indent=2),encoding='utf-8')
            self.next_diagnostic = now+1

    def draw_trace(self, now):
        self.chart.delete('all')
        w = max(100,self.chart.winfo_width())
        points = [(t,0.2*v,median) for t,v,median in self.trace if 0 <= now-t < 15]
        threshold = self.flow.thresholds['motion'] if self.flow.thresholds else None
        self.chart.create_text(10,5,anchor='nw',fill=MUTED,
                               text='0.2 x Jitter / last 15 s / fixed scale',font=('Segoe UI',9))
        if not threshold:
            self.chart.create_text(w/2,58,fill=MUTED,
                                   text='Complete empty-area calibration to show the reference line.')
            return
        # Display only: the lamp still uses the board's official motion flag.
        # Lock the range to calibration, rather than rescaling to recent peaks.
        scale = 3*threshold
        left, right, top, bottom = 65, w-12, 32, 82
        height = bottom-top
        amber, blue = '#ffbf69', '#65baff'
        self.chart.create_text(w-10,5,anchor='ne',fill=amber,
                               text=f'Calibration reference: {threshold:.5g}',font=('Segoe UI',9))
        dynamic_label = f'{points[-1][2]:.5g}' if points else 'waiting for data'
        self.chart.create_text(10,19,anchor='nw',fill=blue,
                               text=f'Dynamic reference (recent jitter median): {dynamic_label}',font=('Segoe UI',8))
        for value in (0,threshold,scale):
            y = bottom-value/scale*height
            self.chart.create_text(left-5,y,anchor='e',fill=MUTED,
                                   text=f'{value:.3g}',font=('Segoe UI',8))
        self.chart.create_line(left,top,left,bottom,right,bottom,fill='#52697d')
        y = bottom-threshold/scale*height
        self.chart.create_line(left,y,right,y,fill=amber,dash=(6,4),width=2)
        self.chart.create_text(left,101,anchor='sw',fill=MUTED,font=('Segoe UI',8),
                               text='Reference only; lamp follows official Motion.  Time: -15 s to now.')
        # On the scaled-jitter axis the dynamic reference is the raw median,
        # not 0.2 * median or the console's median / sensitivity field.
        for column,color,dash in ((2,blue,(3,3)),(1,GREEN,())):
            segment = []
            prev = None
            for point in points:
                t,v = point[0],point[column]
                if prev is not None and t-prev>.2:
                    if len(segment)>=4:
                        self.chart.create_line(*segment,fill=color,width=2,dash=dash)
                    segment = []
                x = left+(t-(now-15))/15*(right-left)
                segment += [x,bottom-min(max(v,0),scale)/scale*height]
                if v > scale:
                    self.chart.create_polygon(x-3,top+4,x+3,top+4,x,top-1,
                                              fill=blue if column==2 else amber)
                prev = t
            if len(segment)>=4:
                self.chart.create_line(*segment,fill=color,width=2,dash=dash)
        if any(max(v,median) > scale for _,v,median in points):
            self.chart.create_text(right,top-2,anchor='se',fill=amber,font=('Segoe UI',8),
                                   text='Above-range values marked at top')

    def close(self):
        if self.installing:
            messagebox.showinfo('Firmware installation','Wait for firmware installation to finish before closing.')
            return
        if self.exporting:
            messagebox.showinfo('Saving results','Please wait for the comparison files to finish saving.')
            return
        if self.session:
            if self.flow.stage in ACTIVE:
                self.session.update(status='aborted',error='Application closed during experiment.')
            self.session.close()
        self.worker.stopping.set()
        self.worker.join(timeout=1.5)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'data/wifi/demo')
    parser.add_argument('--status-file',type=Path,default=ROOT/'data/wifi/demo/live-status.json')
    args = parser.parse_args()
    root = tk.Tk()
    App(root,args.output.resolve(),args.status_file.resolve())
    root.mainloop()
