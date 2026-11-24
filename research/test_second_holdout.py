"""Unit checks for the second temporal experiment."""
import unittest
from datetime import date
from second_holdout import Event, partition, variant_of, context_group, aggregate, text_features
class TestSecondHoldout(unittest.TestCase):
    def test_embargo_and_new_test(self):
        self.assertEqual(partition(Event("a",date(2026,1,1),date(2026,2,1),1)),"train")
        self.assertIsNone(partition(Event("b",date(2026,3,1),date(2026,3,20),1)))
        self.assertEqual(partition(Event("c",date(2026,4,1),date(2026,5,1),0)),"validation")
        self.assertEqual(partition(Event("d",date(2026,7,1),date(2026,8,1),0)),"test")
        self.assertIsNone(partition(Event("e",date(2026,7,1),date(2026,7,1),1)))
    def test_context_separation(self):
        self.assertEqual(variant_of("model (zero shot)",{}),"zero-shot")
        self.assertEqual(context_group(variant_of("model (zero shot with freeze values)",{})),"market-context")
        self.assertIsNone(variant_of("model",{"forecast_variant_key":"unrecognized"}))
    def test_masked_input(self):
        a=Event("SECRET_A",date(2026,7,1),date(2026,8,1),0)
        b=Event("SECRET_B",date(2026,7,1),date(2026,9,1),1)
        self.assertEqual(text_features(a,"Will X win in 2026?"),text_features(b,"Will X win in 2026?"))
        self.assertNotIn("2026",text_features(a,"Will X win in 2026?"))
    def test_aggregation_invariants(self):
        p={"a":.2,"b":.8}
        for method in ("mean","median","logit","tempered-logit","weighted"):
            self.assertAlmostEqual(aggregate(p,method),.5)
        self.assertAlmostEqual(aggregate(p,"weighted",{"a":3,"b":1}),.35)
if __name__=="__main__":
    unittest.main()
