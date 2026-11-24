"""F2 feasibility: reuse pinned No-Stream engine with three explicitly mapped transports.
Public BLS evidence only; no contest credentials, no purchases or paid fallback.
Cerebras trial authorization is not an independently verified monetary hard cap.
"""
import asyncio, hashlib, json, math, os, statistics, threading, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
import nostream_free_f0 as f

NEM="openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
GPT="openrouter/openai/gpt-oss-120b"
GEM="openrouter/google/gemma-4-26b-a4b-it:free"
UTIL="openrouter/google/gemma-4-26b-a4b-it"
ROSTER=(NEM,GPT,GEM)
ROUTES={GPT:("cerebras","gpt-oss-120b",16384),GEM:("google","gemma-4-26b-a4b-it",24576),UTIL:("google","gemma-4-26b-a4b-it",4096)}
OUT=Path("free-results")
DIRECT=[]
LOCK=threading.Lock()
seen=set()
completed={}
closing=False
GEM_RETRY_DELAYS=(10,25)
GEM_RETRY_WINDOW=120
G2_GOOGLE_SOCKET_TIMEOUT=300
QUESTION_TYPE=os.getenv("NOSTREAM_QUESTION_TYPE","binary")
G2=os.getenv("NOSTREAM_G2")=="true"
TYPED_MEMBERS={}
NEM_TYPED={}
AGGREGATIONS=[]
def direct_payload(role,prompt):
    if role not in ROUTES or not isinstance(prompt,str) or len(prompt.encode())>29952:
        raise f.StopBudget("unapproved direct role or prompt")
    provider,model,cap=ROUTES[role]
    if provider=="cerebras":
        return "https://api.cerebras.ai/v1/chat/completions",{"model":model,"messages":[{"role":"user","content":prompt}],"max_completion_tokens":cap,"stream":False}
    return "https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent",{"contents":[{"role":"user","parts":[{"text":prompt}]}],"generationConfig":{"maxOutputTokens":cap,"candidateCount":1}}
def direct_request(role,prompt):
    provider,model,cap=ROUTES[role]
    url,payload=direct_payload(role,prompt)
    if provider=="cerebras":
        if os.getenv("NOSTREAM_CEREBRAS_TRIAL_AUTHORIZED")!="true":raise f.StopBudget("trial not authorized")
        key=os.environ["CEREBRAS_API_KEY"];headers={"Authorization":"Bearer "+key}
    else:
        key=os.environ["GEMINI_API_KEY"];headers={"x-goog-api-key":key}
    if not key:raise f.StopBudget("missing direct credential")
    headers.update({"Accept":"application/json","Content-Type":"application/json"})
    req=urllib.request.Request(url,headers=headers,data=json.dumps(payload).encode())
    timeout=G2_GOOGLE_SOCKET_TIMEOUT if G2 and role==GEM else 150
    with f.OPENER.open(req,timeout=timeout) as r:
        body=json.loads(r.read(8_000_000))
        rates={k.lower():int(v) for k,v in r.headers.items() if k.lower() in ("x-ratelimit-limit-requests-minute","x-ratelimit-limit-tokens-minute","x-ratelimit-limit-tokens-day") and v.isdigit()}
        return body,rates
