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


from publication_guard import require_publication_authorization


class PublicationGuardTests(unittest.TestCase):
    def test_live_modes_fail_closed(self):
        for mode in ("tournament", "metaculus_cup"):
            for env in ({}, {"FUTUREEVAL_LIVE_ENABLED": "True"}, {"FUTUREEVAL_LIVE_ENABLED": "1"}):
                with self.subTest(mode=mode, env=env), self.assertRaises(RuntimeError):
                    require_publication_authorization(mode, True, env)

    def test_explicit_activation_allows_live(self):
        require_publication_authorization(
            "tournament", True, {"FUTUREEVAL_LIVE_ENABLED": "true"}
        )

    def test_dry_run_and_sandbox_are_allowed(self):
        require_publication_authorization("tournament", False, {})
        require_publication_authorization("metaculus_cup", False, {})
        require_publication_authorization("test_questions", True, {})

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            require_publication_authorization("unknown", False, {})

    def test_live_workflows_are_guarded_independently(self):
        root = Path(__file__).resolve().parents[1]
        for path in (
            ".github/workflows/run_bot_on_tournament.yaml",
            ".github/workflows/run_bot_on_metaculus_cup.yaml",
        ):
            content = root.joinpath(path).read_text()
            with self.subTest(path=path):
                self.assertIn("if: ${{ vars.FUTUREEVAL_LIVE_ENABLED == 'true' }}", content)
                self.assertIn("FUTUREEVAL_LIVE_ENABLED: ${{ vars.FUTUREEVAL_LIVE_ENABLED }}", content)

    def test_main_calls_guard_before_banner(self):
        main = Path(__file__).resolve().parents[1].joinpath("main.py").read_text()
        self.assertLess(
            main.index("require_publication_authorization(run_mode, publish_to_metaculus)"),
            main.index("print_startup_banner(run_mode, will_publish=publish_to_metaculus)"),
        )


if __name__ == "__main__":
    unittest.main()
