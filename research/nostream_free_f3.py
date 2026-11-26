"""F3 native No-Stream technical pilot; reuse F2 transport/extraction hooks.

Three new January event fixtures, frozen public pre-event evidence only.
No competition submission, paid fallback, or proof of predictive skill.
"""
import asyncio, hashlib, json, math, os, statistics, sys, threading, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import nostream_free_f2 as x
import g2_diverse_evidence as ev

f=x.f
NEM=x.NEM; GPT=x.GPT; UTIL=x.UTIL
ERNIE="openrouter/baidu/ernie-5.5-flash-preview:free"
ROSTER=(NEM,GPT,ERNIE)
OR_MODELS={NEM:"nvidia",ERNIE:"baidu"}
CASE_SPECS={
 "F301":("D01","25abefef6ef13f8346a5669cc52e52981867f5e9a58215606daa167e67a74815",990031,"2027-02-28T23:59:59Z","percent, seasonally adjusted U-3"),
 "F302":("D05","320b3e7a322aa5b4831778f959b4b260ae45ca0ff1fbfe0b0a0cbdf5d8061721",990032,"2027-02-28T23:59:59Z","observed monthly sunspot number"),
 "F303":("D03","c69d9bba0dd7f22761d0788188926368935ab79f0b993202ed7020cbe1f16804",990033,"2027-02-15T23:59:59Z","count of magnitude >=6 earthquakes per UTC month"),
}
DAY="2026-11-26"
CASE=os.environ["NOSTREAM_F3_CASE"]
OUT=Path("free-results")
CACHE={}
LOCK=threading.Lock()
UTIL_DIGEST=None
CLOSED=False

def require(ok,msg):
    if not ok:raise f.StopBudget(msg)

def input_fixture():
    source,digest,qid,resolve,units=CASE_SPECS[CASE]
    raw=Path("diverse-input/snapshot.json").read_bytes()
    require(hashlib.sha256(raw).hexdigest()==digest,"snapshot hash")
    doc=json.loads(raw)
    original=ev.load_case(source)
    require(doc["case"]==original and doc["observation_cutoff"]==ev.CUTOFF and doc["retrieved_at"].startswith("2026-11-25T"),"snapshot provenance")
    rows=doc["observations"]
    require(bool(rows) and rows==sorted(rows) and len({r[0] for r in rows})==len(rows) and all(r[0]<=ev.CUTOFF and type(r[1]) in (float,int) and math.isfinite(r[1]) for r in rows),"invalid evidence")
    case=dict(original,id=CASE,qid=qid,resolve=resolve)
    case["question"]=original["question"].replace("December 2026","January 2027")
    case["criteria"]=original["criteria"].replace("December 2026","January 2027").replace("2027-01-31 UTC","2027-02-28 UTC").replace("2027-01-15 UTC","2027-02-15 UTC").replace("[2026-12-01T00:00:00Z,2027-01-01T00:00:00Z)","[2027-01-01T00:00:00Z,2027-02-01T00:00:00Z)")
    require(case["question"]!=original["question"] and "January 2027" in case["question"] and case["criteria"]!=original["criteria"],"not new event")
    q=ev.build_question(case)
    q=q.model_copy(update={"open_time":datetime(2026,11,26,tzinfo=timezone.utc)})
    evidence="Public source "+case["source"]+"; observation units: "+units+"; retrieved "+doc["retrieved_at"]+". Observations (period, value): "+json.dumps(rows,separators=(",",":"))
    return case,q,evidence,digest

def configure(case):
    require(x.G2 and not x.DIVERSE_CASE and x.QUESTION_TYPE==case["type"],"wrong mode")
    x.ROSTER=ROSTER
    x.ROUTES={k:v for k,v in x.ROUTES.items() if k in (GPT,UTIL)}
    f.ROSTER=[role.removeprefix("openrouter/") for role in OR_MODELS]
    f.ALLOW=set(f.ROSTER);f.MAX_ATTEMPTS=2;f.ROUTED=True

def admit(day, authorized, key, credits):
    require(authorized and day==DAY,"fresh explicit date admission required")
    require(key.get("is_free_tier") is True and key.get("usage")==0 and credits.get("total_credits")==credits.get("total_usage")==0,"not zero-credit")
    quota=f.verified_quota(key)
    require(quota["remaining"]>=f.quota_reserve+2,"reserve")
    return quota

def reserve_aux(prompt):
    global UTIL_DIGEST
    digest=hashlib.sha256(prompt.encode()).hexdigest()
    with LOCK:
        require(not CLOSED,"closed")
        require(UTIL_DIGEST is None or UTIL_DIGEST==digest,"auxiliary budget")
        UTIL_DIGEST=digest