def bounded_direct_request(role,prompt,rec):
    # A successful response is never repeated. Only explicit transient 503 on
    # this exact free Gemma role may retry; no model or provider fallback.
    start=time.monotonic()
    rec["dispatches"]=[]
    for index in range(1+(len(GEM_RETRY_DELAYS) if role==GEM else 0)):
        attempt={"number":index+1,"issued_at":datetime.now(timezone.utc).isoformat()}
        rec["dispatches"].append(attempt)
        try:
            body,rates=direct_request(role,prompt)
            attempt["http"]=200
            return body,rates
        except urllib.error.HTTPError as e:
            attempt["http"]=e.code
            if role!=GEM or e.code!=503 or index>=len(GEM_RETRY_DELAYS):raise
            hint=(e.headers or {}).get("Retry-After")
            if hint is not None and (not isinstance(hint,str) or not hint.isdigit() or len(hint)>3):raise
            delay=max(GEM_RETRY_DELAYS[index],int(hint or 0))
            if delay>60 or time.monotonic()-start+delay>=GEM_RETRY_WINDOW:raise
            attempt["retry_wait_seconds"]=delay
            print("F2_GEMMA_RETRY="+json.dumps(attempt),flush=True)
            time.sleep(delay)
            with LOCK:
                if closing:raise f.StopBudget("run closed before retry")
        except Exception as e:
            attempt["error"]=type(e).__name__
            raise
    raise f.StopBudget("retry exhausted")

