import unittest
from datetime import date, timedelta
from economic_baseline import matching_deltas, probabilities, METHODS

class TestEconomicBaseline(unittest.TestCase):
    def history(self,values):
        d=date(2025,1,1)
        return [(d+timedelta(days=14*i),float(x)) for i,x in enumerate(values)]
    def test_no_overlap_and_horizon(self):
        hist=self.history(range(10))
        pairs=matching_deltas(hist,28)
        self.assertEqual([x[1] for x in pairs],[2.0]*4)
        self.assertEqual(len({x[0] for x in pairs}),4)
    def test_small_sample_neutral(self):
        p,n=probabilities(self.history([1,2,3]),14)
        self.assertLess(n,3)
        self.assertEqual(p,{m:.5 for m in METHODS})
    def test_strict_increase_ties_are_no(self):
        p,n=probabilities(self.history([1]*10),14)
        self.assertEqual(n,9)
        self.assertAlmostEqual(p["empirical"],2/13)
    def test_direction_and_bounds(self):
        p,n=probabilities(self.history(range(12)),14)
        self.assertGreater(p["momentum"],.5)
        self.assertLess(p["mean_reversion"],.5)
        self.assertTrue(all(0<=v<=1 for v in p.values()))
if __name__=="__main__":
    unittest.main()