def invoke_router(role,prompt):
    digest=hashlib.sha256(prompt.encode()).hexdigest()
    with LOCK:
        require(not CLOSED,"closed")
        if role in CACHE:
            old,value=CACHE[role]
            require(old==digest,"prompt changed for completed role")
            return value
        # f.invoke_sync enforces one dispatch per approved role even on failure.
    answer=f.invoke_sync(role,prompt)
    with LOCK:CACHE[role]=(digest,answer)
    return answer

async def invoke(self,prompt,*args,**kwargs):
    role=self.model
    if role in OR_MODELS:return await asyncio.to_thread(invoke_router,role,prompt)
    if role==UTIL:reserve_aux(prompt)
    require(role in (GPT,UTIL),"unknown role")
    return await asyncio.to_thread(x.invoke_direct,role,prompt)

def valid_aggregation(case,q,members,aggs,report):
    if report is None or set(members)!=set(ROSTER):return False
    if len(aggs)!=1 or len(aggs[0]["inputs"])!=3:return False
    a=aggs[0]
    if sorted(json.dumps(v,sort_keys=True) for v in a["inputs"])!=sorted(json.dumps(v,sort_keys=True) for v in members.values()) or report!=a["output"]:return False
    if case["type"]=="binary":return abs(report-round(statistics.median(members.values()),3))<=.001
    if case["type"]=="multiple_choice":
        from metaculus_bot.mc_processing import clamp_and_renormalize_probs
        expected=dict(zip(q.options,clamp_and_renormalize_probs([statistics.median(v[n] for v in members.values()) for n in q.options]),strict=True))
        return max(abs(report[n]-expected[n]) for n in q.options)<=1e-6
    return len(report)==201 and report==sorted(report) and all(math.isfinite(p) and 0<=p<=1 for p in report)

def offline():
    global UTIL_DIGEST
    case,q,evidence,digest=input_fixture()
    configure(case)
    meta={"is_free_tier":True,"usage":0,"free_model_daily_requests":{"limit":50,"used":0,"remaining":50}}
    credits={"total_credits":0,"total_usage":0}
    require(admit(DAY,True,meta,credits)["remaining"]==50,"admission")
    for day,auth,k,c in (("2026-11-25",True,meta,credits),(DAY,False,meta,credits),(DAY,True,dict(meta,usage=.01),credits),(DAY,True,meta,dict(credits,total_credits=1)),(DAY,True,dict(meta,free_model_daily_requests={"limit":50,"used":39,"remaining":11}),credits)):
        try:admit(day,auth,k,c)
        except f.StopBudget:pass
        else:raise AssertionError("unsafe admission")
    reserve_aux("first");reserve_aux("first")
    try:reserve_aux("second")
    except f.StopBudget:pass
    else:raise AssertionError("second utility admitted")
    UTIL_DIGEST=None
    with patch.object(f,"invoke_sync",return_value="fixture") as call:
        require(invoke_router(ERNIE,"same")==invoke_router(ERNIE,"same"),"cache")
        require(call.call_count==1,"duplicate dispatch")
        try:invoke_router(ERNIE,"different")
        except f.StopBudget:pass
        else:raise AssertionError("different prompt reuse")
    CACHE.clear()
    if case["type"]=="binary":v=.5
    elif case["type"]=="multiple_choice":v=dict(zip(q.options,[.2,.3,.5]))
    else:v=[i/200 for i in range(201)]
    members=dict.fromkeys(ROSTER,v);agg=[{"inputs":[v,v,v],"output":v}]
    require(valid_aggregation(case,q,members,agg,v),"valid aggregate")
    require(not valid_aggregation(case,q,{NEM:v,GPT:v},agg,v),"missing member accepted")
    require(not f.attempted and not x.DIRECT,"offline dispatch")
    print("F3_NATIVE_OFFLINE_PASS="+json.dumps({"case":CASE,"type":case["type"],"source":digest,"qid":q.id_of_question,"calls":0}))