def invoke_direct(role,prompt):
    provider,model,cap=ROUTES[role]
    direct_payload(role,prompt)
    with LOCK:
        if closing:raise f.StopBudget("closed direct role")
        digest=hashlib.sha256(prompt.encode()).hexdigest()
        # Distinct auxiliary extraction prompts are budgeted independently,
        # while every forecaster retains its single exact prompt identity.
        slot=(role,digest) if G2 and role==UTIL else role
        if slot in completed:
            old_digest,content=completed[slot]
            if digest!=old_digest:raise f.StopBudget("different prompt for completed role")
            print("F2_CACHE_HIT="+json.dumps({"role":role,"prompt_sha256":digest}),flush=True)
            return content
        if slot in seen:raise f.StopBudget("duplicate in-flight or failed role")
        if G2 and role==UTIL and sum(isinstance(k,tuple) and k[0]==UTIL for k in seen)>=3:
            raise f.StopBudget("auxiliary extraction budget exhausted")
        seen.add(slot)
        rec={"role":role,"provider":provider,"requested_model":model,"max_tokens":cap,"prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),"issued_at":datetime.now(timezone.utc).isoformat(),"billing_basis":"trial-attested-not-invoice-verified" if provider=="cerebras" else "Gemma free-only public price"}
        DIRECT.append(rec)
    start=time.monotonic()
    try:
        body,rates=bounded_direct_request(role,prompt,rec)
        if provider=="cerebras":
            choice=body["choices"][0]
            returned=body.get("model");finish=choice.get("finish_reason");content=choice["message"].get("content") or ""
            usage=body.get("usage",{});rid=body.get("id")
            rec["rate_headers"]=rates
            if rates.get("x-ratelimit-limit-requests-minute")!=5 or rates.get("x-ratelimit-limit-tokens-minute")!=30000 or rates.get("x-ratelimit-limit-tokens-day")!=1000000:
                raise f.StopBudget("unexpected Cerebras trial limits")
        else:
            choice=body["candidates"][0];returned=body.get("modelVersion")
            finish=choice.get("finishReason")
            content="".join(p.get("text","") for p in choice.get("content",{}).get("parts",[]) if not p.get("thought"))
            usage=body.get("usageMetadata",{});rid=body.get("responseId")
        rec.update({"returned_model":returned,"finish":finish,"id":rid,"usage":{k:v for k,v in usage.items() if type(v) is int},"response_sha256":hashlib.sha256(content.encode()).hexdigest()})
        if returned!=model or finish not in ("stop","STOP") or not content:raise RuntimeError("invalid direct output")
        if role in ROSTER:
            parsed=f.parse_structured_block(content,QUESTION_TYPE)
            if G2:
                # A transport-successful answer must reach the original extraction
                # ladder (strict block -> deterministic repair -> bounded parser).
                rec["strict_block_valid"]=parsed is not None
                if parsed is not None:rec["structured_forecast"]=parsed.model_dump(mode="json")
            elif QUESTION_TYPE=="binary":
                if not isinstance(parsed,f.BinaryStructured):raise RuntimeError("wrong structured type")
                rec["structured_probability"]=parsed.posterior_prob
            else:
                if parsed is None:raise RuntimeError("missing valid structured forecast")
                rec["structured_forecast"]=parsed.model_dump(mode="json")
        with LOCK:
            completed[slot]=(rec["prompt_sha256"],content)
        return content
    except urllib.error.HTTPError as e:
        rec["http"]=e.code
        raise RuntimeError("direct HTTP "+str(e.code)) from None
    except Exception as e:
        rec["error"]=type(e).__name__
        raise RuntimeError("direct inference failed: "+type(e).__name__) from None
    finally:
        rec["seconds"]=round(time.monotonic()-start,2)
        with LOCK:
            (OUT/"direct-ledger.json").write_text(json.dumps(DIRECT,sort_keys=True))
            print("F2_DIRECT_LEDGER="+json.dumps(DIRECT,sort_keys=True),flush=True)
async def invoke(self,prompt,*args,**kwargs):
    role=self.model
    if role==NEM:
        content=await asyncio.to_thread(f.invoke_sync,role,prompt)
        if G2:
            parsed=f.parse_structured_block(content,QUESTION_TYPE)
            NEM_TYPED["strict_block_valid"]=parsed is not None
            if parsed is not None:NEM_TYPED["structured_forecast"]=parsed.model_dump(mode="json")
        return content
    if role not in ROUTES:raise f.StopBudget("unknown F2 role")
    return await asyncio.to_thread(invoke_direct,role,prompt)
def build_question():
    from forecasting_tools import MultipleChoiceQuestion, NumericQuestion
    common={"open_time":datetime.now(timezone.utc)-timedelta(days=1),"scheduled_resolution_time":datetime(2027,2,1,tzinfo=timezone.utc),"background_info":"Official BLS CPI-U all items US city average not seasonally adjusted.","fine_print":"Initial BLS release only. Local noncontest technical fixture; not an independent predictive cohort."}
    if QUESTION_TYPE=="binary":
        return f.BinaryQuestion(question_text="Will US CPI-U inflation for November 2026 be at least 3.5% year over year?",id_of_question=990003,id_of_post=990003,resolution_criteria="YES if the first BLS November 2026 release reports the all-items 12-month CPI-U change as at least 3.5 percent; otherwise NO. https://www.bls.gov/news.release/cpi.htm",**common)
    if QUESTION_TYPE=="multiple_choice":
        return MultipleChoiceQuestion(question_text="In which range will the US CPI-U December 2026 year-over-year inflation rate fall?",id_of_question=990004,id_of_post=990004,options=["Below 2.5%","2.5% to below 3.5%","3.5% or higher"],resolution_criteria="First BLS December 2026 release, all-items CPI-U 12-month percentage change. Below 2.5; 2.5 inclusive to 3.5 exclusive; 3.5 inclusive or higher. https://www.bls.gov/news.release/cpi.htm",**common)
    if QUESTION_TYPE=="numeric":
        return NumericQuestion(question_text="What will the US CPI-U all-items index level be for December 2026?",id_of_question=990005,id_of_post=990005,resolution_criteria="First BLS release of December 2026 all-items CPI-U US city average not seasonally adjusted, 1982-84=100. https://www.bls.gov/news.release/cpi.htm",unit_of_measure="index points",lower_bound=250.0,upper_bound=450.0,open_lower_bound=True,open_upper_bound=True,**common)
    raise f.StopBudget("unapproved question type")

def typed_value(prediction,question):
    if QUESTION_TYPE=="binary":
        if isinstance(prediction,bool) or not isinstance(prediction,(int,float)) or not math.isfinite(prediction) or not 0<=prediction<=1:raise ValueError("invalid binary")
        return float(prediction)
    if QUESTION_TYPE=="multiple_choice":
        opts=prediction.predicted_options
        value={o.option_name:o.probability for o in opts}
        if len(opts)!=len(value) or set(value)!=set(question.options) or not all(math.isfinite(p) and 0<=p<=1 for p in value.values()) or abs(sum(value.values())-1)>1e-6:raise ValueError("invalid MC ballot")
        return value
    if QUESTION_TYPE=="numeric":
        points=list(prediction.cdf)
        probs=[p.percentile for p in points]
        if len(probs)!=201 or not all(math.isfinite(p) and 0<=p<=1 for p in probs) or probs!=sorted(probs):raise ValueError("invalid numeric CDF")
        return probs
    raise ValueError("unknown type")

ORIGINAL_MAKE=f.TemplateForecaster._make_prediction
ORIGINAL_AGG=f.TemplateForecaster._aggregate_predictions

async def capture_make(self,question,research,llm_to_use=None,chart_b64=None):
    result=await ORIGINAL_MAKE(self,question,research,llm_to_use,chart_b64)
    role=llm_to_use.model if llm_to_use else None
    if role not in ROSTER or role in TYPED_MEMBERS:raise f.StopBudget("unexpected member identity")
    value=typed_value(result.prediction_value,question) if hasattr(result,"prediction_value") else typed_value(result.prediction,question)
    TYPED_MEMBERS[role]=value
    return result

async def capture_aggregate(self,predictions,question,*args,**kwargs):
    # Record actual upstream aggregation input and output without replacing its algorithm.
    inputs=[typed_value(p,question) for p in predictions]
    result=await ORIGINAL_AGG(self,predictions,question,*args,**kwargs)
    AGGREGATIONS.append({"inputs":inputs,"output":typed_value(result,question)})
    return result

def validate_g2(report,question,degradation,err,before,after):
    members=TYPED_MEMBERS
    direct={r["role"]:r for r in DIRECT if r["role"] in ROSTER and r.get("finish") in ("stop","STOP") and "error" not in r}
    nem=[r for r in f.ledger if r.get("finish")=="stop" and r.get("cost")==0 and r.get("returned_model")==NEM.removeprefix("openrouter/")]
    hashes={r["prompt_sha256"] for r in nem}|{r["prompt_sha256"] for r in direct.values()}
    value=typed_value(report.prediction,question) if report is not None else None
    matching=[a for a in AGGREGATIONS if len(a["inputs"])==3]
    agg_ok=False
    if len(matching)==1 and set(members)==set(ROSTER):
        a=matching[0]
        same_members=sorted(json.dumps(v,sort_keys=True) for v in a["inputs"])==sorted(json.dumps(v,sort_keys=True) for v in members.values())
        if QUESTION_TYPE=="binary":
            expected=round(statistics.median(members.values()),3)
            agg_ok=same_members and value==a["output"] and abs(value-expected)<=.001
        elif QUESTION_TYPE=="multiple_choice":
            from metaculus_bot.mc_processing import clamp_and_renormalize_probs
            names=list(question.options)
            expected=dict(zip(names,clamp_and_renormalize_probs([statistics.median(v[n] for v in members.values()) for n in names]),strict=True))
            agg_ok=same_members and value==a["output"] and max(abs(value[n]-expected[n]) for n in names)<=1e-6
        else:
            # Verify actual typed input count, member identity, valid monotone 201-point
            # distribution and report equality. Numeric upstream interpolation/tail floor
            # is NOT independently reimplemented; don't call this independent arithmetic.
            agg_ok=same_members and value==a["output"]
    try:
        quota=f.verified_quota(after)
        quota_ok=quota["limit"]==f.quota_start["limit"] and quota["used"]>=f.quota_start["used"] and f.quota_day==datetime.now(timezone.utc).date().isoformat()
    except f.StopBudget:quota_ok=False
    passed=(set(members)==set(ROSTER) and len(nem)==1 and set(direct)=={GPT,GEM} and len(hashes)==1 and bool(NEM_TYPED) and agg_ok and degradation==0 and err is None and quota_ok and not f.stopped and before.get("usage")==after.get("usage")==0)
    summary={"candidate":"F2","gate":"G2","question_type":QUESTION_TYPE,"source_sha":f.PIN,"members":members,"report":value,"aggregation_verified":agg_ok,"numeric_independent_recomputation":False if QUESTION_TYPE=="numeric" else None,"strict_block_valid":{NEM:NEM_TYPED.get("strict_block_valid"),**{role:r.get("strict_block_valid") for role,r in direct.items()}},"common_prompt":len(hashes)==1,"degradation":degradation,"engine_error":err,"technical_pipeline_pass":passed,"openrouter_after":after,"openrouter_cost_usd":sum(float(r["cost"]) for r in f.ledger if r.get("cost") is not None),"direct_billing_independently_verified":False,"published":0,"research_scope":"public BLS only","attempts":len(f.attempted)+sum(len(r.get("dispatches",[])) for r in DIRECT)}
    (OUT/"g2-summary.json").write_text(json.dumps(summary,sort_keys=True))
    (OUT/"g2-aggregations.json").write_text(json.dumps(AGGREGATIONS,sort_keys=True))
    print("G2_RESULT="+json.dumps(summary,sort_keys=True),flush=True)
    if not passed:raise SystemExit("BLOCK: G2 typed integration incomplete")

async def main():
    global closing
    f.assert_no_platform_credentials()
    if os.getenv("NOSTREAM_F2_AUTHORIZED")!="true":raise f.StopBudget("F2 not authorized")
    if os.getenv("NOSTREAM_CEREBRAS_TRIAL_AUTHORIZED")!="true" or not all(os.getenv(k) for k in ("GEMINI_API_KEY","CEREBRAS_API_KEY")):
        raise f.StopBudget("direct credentials or trial attestation absent")
    before=f.get_meta("/key");credits=f.get_meta("/credits")
    print("F2_OPENROUTER_BEFORE="+json.dumps({"key":before,"credits":credits}),flush=True)
    if before.get("is_free_tier") is not True or before.get("usage")!=0 or credits.get("total_credits")!=0 or credits.get("total_usage")!=0:raise f.StopBudget("OpenRouter account mismatch")
    f.quota_start=f.verified_quota(before);f.quota_day=datetime.now(timezone.utc).date().isoformat()
    if f.quota_start["remaining"]<11:raise f.StopBudget("OpenRouter reserve")
    f.ROSTER=[NEM.removeprefix("openrouter/")];f.ALLOW=set(f.ROSTER);f.MAX_ATTEMPTS=1
    f.verify_catalog()
    # Independent direct model metadata read; no inference if identity mismatch.
    for role in (GPT,GEM):
        provider,model,_=ROUTES[role]
        if provider=="cerebras":url="https://api.cerebras.ai/v1/models/"+model;headers={"Authorization":"Bearer "+os.environ["CEREBRAS_API_KEY"]}
        else:url="https://generativelanguage.googleapis.com/v1beta/models/"+model;headers={"x-goog-api-key":os.environ["GEMINI_API_KEY"]}
        with f.OPENER.open(urllib.request.Request(url,headers=headers),timeout=20) as r:meta=json.load(r)
        if provider=="cerebras" and meta.get("id")!=model:raise f.StopBudget("Cerebras identity")
        if provider=="google" and (meta.get("name")!="models/"+model or meta.get("outputTokenLimit",0)<24576 or "generateContent" not in meta.get("supportedGenerationMethods",[])):raise f.StopBudget("Gemma capability")
    q=f.BinaryQuestion(question_text="Will US CPI-U inflation for December 2026 be at least 3.0% year over year?",id_of_question=990002,id_of_post=990002,background_info="BLS all-items CPI-U US city average not seasonally adjusted.",resolution_criteria="YES if first BLS release for December 2026 reports all-items 12-month inflation of at least 3.0%; otherwise NO. Source https://www.bls.gov/news.release/cpi.htm",fine_print="Use initial release. Synthetic local noncontest question.",open_time=datetime.now(timezone.utc)-timedelta(days=1),scheduled_resolution_time=datetime(2027,2,1,tzinfo=timezone.utc))
    if G2:q=build_question()
    src="https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0"
    rows=f.request(src)["Results"]["series"][0]["data"]
    rows=[x for x in rows if (int(x["year"]),x["period"])<(2026,"M12") and x["period"]!="M13"][:24]
    assert len(rows)>=12
    evidence="Official BLS data "+src+"\n"+json.dumps(rows)
    (OUT/"evidence.sha256").write_text(hashlib.sha256(evidence.encode()).hexdigest())
    async def research(question):return evidence
    models=[f.GeneralLlm(model=m,allowed_tries=1) for m in ROSTER]
    util=f.GeneralLlm(model=UTIL,allowed_tries=1)
    report=None;err=None;degradation=None
    from contextlib import ExitStack
    with ExitStack() as stack:
        stack.enter_context(f.publication_guard())
        stack.enter_context(patch.object(f.GeneralLlm,"invoke",invoke))
        if G2:
            stack.enter_context(patch.object(f.TemplateForecaster,"_make_prediction",capture_make))
            stack.enter_context(patch.object(f.TemplateForecaster,"_aggregate_predictions",capture_aggregate))
        try:
            bot=f.TemplateForecaster(llms={"forecasters":models,"default":util,"parser":util,"researcher":util,"summarizer":util},research_provider=research,publish_reports_to_metaculus=False,skip_previously_forecasted_questions=False,aggregation_strategy=f.AggregationStrategy.MEDIAN,min_forecasters_to_publish=3,max_questions_per_run=1)
            reports=await bot.forecast_questions([q])
            if len(reports)==1 and isinstance(reports[0],f.ForecastReport):report=reports[0]
            degradation=bot.alertable_count
        except Exception as e:err=type(e).__name__
        finally:
            with LOCK:closing=True
    if G2:
        return validate_g2(report,q,degradation,err,before,f.get_meta("/key"))
    members={NEM:r["structured_probability"] for r in f.ledger if isinstance(r.get("structured_probability"),(int,float))}
    members.update({r["role"]:r["structured_probability"] for r in DIRECT if r["role"] in ROSTER and isinstance(r.get("structured_probability"),(int,float))})
    hashes={r["prompt_sha256"] for r in f.ledger if "structured_probability" in r}|{r["prompt_sha256"] for r in DIRECT if r["role"] in ROSTER and "structured_probability" in r}
    median=f.aggregate_binary_median(list(members.values())) if set(members)==set(ROSTER) else None
    p=getattr(report,"prediction",None)
    after=f.get_meta("/key")
    passed=(isinstance(p,float) and math.isfinite(p) and median is not None and abs(p-median)<=.001 and len(hashes)==1 and degradation==0 and not f.stopped and after.get("usage")==0 and all(r.get("cost")==0 for r in f.ledger))
    summary={"candidate":"F2","source_sha":f.PIN,"members":members,"common_prompt":len(hashes)==1,"expected_median":median,"upstream_report_probability":p,"degradation":degradation,"engine_error":err,"technical_pipeline_pass":passed,"openrouter_cost_usd":sum(float(r["cost"]) for r in f.ledger if r.get("cost") is not None),"openrouter_after":after,"direct_billing_independently_verified":False,"research_scope":"public BLS only, not complete No-Stream research parity","published":0,"attempts":len(f.attempted)+sum(len(r.get("dispatches",[])) for r in DIRECT),"direct_roles":len(DIRECT)}
    print("F2_RESULT="+json.dumps(summary,sort_keys=True),flush=True)
    (OUT/"summary.json").write_text(json.dumps(summary,sort_keys=True))
    if not passed:raise SystemExit("BLOCK: F2 technical integration incomplete")
if __name__=="__main__":asyncio.run(main())
