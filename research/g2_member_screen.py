"""Single-role F3 ERNIE technical screen on the exact D06 replay prompt.
Default execution is offline. No publication, no repeat of successful roles,
no changes to F2, no automatic fallback, no live workflow activation here.
"""
import json, math, os, statistics, sys
from datetime import datetime, timezone, date
from pathlib import Path
from unittest.mock import patch
import nostream_free_f2 as x
import g2_d06_recovery_probe as recovery

f=x.f
MODEL="baidu/ernie-5.5-flash-preview:free"
PROVIDER="baidu"
LAST_SPENT_DAY=date(2026,11,25)
EVENT_START=date(2026,12,1)
MAX_ATTEMPTS=1

def admit(day, expected_day, authorized, key_meta, credits):
    recovery.require(authorized is True and expected_day==day.isoformat(),"new explicit date-bound admission absent")
    recovery.require(LAST_SPENT_DAY<day<EVENT_START,"fresh quota/pre-event window closed")
    recovery.require(key_meta.get("is_free_tier") is True and key_meta.get("usage")==0 and credits.get("total_credits")==credits.get("total_usage")==0,"zero-credit account not proved")
    quota=f.verified_quota(key_meta)
    recovery.require(quota["remaining"]>=MAX_ATTEMPTS+f.quota_reserve,"reserve")
    return quota

def configure_route():
    f.ROSTER=[MODEL];f.ALLOW={MODEL};f.MAX_ATTEMPTS=MAX_ATTEMPTS;f.ROUTED=True

def read_inputs():
    root=Path("original")
    original=recovery.verify_original(recovery.read_json(root/"g2-summary.json"),recovery.read_json(root/"ledger.json"),recovery.read_json(root/"direct-ledger.json"))
    return original,recovery.reconstruct_prompt_text()

def aggregate(original,role,p):
    recovery.require(original==recovery.ORIGINAL_BALLOTS and role==MODEL and role not in original,"wrong ballot identity")
    recovery.require(type(p) in (int,float) and math.isfinite(p) and 0<=p<=1,"invalid strict forecast")
    from metaculus_bot.constants import BINARY_PROB_MIN,BINARY_PROB_MAX
    from metaculus_bot.aggregation_strategies import aggregate_binary_median
    published=max(BINARY_PROB_MIN,min(BINARY_PROB_MAX,p))
    combined=aggregate_binary_median([*original.values(),published])
    recovery.require(combined==round(statistics.median([*original.values(),published]),3),"median mismatch")
    return combined,published

def offline():
    configure_route()
    with patch("socket.socket.connect",side_effect=AssertionError("network forbidden")), patch("socket.create_connection",side_effect=AssertionError("network forbidden")),patch.object(f,"request",side_effect=AssertionError("network forbidden")):
        original,prompt=read_inputs()
        meta={"is_free_tier":True,"usage":0,"free_model_daily_requests":{"limit":50,"used":0,"remaining":50}}
        credit={"total_credits":0,"total_usage":0}
        next_day=date(2026,11,26)
        assert admit(next_day,"2026-11-26",True,meta,credit)["remaining"]==50
        for day,expected,auth,km,cr in (
            (LAST_SPENT_DAY,"2026-11-25",True,meta,credit),
            (EVENT_START,"2026-12-01",True,meta,credit),
            (next_day,"2026-11-27",True,meta,credit),
            (next_day,"2026-11-26",False,meta,credit),
            (next_day,"2026-11-26",True,dict(meta,usage=.001),credit),
            (next_day,"2026-11-26",True,meta,dict(credit,total_credits=1)),
            (next_day,"2026-11-26",True,dict(meta,free_model_daily_requests={"limit":50,"used":40,"remaining":10}),credit),
        ):
            try:admit(day,expected,auth,km,cr)
            except (ValueError,f.StopBudget):pass
            else:raise AssertionError("unsafe admission")
        z={"prompt":"0","completion":"0","request":"0"}
        routes=f.zero_routes({"id":MODEL,"endpoints":[{"tag":PROVIDER,"pricing":z},{"tag":"paid","pricing":dict(z,prompt="1")}]},MODEL)
        assert routes==[PROVIDER]
        f.free_routes[MODEL]=routes
        f.catalog[MODEL]={"top_provider":{"max_completion_tokens":24576}}
        payload=f.payload_for(MODEL,prompt)
        assert payload["model"]==MODEL and payload["provider"]["only"]==[PROVIDER] and payload["provider"]["allow_fallbacks"] is False
        assert all(v==0 for v in payload["provider"]["max_price"].values())
        assert not any(k in payload for k in ("models","tools","plugins"))
        assert aggregate(original,MODEL,.12)==(.05,.12)
        for role,p in ((x.GPT,.12),(MODEL,True),(MODEL,float("nan")),(MODEL,1.1)):
            try:aggregate(original,role,p)
            except ValueError:pass
            else:raise AssertionError("invalid ballot")
        assert not f.attempted
    print("F3_SCREEN_OFFLINE_PASS="+json.dumps({"model":MODEL,"provider":PROVIDER,"source_prompt":recovery.PROMPT,"earliest_utc_day":"2026-11-26","inference_calls":0,"native_pipeline_pass":False,"published":0,"live_admitted":False}))

