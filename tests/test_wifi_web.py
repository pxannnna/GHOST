import unittest
from services.wifi.live.api import MotionSession
from services.wifi.live.protocol import Status, Report

def status(t, calibrated=False, wifi=True):
    return Status(1,'ghost-radar-1',int(t*1000),wifi,False,calibrated,.02,.01)
def report(t,motion=0):
    return Report(int(t*10),int(t*1000),.01,.01,.01,0,.08,.02,.1,motion)

class WifiWebTests(unittest.TestCase):
    def ready(self):
        s=MotionSession();s.event('opened','COM7',0);s.event('status',status(1),1);s.event('report',report(1),1);return s
    def calibrated(self):
        s=self.ready();s.calibrate(1);s.event('training',('STARTED',0),1)
        for t in range(2,32):s.event('status',status(t),t);s.tick(t)
        self.assertEqual(s.stage,'await_stop');self.assertIn('radar --train_stop',s.commands)
        s.event('training',('DONE',0),31);s.event('status',status(31,True),31)
        s.event('status',status(34,True),34);s.event('report',report(34),34);s.tick(34)
        self.assertEqual(s.stage,'detecting');return s
    def test_calibration_then_unlimited_detection(self):
        s=self.calibrated()
        for t in range(35,201):s.event('status',status(t,True),t);s.event('report',report(t),t);s.tick(t)
        self.assertEqual(s.stage,'detecting');self.assertIsNone(s.snapshot(200)['calibration_remaining_s'])
    def test_one_second_pulse_not_extended(self):
        s=self.calibrated();s.event('report',report(35,1),35);self.assertTrue(s.snapshot(35.5)['green'])
        s.event('report',report(35.8,1),35.8);self.assertFalse(s.snapshot(36.1)['green']);self.assertEqual(s.pulse.count,1)
    def test_missing_reports_are_unknown(self):
        s=self.calibrated();s.event('status',status(37,True),37);s.tick(37)
        state=s.snapshot(37);self.assertIsNone(state['motion']);self.assertFalse(state['green']);self.assertFalse(state['fresh'])
    def test_disconnect_invalidates_calibration(self):
        s=self.calibrated();s.event('wifi_lost',None,35)
        self.assertIsNone(s.threshold);self.assertEqual(s.stage,'error');self.assertIsNone(s.snapshot(35)['motion'])
    def test_ack_timeout(self):
        s=self.ready();s.calibrate(1);s.tick(6)
        self.assertEqual(s.stage,'error');self.assertIn('radar --train_stop',s.commands)
    def test_invalid_threshold_rejected(self):
        s=self.ready();s.stage='wait_status';bad=status(2,True);bad.motion_threshold=0;s.event('status',bad,2)
        self.assertEqual(s.stage,'error');self.assertIsNone(s.threshold)
    def test_stop_clears_running_detection(self):
        s=self.calibrated();s.stop();self.assertEqual(s.stage,'idle');self.assertIsNone(s.threshold)
    def test_restart_requires_new_calibration(self):
        s=self.calibrated();s.event('status',status(1,True),35);self.assertEqual(s.stage,'error');self.assertIsNone(s.threshold)
    def test_stale_status_cannot_start_calibration(self):
        s=self.ready()
        with self.assertRaises(ValueError):s.calibrate(20)
if __name__=='__main__':unittest.main()
