"""F2 G2 diverse-case inputs, public historical observations only, no LLM calls."""
import csv,hashlib,io,json,math,sys,urllib.request,urllib.parse
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

MANIFEST=Path(__file__).with_name("g2_diverse_cases.json")
CUTOFF="2026-11-24"
ALLOWED={"api.bls.gov","earthquake.usgs.gov","fred.stlouisfed.org","services.swpc.noaa.gov","data-api.ecb.europa.eu"}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
OPENER=urllib.request.build_opener(NoRedirect())
def load_case(case_id):
    manifest=json.loads(MANIFEST.read_text())
    assert manifest["cutoff"]==CUTOFF
    cases=manifest["cases"]
    assert len(cases)==6 and len({c["qid"] for c in cases})==6 and len({c["id"] for c in cases})==6
    assert Counter(c["type"] for c in cases)=={"binary":2,"multiple_choice":2,"numeric":2}
    assert manifest["max_total_attempts"]==6*manifest["max_attempts_per_case"]==30
    case=next(c for c in cases if c["id"]==case_id)
    assert case["resolve"]>"2026-12-31"
    return case
def fetch_public(url):
    p=urllib.parse.urlsplit(url)
    assert p.scheme=="https" and p.hostname in ALLOWED and p.port in (None,443) and not p.username and not p.password
    req=urllib.request.Request(url,headers={"User-Agent":"FutureEval-research-fixture/1.0","Accept":"*/*"})
    with OPENER.open(req,timeout=30) as r:
        body=r.read(2_000_001)
        assert r.status==200 and len(body)<=2_000_000
    return body
def normalize(case,body):
    adapter=case["adapter"]
    result=[]
    if adapter=="bls":
        obj=json.loads(body)
        assert obj["status"]=="REQUEST_SUCCEEDED"
        series=obj["Results"]["series"]
        assert len(series)==1 and series[0]["seriesID"]==case["series"]
        for r in series[0]["data"]:
            if r["period"]=="M13":continue
            month=r["year"]+"-"+r["period"][1:]
            if "2025-01"<=month<="2026-10":
                result.append([month,float(r["value"])])
        minimum=12
    elif adapter=="usgs":
        obj=json.loads(body); features=obj["features"]
        assert obj["metadata"]["count"]==len(features)<1000
        ids=set();counts=Counter()
        for event in features:
            p=event["properties"]
            t=datetime.fromtimestamp(p["time"]/1000,timezone.utc).strftime("%Y-%m-%d")
            if not "2026-01-01"<=t<"2026-11-01":continue
            assert p["type"]=="earthquake" and float(p["mag"])>=6 and event["id"] not in ids
            ids.add(event["id"]);counts[t[:7]]+=1
        result=[[f"2026-{m:02d}",counts[f"2026-{m:02d}"]] for m in range(1,11)]
        minimum=10
    elif adapter=="noaa":
        for r in json.loads(body):
            month=r["time-tag"][:7]
            if "2024-01"<=month<="2026-10" and r.get("ssn") is not None and float(r["ssn"])>=0:
                result.append([month,float(r["ssn"])])
        minimum=18
    elif adapter in ("fred","ecb"):
        for r in csv.DictReader(io.StringIO(body.decode("utf-8-sig"))):
            date=(r.get("observation_date") or r.get("DATE")) if adapter=="fred" else r.get("TIME_PERIOD")
            value=r[case["series"]] if adapter=="fred" else r["OBS_VALUE"]
            if date and "2026-06-01"<=date<=CUTOFF and value not in (".","",None):
                result.append([date,float(value)])
        minimum=30
    else:raise ValueError("unknown source adapter")
    assert len(result)>=minimum and len({r[0] for r in result})==len(result)
    assert all(math.isfinite(r[1]) for r in result)
    return sorted(result)
def snapshot(case_id,out):
    case=load_case(case_id)
    now=datetime.now(timezone.utc)
    # The events are prospective. Never retrieve post-event input.
    if now.date().isoformat()>="2026-12-01":raise RuntimeError("pre-event evidence window closed")
    raw=fetch_public(case["url"]); rows=normalize(case,raw)
    out.mkdir(parents=True,exist_ok=True)
    document={"case":case,"retrieved_at":now.isoformat(),"observation_cutoff":CUTOFF,"source_sha256":hashlib.sha256(raw).hexdigest(),"observations":rows}
    data=json.dumps(document,sort_keys=True,ensure_ascii=True).encode()
    (out/"snapshot.json").write_bytes(data)
    print("DIVERSE_EVIDENCE="+json.dumps({"id":case_id,"source":case["source"],"rows":len(rows),"first":rows[0][0],"last":rows[-1][0],"snapshot_sha256":hashlib.sha256(data).hexdigest(),"source_sha256":document["source_sha256"],"inference_calls":0}),flush=True)
    return document

def build_question(case):
    from forecasting_tools import BinaryQuestion,MultipleChoiceQuestion,NumericQuestion
    common=dict(question_text=case["question"],id_of_question=case["qid"],id_of_post=case["qid"],background_info="Public source: "+case["source"],resolution_criteria=case["criteria"]+" Source: "+case["source"],fine_print="Noncontest prospective research fixture. Use specified source and resolution snapshot, not other forecasts.",open_time=datetime(2026,11,25,tzinfo=timezone.utc),scheduled_resolution_time=datetime.fromisoformat(case["resolve"].replace("Z","+00:00")))
    if case["type"]=="binary":return BinaryQuestion(**common)
    if case["type"]=="multiple_choice":return MultipleChoiceQuestion(options=case["options"],**common)
    if case["type"]=="numeric":return NumericQuestion(unit_of_measure=case["unit"],lower_bound=case["lower"],upper_bound=case["upper"],open_lower_bound=case["open_lower"],open_upper_bound=case["open_upper"],**common)
    raise ValueError("unknown question type")
if __name__=="__main__":
    snapshot(sys.argv[1],Path(sys.argv[2]))
