import unittest
import numpy as np
from aircraft_audio.identify import demo
from aircraft_audio.sustained_match import fit_sustained

class IdentificationTests(unittest.TestCase):
    def test_synthetic_aircraft_and_receiver_recovery(self):
        r=demo()
        self.assertIsNotNone(r['best_supported'])
        self.assertEqual(r['best_supported']['candidate_index'],0)
        self.assertEqual(r['best_supported']['aircraft'],'SYNTHETIC-AIRCRAFT')
        self.assertAlmostEqual(r['best_supported']['source_frequency_hz'],220,delta=1)

    def test_validation_columns_do_not_refit_pitch(self):
        f=np.arange(80.,551.,.5);t=np.arange(0.,100.,.5)
        curve=200-60*(t-50)/np.sqrt((t-50)**2+20**2)
        evidence=16*np.exp(-.5*((f[:,None]-curve)/.6)**2)
        a=fit_sustained(f,evidence,(curve/200)[None,:],t,[100,400])
        heldout=(np.floor(t/8).astype(int)%2)==1
        evidence[:,heldout]=40*np.exp(-.5*((f[:,None]-curve[heldout]-20)/.6)**2)
        b=fit_sustained(f,evidence,(curve/200)[None,:],t,[100,400])
        np.testing.assert_allclose(a['source_frequency_hz'],b['source_frequency_hz'])
        np.testing.assert_allclose(a['score'],b['score'])
        self.assertTrue(a['accepted'][0]);self.assertFalse(b['accepted'][0])

if __name__=='__main__':unittest.main()