async def live():
    global CLOSED
    f.assert_no_platform_credentials()
    require(os.getenv("NOSTREAM_F3_LIVE_AUTHORIZED")=="true" and datetime.now(timezone.utc).date().isoformat()==DAY,"live date gate")
    require(os.getenv("NOSTREAM_CEREBRAS_TRIAL_AUTHORIZED")=="true" and os.getenv("NOSTREAM_CEREBRAS_NO_RECHARGE_ATTESTED")=="true","trial attestation")
    require(all(os.getenv(k) for k in ("CEREBRAS_API_KEY","GEMINI_API_KEY","OPENROUTER_API_KEY")),"missing credential")
    case,q,evidence,digest=input_fixture();configure(case)
    before=f.get_meta("/key");credits=f.get_meta("/credits")
    f.quota_start=admit(DAY,True,before,credits);f.quota_day=DAY
    f.verify_catalog();f.discover_routes()
    require(all(f.free_routes.get(role.removeprefix("openrouter/"))==[provider] for role,provider in OR_MODELS.items()),"changed zero-price route")
    for url,headers,model in (("https://api.cerebras.ai/v1/models/gpt-oss-120b",{"Authorization":"Bearer "+os.environ["CEREBRAS_API_KEY"]},"gpt-oss-120b"),("https://generativelanguage.googleapis.com/v1beta/models/gemma-4-26b-a4b-it",{"x-goog-api-key":os.environ["GEMINI_API_KEY"]},"models/gemma-4-26b-a4b-it")):
        with f.OPENER.open(urllib.request.Request(url,headers=headers),timeout=20) as response:meta=json.load(response)
        require(meta.get("id",meta.get("name"))==model,"direct model identity")
    async def research(question):return evidence
    (OUT/"evidence.sha256").write_text(hashlib.sha256(evidence.encode()).hexdigest())
    models=[f.GeneralLlm(model=m,allowed_tries=1) for m in ROSTER]
    util=f.GeneralLlm(model=UTIL,allowed_tries=1)
    report=None;err=None;degradation=None
    with f.publication_guard(),patch.object(f.GeneralLlm,"invoke",invoke),patch.object(f.TemplateForecaster,"_make_prediction",x.capture_make),patch.object(f.TemplateForecaster,"_aggregate_predictions",x.capture_aggregate):
        try:
            bot=f.TemplateForecaster(llms={"forecasters":models,"default":util,"parser":util,"researcher":util,"summarizer":util},research_provider=research,publish_reports_to_metaculus=False,skip_previously_forecasted_questions=False,aggregation_strategy=f.AggregationStrategy.MEDIAN,min_forecasters_to_publish=3,max_questions_per_run=1)
            reports=await bot.forecast_questions([q])
            if len(reports)==1 and isinstance(reports[0],f.ForecastReport):report=reports[0]
            degradation=bot.alertable_count
        except Exception as e:err=type(e).__name__
        finally:
            with LOCK:CLOSED=True
            with x.LOCK:x.closing=True
    value=x.typed_value(report.prediction,q) if report is not None else None
    primary={r["model"]:r for r in f.ledger if r.get("finish")=="stop" and r.get("cost")==0 and r.get("returned_model")==r["model"]}
    gpt=[r for r in x.DIRECT if r["role"]==GPT and r.get("finish")=="stop" and r.get("returned_model")=="gpt-oss-120b" and "error" not in r]
    hashes={r["prompt_sha256"] for r in primary.values()}|{r["prompt_sha256"] for r in gpt}
    attempts=len(f.attempted)+sum(len(r.get("dispatches",[])) for r in x.DIRECT)
    after=f.get_meta("/key");quota=f.verified_quota(after)
    providers_ok=set(primary)==set(f.ROSTER) and all(str(primary[m].get("provider","")).casefold()==OR_MODELS["openrouter/"+m] for m in primary)
    aggregation_ok=valid_aggregation(case,q,x.TYPED_MEMBERS,x.AGGREGATIONS,value)
    passed=providers_ok and len(gpt)==1 and len(hashes)==1 and aggregation_ok and degradation==0 and err is None and len(f.attempted)==2 and len(f.ledger)==2 and attempts<=4 and not f.stopped and after.get("usage")==0 and quota["limit"]==f.quota_start["limit"] and quota["used"]>=f.quota_start["used"] and datetime.now(timezone.utc).date().isoformat()==DAY
    result={"candidate":"F3","case":CASE,"question_type":case["type"],"qid":q.id_of_question,"snapshot_sha256":digest,"source_sha":f.PIN,"members":x.TYPED_MEMBERS,"report":value,"aggregation_verified":aggregation_ok,"numeric_independent_recomputation":False if case["type"]=="numeric" else None,"common_prompt":len(hashes)==1,"technical_pipeline_pass":passed,"attempts":attempts,"openrouter_after":after,"openrouter_cost_usd":sum(float(r["cost"]) for r in f.ledger if r.get("cost") is not None),"direct_billing_independently_verified":False,"degradation":degradation,"engine_error":err,"published":0}
    (OUT/"f3-native-summary.json").write_text(json.dumps(result,sort_keys=True))
    (OUT/"f3-native-aggregations.json").write_text(json.dumps(x.AGGREGATIONS,sort_keys=True))
    print("F3_NATIVE_RESULT="+json.dumps(result,sort_keys=True),flush=True)
    if not passed:raise SystemExit("BLOCK: native F3 incomplete")
if __name__=="__main__":
    if sys.argv[1:]==["--live"]:asyncio.run(live())
    elif not sys.argv[1:]:offline()
    else:raise SystemExit("unsupported arguments")
