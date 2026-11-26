"""Offline native G3 development input bridge, no live entrypoint.
Reuse frozen definitions, exact sources and F3 native aggregation.
Only synthetic responses; no real forecasting or confirmatory admission.
"""
import asyncio,hashlib,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
import nostream_free_f3 as f3
import g3_bls_resolution as bls
import g3_eurostat_development as eu
import g2_diverse_evidence as ev
import g3_eurostat_country_development as countries
import g3_cross_domain_development as cross

SPECS={
 ("bls","cpi"):(991001,"Will US seasonally adjusted CPI-U all-items increase by at least 0.3% in January 2027 relative to December 2026?"),
 ("bls","payroll"):(991002,"Will US seasonally adjusted total nonfarm payroll employment rise by at least 100 thousand in January 2027 relative to December 2026?"),
 ("bls","openings"):(991003,"Will US seasonally adjusted total nonfarm job openings be at least as high in January 2027 as in December 2026?"),
 ("eurostat","hicp"):(991004,"Will the French all-items HICP monthly rate of change for January 2027 be at least 0.3%?"),
 ("eurostat","retail"):(991005,"Will the French seasonally and calendar adjusted retail sales volume index increase by at least 0.5% in January 2027 relative to December 2026?"),
 ("eurostat","unemployment"):(991006,"Will the French seasonally adjusted unemployment rate rise by at least 0.1 percentage point in January 2027 relative to December 2026?")
}
COUNTRY_NAMES={"DE":"Germany","ES":"Spain","IT":"Italy","NL":"the Netherlands","PL":"Poland","SE":"Sweden"}
for i,(c,name) in enumerate(COUNTRY_NAMES.items()):
    SPECS[("country",c+":hicp")]=(991010+i*3,f"Will the all-items HICP monthly rate of change in {name} for January 2027 be at least 0.3%?")
    SPECS[("country",c+":retail")]=(991011+i*3,f"Will the seasonally and calendar adjusted retail sales volume index in {name} increase by at least 0.5% in January 2027 relative to December 2026?")
    SPECS[("country",c+":unemployment")]=(991012+i*3,f"Will the seasonally adjusted unemployment rate in {name} rise by at least 0.1 percentage point in January 2027 relative to December 2026?")
SPECS.update({
    ("cross","nao"):(991030,"Will the NOAA CPC monthly North Atlantic Oscillation index for January 2027 be at least zero?"),
    ("cross","oil"):(991031,"Will US commercial crude oil stocks excluding the Strategic Petroleum Reserve for the week ending January 15, 2027 be at least one million barrels lower than for January 8, 2027?"),
    ("cross","river"):(991032,"Will the complete seven-day mean daily discharge at USGS Potomac River Little Falls station 01646500 for January 11 through January 17, 2027 be at least 10,000 cubic feet per second?")
})
require_unique_qids=len({v[0] for v in SPECS.values()})==len(SPECS)
if not require_unique_qids:raise ValueError("duplicate local question IDs")
MOCK={f3.NEM:.2,f3.GPT:.5,f3.ERNIE:.8}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def prepare(family,key,root,expected):
    root=Path(root)
    if family=="bls":
        snapshot=(root/"source"/"bls-candidate.json").read_bytes()
        receipt=bls.prepare(key,snapshot)
        frozen=json.loads((root/"definition"/"bls-definition.json").read_bytes())
        rows=json.loads(snapshot)["rows"]
        source_hash=sha(snapshot)
        units=bls.SPECS[key]["label"]
    elif family=="eurostat":
        raw=(root/"source"/"eurostat-source.json").read_bytes()
        report=(root/"source"/"eurostat-report.json").read_bytes()
        receipt=eu.prepare(key,raw,report)
        frozen=json.loads((root/"definition"/"eurostat-definition.json").read_bytes())
        rows=json.loads(report)["rows"];source_hash=sha(raw)
        units=json.dumps(eu.SPECS[key]["filters"],sort_keys=True)
    elif family=="country":
        c,k=key.split(":")
        receipt=countries.prepare(c,root/"source")["results"][k]
        frozen=json.loads((root/"definition"/"country-definition.json").read_bytes())["results"][k]
        doc=json.loads((root/"source"/"country-result.json").read_bytes())["reports"][k]
        rows=doc["rows"];source_hash=sha((root/"source"/f"{c}-{k}-source.json").read_bytes())
        units=json.dumps(doc["spec"]["filters"],sort_keys=True)
    elif family=="cross":
        raw=(root/"source"/"cross-domain.json").read_bytes()
        receipt=cross.prepare(key,raw)
        frozen=json.loads((root/"definition"/"cross-domain-definition.json").read_bytes())
        rows=json.loads(raw)["rows"];source_hash=sha(raw)
        units=json.dumps(json.loads(raw)["spec"],sort_keys=True)
    else:raise ValueError("unknown family")
    require(receipt==frozen and receipt["definition_sha256"]==expected,"frozen definition mismatch")
    e=receipt["definition"]
    require(e["partition"]=="development_only" and not e["confirmatory_eligible"] and not e["inference_authorized"],"authority changed")
    require(e["forecast_before"]=="2027-01-01T00:00:00Z" and (all(t.startswith("2027-01-") for t in e["required_periods"]) if family=="cross" else e["target_month"]=="2027-01"),"event window")
    qid,question=SPECS[(family,key)]
    criteria="YES if the exact threshold stated in the question is met using the registered official data series. Use only the first successful eligible official response on UTC "+e["capture_date_utc"]+". Use the required periods and exact published values; no backfill. Missing or inadmissible data remain unresolved. Registered definition: "+json.dumps(e,sort_keys=True,separators=(",",":"))
    case={"id":e["id"],"qid":qid,"type":"binary","question":question,"criteria":criteria,"source":e["resolution_source"],"resolve":e["capture_date_utc"]+"T23:59:59Z"}
    q=ev.build_question(case).model_copy(update={"open_time":datetime(2026,11,26,tzinfo=timezone.utc)})
    evidence="G3_FROZEN_OBSERVATIONS definition_sha256="+expected+"; source="+e["resolution_source"]+"; historical observation units/filters="+units+"; rows="+json.dumps(rows,separators=(",",":"),sort_keys=True)
    return case,q,evidence,source_hash,receipt["baseline"]
