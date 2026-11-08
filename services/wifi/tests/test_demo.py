"""Deterministic checks; these are simulated inputs, not hardware evidence."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from services.wifi.demo.firmware import flash_args
from services.wifi.demo.protocol import parse, Pulse, Report, Status, wifi_command
from services.wifi.demo.results import Session, summarize, export_results
from services.wifi.demo.transport import candidates
from services.wifi.demo.workflow import Experiment, Timing


def report(t=1000, motion=0):
    return Report(t,t,.001,.001,.01,0,.001,.001,.005,motion)


def status(t, calibrated=False, training=False, wifi=True):
    return Status(1,'ghost-radar-1',t,wifi,training,calibrated,.001,.004)


class ProtocolTests(unittest.TestCase):
    def test_real_format(self):
        kind,r = parse('csi> RADAR_DADA,99,1234,0.001,0.002,0.003,1,0.004,0.005,0.025,0')
        self.assertEqual(kind,'report')
        self.assertEqual((r.sequence,r.device_ms,r.presence,r.motion),(99,1234,1,0))
        self.assertEqual(r.jitter,.004)
        self.assertIsNone(parse('RADAR_DADA,0,0,0,0.001102,0,0,0.032899,0'))
        self.assertIsNone(parse('RADAR_DADA,99,1234,0.001,0.002,0.003,1,nan,0.005,0.025,0'))
        self.assertIsNone(parse('RADAR_DADA,99,1234,0.001'))

    def test_identity_and_credentials(self):
        _,s = parse('GHOST_STATUS,1,ghost-radar-1,900,1,0,1,0.001,0.004')
        self.assertTrue(s.compatible)
        self.assertTrue(s.calibrated)
        self.assertIn('"A phone"',wifi_command('A phone','password123'))
        for value in ('bad\r\nradar --train_start','bad"command','bad\\escape'):
            with self.assertRaises(ValueError):
                wifi_command(value,'password123')

    def test_pulse(self):
        p = Pulse()
        self.assertTrue(p.update(1,10))
        self.assertFalse(p.update(1,10.9))
        self.assertEqual(p.until,11)
        self.assertFalse(p.update(1,12))
        self.assertFalse(p.update(0,12.1))
        self.assertTrue(p.update(1,12.2))
        self.assertEqual(p.count,2)
        p.invalidate()
        self.assertEqual(p.until,0)

    def test_supported_usb_only(self):
        good=SimpleNamespace(vid=0x303a,pid=0x1001)
        bad=SimpleNamespace(vid=0x1234,pid=0x1234)
        self.assertEqual(candidates([bad,good]),[good])


class WorkflowTests(unittest.TestCase):
    def calibrated(self):
        f = Experiment(Timing(countdown=1,calibration=2,recording=3,settling=1))
        f.start_empty(0)
        f.tick(1)
        self.assertIn(('command','radar --train_start'),f.drain())
        f.on_training(('STARTED',0),1)
        f.tick(3)
        self.assertEqual(f.stage,'await_stop')
        f.on_training(('DONE',0),3.1)
        self.assertEqual(f.stage,'wait_status')
        f.on_status(status(100,calibrated=True),3.2)
        f.on_report(report(101),4)
        f.tick(4.3)
        self.assertEqual(f.stage,'empty')
        return f

    def test_full_experiment_keeps_one_calibration(self):
        f = self.calibrated()
        f.on_report(report(200),5)
        f.on_report(report(300),6)
        f.tick(7.4)
        self.assertEqual(f.stage,'waiting_walk')
        f.start_walking(8)
        f.on_report(report(400),8.8)
        f.tick(9)
        self.assertEqual(f.stage,'walking')
        f.on_report(report(500,1),10)
        f.on_report(report(600,1),11)
        f.tick(12.1)
        self.assertEqual(f.stage,'complete')
        self.assertEqual(len(f.rows['empty']),2)
        self.assertEqual(len(f.rows['walking']),2)
        self.assertEqual(f.thresholds['motion'],.004)
        self.assertNotIn(('command','radar --train_start'),f.drain())

    def test_missing_ack_and_failed_calibration(self):
        f=Experiment()
        f.start_empty(0); f.tick(5); f.tick(11)
        self.assertEqual(f.stage,'error')
        self.assertIsNone(f.thresholds)
        f.start_empty(12); f.tick(17); f.on_training(('ERROR',259),18)
        self.assertEqual(f.stage,'error')

    def test_reboot_and_disconnect_invalidate(self):
        for s in (status(1,True),status(200,True,wifi=False)):
            f=self.calibrated()
            f.on_status(s,5)
            self.assertEqual(f.stage,'error')
            self.assertIsNone(f.thresholds)

    def test_zero_thresholds_and_stale_walking(self):
        f=Experiment(); f.stage='wait_status'
        s=status(100,calibrated=True); s.motion_threshold=0
        f.on_status(s,1)
        self.assertEqual(f.stage,'error')
        f=self.calibrated()
        f.on_report(report(200),5); f.on_report(report(300),6); f.tick(7.4)
        f.start_walking(8); f.tick(9)
        self.assertEqual(f.stage,'error')


class ArtifactTests(unittest.TestCase):
    def test_flash_checksums_and_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); image=root/'app.bin'; image.write_bytes(b'firmware')
            spec={'target':'esp32c6','firmware_id':'ghost-radar-1','images':[{'address':'0x20000','file':'app.bin','sha256':hashlib.sha256(image.read_bytes()).hexdigest()}]}
            manifest=root/'manifest.json'; manifest.write_text(json.dumps(spec))
            self.assertEqual(flash_args(manifest)[0],'0x20000')
            image.write_bytes(b'changed')
            with self.assertRaises(ValueError): flash_args(manifest)
            spec['images'][0]['file']='../outside.bin'; manifest.write_text(json.dumps(spec))
            with self.assertRaises(ValueError): flash_args(manifest)

    def test_session_and_gap_metrics(self):
        rows=[{'host_elapsed_s':i,**report(t,m).values()} for i,(t,m) in enumerate([(1000,0),(1100,1),(6200,0)])]
        stats=summarize(rows)
        self.assertAlmostEqual(stats['max_report_gap_s'],5.1)
        self.assertAlmostEqual(stats['motion_report_fraction'],1/3)
        with tempfile.TemporaryDirectory() as temp:
            session=Session(Path(temp),Timing())
            for r in rows: session.row('empty',r)
            session.update(status='test_fixture')
            session.close()
            with (session.path/'empty.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))),3)

    def test_complete_export(self):
        data = {'empty':[{'host_elapsed_s':i,**report(1000+i*100,0).values()} for i in range(10)],
                'walking':[{'host_elapsed_s':i,**report(2000+i*100,i%2).values()} for i in range(10)]}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            result=export_results(path,data,{'presence':.001,'motion':.004},mode='simulated')
            self.assertEqual(result['walking']['motion_report_fraction'],.5)
            self.assertEqual(result['empty']['motion_report_fraction'],0)
            self.assertTrue((path/'comparison.png').stat().st_size>1000)
            self.assertIn('Data mode: simulated',(path/'report.html').read_text())


if __name__ == '__main__':
    unittest.main()
