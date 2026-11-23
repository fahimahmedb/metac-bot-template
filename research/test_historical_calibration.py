import dataclasses
import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path

path = Path(__file__).with_name("historical_calibration.py")
spec = importlib.util.spec_from_file_location("historical_calibration",path)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)

def row(id, issued, resolved, p, y):
    return m.Row(id,date.fromisoformat(issued),date.fromisoformat(resolved),p,y)

class TemporalCalibrationTests(unittest.TestCase):
    def test_time_embargo_and_event_deduplication(self):
        rows=[
            row("train","2025-03-02","2025-06-01",.7,1),
            row("late-label","2025-08-01","2025-09-20",.7,1),
            row("train","2026-03-01","2026-04-01",.8,1),
            row("validation","2025-11-01","2025-12-01",.2,0),
            row("late-val","2025-12-01","2026-01-25",.2,0),
            row("test","2026-03-01","2026-05-01",.9,1),
            row("already-known","2026-03-01","2026-02-01",1,1),
            row("too-late","2026-07-02","2026-08-01",.5,0),
        ]
        train,val,test=m.split(rows)
        self.assertEqual([r.event for r in train],["train"])
        self.assertEqual([r.event for r in val],["validation"])
        self.assertEqual([r.event for r in test],["test"])

    def test_test_labels_cannot_affect_probabilities(self):
        train=[row(str(i),"2025-04-01","2025-06-01",.9,i%2) for i in range(20)]
        val=[row(str(i),"2025-11-01","2025-12-01",.9,i%2) for i in range(20,40)]
        test=[row(str(i),"2026-03-01","2026-04-01",.8,i%2) for i in range(40,60)]
        fitted=m.fit_and_select(train,val)["chosen"]
        first=m.predict([r.p for r in test],fitted)
        changed=[dataclasses.replace(r,y=1-r.y) for r in test]
        self.assertEqual(first,m.predict([r.p for r in changed],fitted))
        self.assertEqual(fitted,m.fit_and_select(train,val)["chosen"])
        self.assertTrue(all(0<x<1 for x in first))

    def test_baseline_scores(self):
        data=[row("1","2025-04-01","2025-06-01",.5,0),
              row("2","2025-04-01","2025-06-01",.5,1)]
        self.assertAlmostEqual(m.score(data,[.5,.5])["brier"],.25)
        self.assertAlmostEqual(m.score(data,[0,1])["brier"],0)

    def test_do_not_change_identity_if_no_validation_gain(self):
        train=[row(str(i),"2025-04-01","2025-06-01",.5,i%2) for i in range(20)]
        val=[row(str(i),"2025-11-01","2025-12-01",.5,i%2) for i in range(20,40)]
        fitted=m.fit_and_select(train,val)["chosen"]
        self.assertEqual(fitted["method"],"identity")

if __name__=="__main__":
    unittest.main()
