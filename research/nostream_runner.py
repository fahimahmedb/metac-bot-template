"""Pinned No-Stream local, nonpublishing runner.

Execute from the pinned upstream checkout. No upstream CLI, schedules or platform
credentials. The exact inference and research engine is upstream; only the local
input, strict three-member coverage requirement and publication boundary differ.
Real smoke requires separately authorized resources; default is fail-closed.
"""
import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
from pathlib import Path
from contextlib import contextmanager, ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import socket
import subprocess

PIN = "79c1d7a1192a00724646ab05c67f3b776d2d7b65"
PLATFORM_KEYS = ("METACULUS_TOKEN", "MANTIC_TOKEN", "METACULUS_API_TOKEN")
REQUIRED = ("OPENROUTER_API_KEY", "ASKNEWS_CLIENT_ID", "ASKNEWS_SECRET",
            "EXA_API_KEY", "GOOGLE_API_KEY", "FRED_API_KEY", "SEC_EDGAR_CONTACT_EMAIL")

class PublicationBlocked(RuntimeError):
    pass

def assert_no_platform_credentials():
    if any(os.environ.get(k, "").strip() for k in PLATFORM_KEYS):
        raise PublicationBlocked("platform credentials forbidden in forecast process")
    for directory in (Path.cwd(), *Path.cwd().parents):
        if any((directory / name).exists() for name in (".env", ".env.local")):
            raise PublicationBlocked("dotenv file forbidden in isolated checkout")

def reference_config():
    import yaml
    root = Path.cwd()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if sha != PIN:
        raise RuntimeError("wrong upstream revision")
    source = root / ".github/workflows/run_bot_on_tournament.yaml"
    data = yaml.safe_load(source.read_text())
    env = next(s["env"] for s in data["jobs"]["forecast_job"]["steps"] if s.get("id") == "run_bot")
    # Only exact literal settings. Credentials never derived from source.
    flags = {k: str(v) for k, v in env.items() if isinstance(v, str) and "${{" not in v}
    for key in ("BINARY_STACKING_ENABLED", "MC_STACKING_ENABLED", "NUMERIC_STACKING_ENABLED"):
        if flags.get(key) != "false":
            raise RuntimeError("unexpected upstream stacking config")
    for key in ("NATIVE_SEARCH_ENABLED", "GEMINI_SEARCH_ENABLED", "GAP_FILL_ENABLED",
                "GAP_FILL_V2_ENABLED", "PREDICTION_MARKETS_ENABLED", "RESOLUTION_SOURCE_ENABLED"):
        if flags.get(key) != "true":
            raise RuntimeError("unexpected upstream research config: " + key)
    return flags

def _deny(*args, **kwargs):
    raise PublicationBlocked("publication disabled")
async def _deny_async(*args, **kwargs):
    _deny()

@contextmanager
def publication_guard():
    from forecasting_tools.helpers.metaculus_client import MetaculusClient
    from metaculus_bot.publish_hardening import _PATCHED_REPORT_TYPES, _PATCHED_METHODS
    assert_no_platform_credentials()
    original_dns = socket.getaddrinfo
    def guarded_dns(host, *args, **kwargs):
        h = (host.decode() if isinstance(host, bytes) else str(host)).lower().rstrip(".")
        if any(h == d or h.endswith("." + d) for d in ("metaculus.com", "mantic.com")):
            raise PublicationBlocked("platform DNS disabled")
        return original_dns(host, *args, **kwargs)
    with ExitStack() as stack:
        for report_type in _PATCHED_REPORT_TYPES:
            stack.enter_context(patch.object(report_type, "publish_report_to_metaculus", _deny_async))
        for method in _PATCHED_METHODS:
            stack.enter_context(patch.object(MetaculusClient, method, _deny))
        stack.enter_context(patch.object(socket, "getaddrinfo", guarded_dns))
        yield