async def run(family,key,root,expected):
    require(os.environ.get("OPENROUTER_API_KEY")=="dummy-offline" and not any(os.environ.get(k) for k in ("CEREBRAS_API_KEY","GEMINI_API_KEY","METACULUS_TOKEN","METACULUS_API_KEY")),"offline environment required")
    f3.f.assert_no_platform_credentials()
    case,q,evidence,source_hash,baseline=prepare(family,key,root,expected)
    try:prepare(family,key,root,"0"*64)
    except ValueError:pass
    else:raise AssertionError("changed definition admitted")
    f3.configure(case)
    calls=[]
    async def mock(self,prompt,*args,**kwargs):
        role=self.model
        require(role in MOCK and isinstance(prompt,str) and "G3_FROZEN_OBSERVATIONS" in prompt and expected in prompt,"unexpected prompt or auxiliary role")
        calls.append((role,sha(prompt.encode())))
        return "Synthetic fixture only.\n```json\n"+json.dumps({"question_type":"binary","posterior_prob":MOCK[role]})+"\n```"
    async def research(question):
        require(question.id_of_question==case["qid"],"wrong question")
        return evidence
    f=f3.f;x=f3.x
    with patch("socket.socket.connect",side_effect=AssertionError("network forbidden")),patch("socket.create_connection",side_effect=AssertionError("network forbidden")),f.publication_guard(),patch.object(f.GeneralLlm,"invoke",mock),patch.object(f.TemplateForecaster,"_make_prediction",x.capture_make),patch.object(f.TemplateForecaster,"_aggregate_predictions",x.capture_aggregate):
        models=[f.GeneralLlm(model=m,allowed_tries=1) for m in f3.ROSTER]
        util=f.GeneralLlm(model=f3.UTIL,allowed_tries=1)
        bot=f.TemplateForecaster(llms={"forecasters":models,"default":util,"parser":util,"researcher":util,"summarizer":util},research_provider=research,publish_reports_to_metaculus=False,skip_previously_forecasted_questions=False,aggregation_strategy=f.AggregationStrategy.MEDIAN,min_forecasters_to_publish=3,max_questions_per_run=1)
        reports=await bot.forecast_questions([q])
    require(len(reports)==1 and isinstance(reports[0],f.ForecastReport),"no native report")
    value=x.typed_value(reports[0].prediction,q)
    require(len(calls)==3 and {r for r,_ in calls}==set(MOCK) and len({h for _,h in calls})==1,"mock roles/prompt")
    require(x.TYPED_MEMBERS==MOCK and f3.valid_aggregation(case,q,x.TYPED_MEMBERS,x.AGGREGATIONS,value) and value==.5 and bot.alertable_count==0,"native mock aggregate")
    require(not f.attempted and not x.DIRECT,"unexpected real dispatch")
    result={"event_id":case["id"],"local_qid":case["qid"],"definition_sha256":expected,"historical_source_sha256":source_hash,"source_hash_scope":"archived_normalized_report" if family=="cross" else "existing_bridge_source_bytes","baseline":baseline,"synthetic_members":MOCK,"synthetic_aggregate":value,"common_mock_prompt_sha256":calls[0][1],"network_blocked":True,"inference_calls":0,"published":0,"actual_outcomes_scored":0,"confirmatory_eligible":False,"live_admitted":False,"status":"NATIVE_MOCK_DEVELOPMENT_BRIDGE_PASS"}
    Path("g3-development-bridge.json").write_text(json.dumps(result,sort_keys=True))
    print("G3_DEVELOPMENT_BRIDGE="+json.dumps(result,sort_keys=True))
if __name__=="__main__":asyncio.run(run(*sys.argv[1:]))