def live():
    f.assert_no_platform_credentials()
    day=datetime.now(timezone.utc).date()
    # The early date/authorization check occurs BEFORE even metadata network.
    expected=os.getenv("NOSTREAM_SCREEN_EXPECTED_UTC_DAY")
    authorized=os.getenv("NOSTREAM_SCREEN_LIVE_AUTHORIZED")=="true"
    recovery.require(authorized and expected==day.isoformat() and LAST_SPENT_DAY<day<EVENT_START,"not admitted")
    original,prompt=read_inputs()
    configure_route()
    before=f.get_meta("/key");credits=f.get_meta("/credits")
    f.quota_start=admit(day,expected,authorized,before,credits)
    f.quota_day=day.isoformat()
    f.verify_catalog();f.discover_routes()
    recovery.require(f.free_routes.get(MODEL)==[PROVIDER],"exact endpoint changed")
    recovery.require(not f.attempted and not f.stopped,"already used")
    content=f.invoke_sync(MODEL,prompt)
    parsed=f.parse_structured_block(content,"binary")
    recovery.require(isinstance(parsed,f.BinaryStructured),"strict schema missing")
    recovery.require(len(f.attempted)==1 and len(f.ledger)==1 and f.ledger[0].get("returned_model")==MODEL and f.ledger[0].get("cost")==0 and f.ledger[0].get("prompt_sha256")==recovery.PROMPT,"receipt mismatch")
    after=f.get_meta("/key")
    q=f.verified_quota(after)
    recovery.require(not f.stopped and after.get("usage")==0 and q["limit"]==f.quota_start["limit"] and q["used"]>=f.quota_start["used"] and datetime.now(timezone.utc).date()==day,"post quota")
    combined,p=aggregate(original,MODEL,parsed.posterior_prob)
    # Diagnostic typed aggregation only, not F2 or native report/qualification.
    result={"candidate":"F3-ERNIE-D06-replay","original_run":recovery.SOURCE_RUN,"prompt_sha256":recovery.PROMPT,"new_model":MODEL,"new_ballot":p,"typed_median":combined,"inference_calls":1,"original_F2_failure_preserved":True,"native_pipeline_pass":False,"published":0,"predictive_superiority":"UNKNOWN"}
    (f.OUT/"f3-screen.json").write_text(json.dumps(result,sort_keys=True))
    print("F3_SCREEN_RESULT="+json.dumps(result,sort_keys=True))

if __name__=="__main__":
    if sys.argv[1:]==["--live"]:live()
    elif not sys.argv[1:]:offline()
    else:raise SystemExit("unsupported arguments")