def build_bot(research_sink=None):
    from main import TemplateForecaster
    from metaculus_bot.aggregation_strategies import AggregationStrategy
    from metaculus_bot.llm_configs import (FORECASTER_LLMS, STACKER_LLM,
        DISAGREEMENT_ANALYZER_LLM, SUMMARIZER_LLM, PARSER_LLM, RESEARCHER_LLM)
    assert_no_platform_credentials()
    if len(FORECASTER_LLMS) != 3:
        raise RuntimeError("unexpected roster")
    return TemplateForecaster(
        research_reports_per_question=1, predictions_per_research_report=1,
        publish_reports_to_metaculus=False, folder_to_save_reports_to=None,
        skip_previously_forecasted_questions=False, max_questions_per_run=1,
        aggregation_strategy=AggregationStrategy.CONDITIONAL_STACKING,
        is_benchmarking=False, min_forecasters_to_publish=3, research_sink=research_sink,
        llms={"forecasters": FORECASTER_LLMS, "stacker": STACKER_LLM,
              "analyzer": DISAGREEMENT_ANALYZER_LLM, "summarizer": SUMMARIZER_LLM,
              "parser": PARSER_LLM, "researcher": RESEARCHER_LLM})

def question():
    from forecasting_tools import BinaryQuestion
    now = datetime.now(timezone.utc)
    # Local prospective smoke case, no tournament post and no resolution in input.
    return BinaryQuestion(question_text="Will US CPI-U inflation for November 2026 be at least 3.0% year over year?",
        id_of_question=990001, id_of_post=990001,
        background_info="Use BLS CPI-U, all items, US city average, not seasonally adjusted.",
        resolution_criteria="YES if the first official BLS November 2026 CPI release reports the 12-month all-items CPI-U change as 3.0 percent or higher. Source https://www.bls.gov/news.release/cpi.htm",
        fine_print="Use the initial release, not revisions; no community forecasts.",
        open_time=now-timedelta(days=1), scheduled_resolution_time=datetime(2027,1,31,tzinfo=timezone.utc))

def real_smoke(output):
    # These attestations are NOT an implemented spending limit; provider-side caps
    # and permitted funded accounts must be independently verified by operator.
    if os.getenv("NOSTREAM_SMOKE_AUTHORIZED") != "true" or os.getenv("NOSTREAM_EXTERNAL_CAP_VERIFIED") != "true":
        raise SystemExit("BLOCK: real smoke authorization and verified provider caps absent")
    assert_no_platform_credentials()
    missing = [k for k in REQUIRED if not os.getenv(k, "").strip()]
    if missing:
        raise SystemExit("BLOCK: missing resources " + ", ".join(missing))
    if datetime.now(timezone.utc) >= datetime(2026,12,1,tzinfo=timezone.utc):
        raise SystemExit("BLOCK: smoke question expired; select a fresh prospective noncontest question")
    flags = reference_config()
    os.environ.update(flags)
    logging.basicConfig(level=logging.INFO)
    from metaculus_bot.research.persistence import ResearchPersistenceWriter
    from metaculus_bot.credit_telemetry import install_role_spend_tracker, log_role_spend
    from metaculus_bot.cli import _forecast_with_callback_drain
    from forecasting_tools.data_models.forecast_report import ForecastReport
    writer = ResearchPersistenceWriter("local-smoke", "metaculus", "noncontest", os.getenv("GITHUB_RUN_ID","local"))
    output.mkdir(parents=True,exist_ok=True)
    with publication_guard():
        bot = build_bot(writer.record)
        install_role_spend_tracker()
        try:
            reports = asyncio.run(_forecast_with_callback_drain(lambda: bot.forecast_questions([question()])))
        finally:
            log_role_spend()
            writer.flush(output_dir=str(output))
        if len(reports) != 1 or not isinstance(reports[0], ForecastReport):
            raise RuntimeError("missing real forecast report")
        report = reports[0]
        if not isinstance(report.prediction, float) or not math.isfinite(report.prediction) or not 0 <= report.prediction <= 1:
            raise RuntimeError("invalid probability")
        if bot.alertable_count:
            raise RuntimeError("degraded real pipeline")
        record={"source_sha":PIN, "issued_at":datetime.now(timezone.utc).isoformat(),
                "probability":report.prediction,"explanation":report.explanation,
                "question":question().question_text,"scope":"noncontest smoke, not performance qualification",
                "publication_enabled":False}
        payload=json.dumps(record,sort_keys=True).encode()
        (output/"forecast.json").write_bytes(payload)
        print("FORECAST_SHA256="+hashlib.sha256(payload).hexdigest())

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--output",type=Path,default=Path("local_smoke_artifacts"))
    args=parser.parse_args()
    assert_no_platform_credentials()
    if args.smoke:
        real_smoke(args.output)
    else:
        print("REFERENCE_CONFIG_JSON="+json.dumps(reference_config(),sort_keys=True))
        print("No inference or publication executed.")
if __name__=="__main__":
    main()
