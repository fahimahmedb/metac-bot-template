"""Offline checks for the evidence protocol; no provider keys or web access."""
import unittest
from pathlib import Path

from forecasting_protocol import RESEARCH_EVIDENCE_PROTOCOL, FORECAST_DECISION_PROTOCOL


class ProtocolSmokeTests(unittest.TestCase):
    def test_evidence_contract_and_counterexample(self):
        self.assertIn("exact resolution trigger", RESEARCH_EVIDENCE_PROTOCOL)
        self.assertIn("publication date", RESEARCH_EVIDENCE_PROTOCOL)
        self.assertIn("counterexample", RESEARCH_EVIDENCE_PROTOCOL)
        self.assertIn("Never fabricate", RESEARCH_EVIDENCE_PROTOCOL)

    def test_no_human_loop_or_forecast_copying(self):
        self.assertIn("never request human input", RESEARCH_EVIDENCE_PROTOCOL)
        self.assertIn("no human input", FORECAST_DECISION_PROTOCOL)
        self.assertIn("Never reproduce another forecaster", FORECAST_DECISION_PROTOCOL)

    def test_main_uses_both_protocols(self):
        main = Path(__file__).resolve().parents[1].joinpath("main.py").read_text()
        self.assertEqual(main.count("{RESEARCH_EVIDENCE_PROTOCOL}"), 1)
        self.assertEqual(main.count("{FORECAST_DECISION_PROTOCOL}"), 4)
        self.assertIn("publish_reports_to_metaculus=publish_to_metaculus", main)


if __name__ == "__main__":
    unittest.main()
