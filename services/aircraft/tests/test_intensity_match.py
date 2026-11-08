import unittest
import numpy as np
from aircraft_audio.intensity_match import maximize_intensity,evaluate_tones,sample_curve
from aircraft_audio.geometry import Frame,Track,received_curve

class IntensityMatchTests(unittest.TestCase):
    def test_curve_integral_equals_direct_scalar_sampling(self):
        f=np.arange(100,201,.5);t=np.arange(40)
        b=np.random.default_rng(4).uniform(0,1,(len(f),len(t)))
        p=110+2.2*t;v,active=sample_curve(f,b,p,[120,180])
        expected=[np.interp(hz,f,b[:,j]) if 120<=hz<=180 else 0 for j,hz in enumerate(p)]
        np.testing.assert_allclose(v,expected)
        s,_,_=evaluate_tones(f,b,(p/150)[None,:],np.array([[150]]),[120,180])
        self.assertAlmostEqual(s[0,0],100*np.mean(expected))

    def test_short_bright_intersection_does_not_beat_longer_match(self):
        f=np.arange(100,201,.5);t=np.arange(40);long=120+t;short=50+5*t
        b=np.zeros((len(f),len(t)))
        for j in range(len(t)):
            b[:,j]=.65*np.exp(-.5*((f-long[j])/.4)**2)
            if 100<=short[j]<=200:b[:,j]=np.maximum(b[:,j],np.exp(-.5*((f-short[j])/.4)**2))
        r=maximize_intensity(f,b,np.array([long/150,short/150]),[100,200],source_frequencies=[150])
        self.assertGreater(r['score'][0],r['score'][1])

    def test_two_flight_inverse_search_recovers_injected_receiver(self):
        frame=Frame(55,-3);lat,lon=55.1,-3.2
        candidates=np.array([[lat+a,lon+b] for a in [-.02,-.01,0,.01,.02] for b in [-.02,-.01,0,.01,.02]])
        truth=12;xyz=frame.xyz(candidates[:,0],candidates[:,1],100);f=np.arange(80,551,.25)
        total=np.zeros(len(candidates))
        for event in range(2):
            centre=1100+event*1000
            rows=[]
            for ti in np.arange(centre-180,centre+181,5):
                x=100*(ti-centre);la=lat+.006+(x/111320 if event else 0)
                lo=lon+.007+(x/(111320*np.cos(np.radians(lat))) if not event else 0)
                rows.append(dict(time_position=ti,latitude=la,longitude=lo,altitude_m=2200))
            track=Track(rows,frame);times=np.arange(centre-40,centre+61,2)
            d,_,_,valid=received_curve(track,xyz,times)
            self.assertTrue(valid.all());tone=180+35*event
            b=.02+.96*np.exp(-.5*((f[:,None]-tone*d[truth][None,:])/.5)**2)
            r=maximize_intensity(f,b,d,[100,400]);total+=r['score']
            self.assertAlmostEqual(r['source_frequency_hz'][truth],tone,delta=.2)
        self.assertEqual(int(np.argmax(total)),truth)

    def test_invalid_and_stationary_geometry_does_not_win(self):
        f=np.arange(100,201,.5);b=np.ones((len(f),32));d=np.ones((3,32));d[1]=np.nan;d[2,5]=-1
        r=maximize_intensity(f,b,d,[100,200],source_frequencies=[150])
        self.assertFalse(r['valid'].any())

if __name__=='__main__':unittest.main()
