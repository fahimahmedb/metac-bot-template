"""Targeted tests of the local integration layer; upstream provider stubs only."""
import os
import socket
import pytest
from forecasting_tools.data_models.forecast_report import ForecastReport
from forecasting_tools.helpers.metaculus_client import MetaculusClient
from metaculus_bot.publish_hardening import _PATCHED_REPORT_TYPES, _PATCHED_METHODS
from nostream_runner import (PLATFORM_KEYS, PublicationBlocked, assert_no_platform_credentials,
    publication_guard, reference_config, build_bot, real_smoke)
from test_offline_e2e_forecast import (_install_env, _install_llm_router,
    _install_provider_stubs, _binary_question, _numeric_question, _mc_question,
    _assert_pipeline_ran)

@pytest.fixture(autouse=True)
def remove_platform_credentials(monkeypatch):
    for k in PLATFORM_KEYS:
        monkeypatch.delenv(k,raising=False)

def test_reference_literal_config():
    flags=reference_config()
    assert flags["NATIVE_SEARCH_ENABLED"]=="true"
    assert flags["GAP_FILL_V2_ENABLED"]=="true"
    assert flags["PREDICTION_MARKETS_ENABLED"]=="true"
    assert flags["BINARY_STACKING_ENABLED"]=="false"
    assert not any(k in flags for k in PLATFORM_KEYS)
    assert "OPENROUTER_API_KEY" not in flags

def test_credentials_rejected(monkeypatch):
    monkeypatch.setenv("METACULUS_TOKEN","fake-token-not-a-real-key")
    with pytest.raises(PublicationBlocked):
        assert_no_platform_credentials()
    with pytest.raises(PublicationBlocked):
        build_bot()

@pytest.mark.asyncio
async def test_publication_paths_denied():
    with publication_guard():
        for cls in _PATCHED_REPORT_TYPES:
            with pytest.raises(PublicationBlocked):
                await cls.publish_report_to_metaculus(None)
        for method in _PATCHED_METHODS:
            with pytest.raises(PublicationBlocked):
                getattr(MetaculusClient,method)(None)
        for host in ("www.metaculus.com", "API.METACULUS.COM.", "competitions.mantic.com"):
            with pytest.raises(PublicationBlocked):
                socket.getaddrinfo(host,443)
        assert socket.getaddrinfo("localhost",443)

def test_default_real_smoke_gate(monkeypatch,tmp_path):
    monkeypatch.delenv("NOSTREAM_SMOKE_AUTHORIZED",raising=False)
    with pytest.raises(SystemExit,match="authorization"):
        real_smoke(tmp_path)
    assert not list(tmp_path.iterdir())

@pytest.mark.asyncio
@pytest.mark.parametrize(("factory","qtype"),[
    (_binary_question,"binary"),(_numeric_question,"numeric"),(_mc_question,"multiple_choice")])
async def test_guarded_actual_pipeline_with_offline_provider_stubs(monkeypatch,caplog,factory,qtype):
    for key,value in reference_config().items():
        monkeypatch.setenv(key,value)
    _install_env(monkeypatch)
    _install_llm_router(monkeypatch)
    _install_provider_stubs(monkeypatch)
    with publication_guard():
        bot=build_bot()
        assert bot.publish_reports_to_metaculus is False
        assert bot.min_forecasters_to_publish==3
        with caplog.at_level("INFO"):
            reports=await bot.forecast_questions([factory()])
        assert len(reports)==1 and isinstance(reports[0],ForecastReport)
        _assert_pipeline_ran(caplog,bot,expect_qtype=qtype)
        prediction=reports[0].prediction
        if qtype=="binary":
            assert 0 <= prediction <= 1
        elif qtype=="numeric":
            ps=[pt.percentile for pt in prediction.cdf]
            assert len(ps)==201 and ps==sorted(ps)
            assert 0<=ps[0]<=ps[-1]<=1
        else:
            ps=[p.probability for p in prediction.predicted_options]
            assert abs(sum(ps)-1)<1e-6
            assert all(0<=p<=1 for p in ps)
