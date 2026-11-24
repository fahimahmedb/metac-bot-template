import unittest
from datetime import date,timedelta
import numpy as np
from rolling_economic import extract_features,train_before,metrics,FEATURES
class TestRollingEconomic(unittest.TestCase):
    def test_no_future(self):
        with self.assertRaises(ValueError):
            extract_features([(date(2026,1,2),1.)],date(2026,1,1),date(2026,1,1),7,"fred")
    def test_label_embargo(self):
        rows=[{"issued":"2025-10-01","target":"2025-10-08"},{"issued":"2025-10-20","target":"2025-10-27"}]
        self.assertEqual(train_before(rows,date(2025,11,15)),rows[:1])
    def test_scale_and_finite(self):
        d=date(2025,1,1)
        h=[(d+timedelta(days=14*i),100.+i) for i in range(10)]
        f=extract_features(h,h[-1][0],h[-1][0],30,"fred")
        self.assertEqual(tuple(f),FEATURES)
        self.assertTrue(np.isfinite(list(f.values())).all())
        g=extract_features([(t,v*10) for t,v in h],h[-1][0],h[-1][0],30,"fred")
        for k in ("z1","z3","level_z","slope","pair_up"):
            self.assertAlmostEqual(f[k],g[k])
    def test_scores(self):
        self.assertAlmostEqual(metrics([0,1],[.5,.5])["brier"],.25)
        self.assertEqual(metrics([0,1],[0,1])["brier"],0)
if __name__=="__main__": unittest.main()
