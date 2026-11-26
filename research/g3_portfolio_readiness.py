"""Read-only planning preflight over existing development receipts.
No new registry, no new forecasts, no outcome access or admission.
The current candidate bank cannot be relabelled as confirmatory evidence.
"""
import copy,hashlib,json,math,sys
from collections import Counter
from datetime import date,datetime,timedelta,timezone
from fractions import Fraction
from pathlib import Path

PINS={
 "bls":("bls-definitions.json","510d985ce368a02b78eb65e5d95270036061fc9f22888f4796be9e88878db9d0",15081230448,45740108112,"reports",3),
 "france":("eurostat-definitions-final.json","182282d1186e23363eeaa74d650d96f5ad02540aeeb1ea514234a05e0587596e",15081476888,45741686088,"reports",3),
 "europe":("country-definitions-final.json","a55cd53824aaf02655ecdbfd5afa3e875030f776c857a8d70c3925c1e3a75a6d",15081951836,45742397543,"definitions",18),
 "cross_domain":("cross-domain-definitions-final.json","96c7970a5bbe3f401cf121f60245a6898d0262795567d1ac6081b71982d27a51",15081817596,45742547902,"reports",3),
 "native_mock":("g3-bridge-final.json","a6dc9cd46ffbe75054dbbf166639cfd840b1acfa8626958b8590d9c79b2bff37",15081368629,45742441153,"ready",6)}
AS_OF="2026-11-26"
MIN_PAIRS=100;MIN_WEEKS=10
COVERAGE=Fraction(95,100)
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(doc):return json.dumps(doc,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def utc(s):
    t=datetime.fromisoformat(s.replace("Z","+00:00"))
    require(t.tzinfo is not None and t.utcoffset().total_seconds()==0,"UTC required")
    return t
def load(root):
    data={}
    for k,(name,h,aid,run,field,count) in PINS.items():
        raw=(root/k/name).read_bytes();require(sha(raw)==h,"receipt bytes "+k)
        data[k]=json.loads(raw)
    return data
def collect(data):
    all_cases={}
    for k in ("bls","france","europe","cross_domain"):
        d=data[k];field,count=PINS[k][-2:]
        require(d["confirmatory_pairs"]==d["inference_calls"]==0 and not d["blocked"] and len(d[field])==count,"group scope "+k)
        require(d.get("actual_outcomes_accessed",d.get("outcomes_accessed"))==0 and d.get("automatic_capture_authorized",False) is False,"group authority "+k)
        for entry in d[field].values():
            e=entry["definition"];b=entry["baseline"]
            require(entry["definition_sha256"]==sha(canonical(e)),"definition bytes")
            require(e["partition"]=="development_only" and e["type"]=="binary" and e["confirmatory_eligible"] is False and e["inference_authorized"] is False and e.get("capture_authorized",False) is False,"definition authority")
            require(entry["inference_calls"]==0 and entry.get("actual_outcomes_accessed",entry.get("outcomes_accessed"))==0,"entry scope")
            n,y=b["n"],b["yes"];p=b["probability"]
            require(type(n) is int and type(y) is int and n>=12 and 0<=y<=n and type(p) in (int,float) and math.isfinite(p) and abs(p-(y+1)/(n+2))<1e-12,"baseline arithmetic")
            require(isinstance(e["family"],str) and e["family"] and isinstance(e["id"],str) and e["id"] not in all_cases and e["resolution_source"].startswith("https://"),"identity")
            require(utc(e["forecast_before"]).date()<=date.fromisoformat(e["capture_date_utc"]),"temporal identity")
            all_cases[e["id"]]={"group":k,"family":e["family"],"definition_sha256":entry["definition_sha256"],"forecast_before":e["forecast_before"],"baseline":b,"source_run":e["source_run"]}
    require(len({e["family"] for e in all_cases.values()})==len(all_cases),"duplicate family identity")
    mock=data["native_mock"]
    require(mock["confirmatory_pairs"]==mock["real_inference"]==0 and mock["live_admitted"] is False and not mock["blocked"] and len(mock["ready"])==PINS["native_mock"][-1],"mock scope")
    mock_ids=set()
    for r in mock["ready"]:
        k=r["event_id"];require(k in all_cases and k not in mock_ids,"mock event")
        e=all_cases[k]
        require(r["definition_sha256"]==e["definition_sha256"] and r["baseline"]==e["baseline"] and r["network_blocked"] is True and r["inference_calls"]==r["published"]==r["actual_outcomes_scored"]==0 and r["confirmatory_eligible"] is False and r["live_admitted"] is False,"mock receipt")
        mock_ids.add(k)
    return all_cases,mock_ids
def readiness(data):
    cases,mock=collect(data)
    dates=set()
    for e in cases.values():
        # Absolute upper bound from today's UTC day through the last possible
        # issue date, not a schedule or claim that earlier issuance is feasible.
        end=utc(e["forecast_before"])-timedelta(microseconds=1)
        d=date.fromisoformat(AS_OF)
        require(d<=end.date(),"deadline already closed")
        while d<=end.date():
            w=d.isocalendar();dates.add((w.year,w.week));d+=timedelta(days=1)
    n=len(cases)
    registered=next(k for k in range(MIN_PAIRS,MIN_PAIRS+100) if math.ceil(COVERAGE*k)>=MIN_PAIRS)
    summary=data["europe"]["summary"]
    return {"status":"BLOCK_CONFIRMATORY_DESIGN","as_of_utc_day":AS_OF,"existing_development_definitions":n,"distinct_family_labels_not_independence":len({e["family"] for e in cases.values()}),"groups":dict(Counter(e["group"] for e in cases.values())),"same_deadline_counts":dict(Counter(e["forecast_before"] for e in cases.values())),"native_mock_ready":len(mock),"native_real_forecasts":0,"confirmatory_pairs":0,"potential_issue_week_upper_bound":len(dates),"minimum_confirmatory_pairs":MIN_PAIRS,"minimum_issue_weeks":MIN_WEEKS,"minimum_registered_if_full_5_percent_missing_allowed":registered,"development_labels_reusable_as_confirmation":False,"gap_if_all_development_labels_were_hypothetically_eligible":MIN_PAIRS-n,"historical_eu_label_dependence":summary,"planning_dispatch_counts_not_authority":{str(k):{"base_3_per_event":3*k,"max_4_per_event":4*k} for k in (registered,200,400)},"blockers":["No prospective confirmatory admission or observations.","Current candidate count insufficient even if hypothetically eligible.","Current issue-window upper bound below ten weeks.","Dependency groups and independent power planning need separate evidence.","No G3 provider budget or capture runtime admitted."],"input_receipts":{k:{"artifact":p[2],"run":p[3],"json_sha256":p[1]} for k,p in PINS.items()},"inference_calls":0,"actual_outcomes_accessed":0,"promotion_authorized":False}
def tests(data):
    r=readiness(data)
    require(r["existing_development_definitions"]==27 and r["native_mock_ready"]==6 and r["potential_issue_week_upper_bound"]==6,"actual bank sizing")
    require(r["minimum_registered_if_full_5_percent_missing_allowed"]==105 and r["planning_dispatch_counts_not_authority"]["105"]=={"base_3_per_event":315,"max_4_per_event":420},"budget arithmetic")
    for kind in range(5):
        d=copy.deepcopy(data);e=d["bls"]["reports"]["cpi"]
        if kind==0:e["definition"]["inference_authorized"]=True;e["definition_sha256"]=sha(canonical(e["definition"]))
        if kind==1:e["baseline"]["probability"]=.9
        if kind==2:d["native_mock"]["ready"][0]["definition_sha256"]="0"*64
        if kind==3:e["definition"]["id"]=d["bls"]["reports"]["payroll"]["definition"]["id"];e["definition_sha256"]=sha(canonical(e["definition"]))
        if kind==4:e["definition_sha256"]="0"*64
        try:readiness(d)
        except ValueError:pass
        else:raise AssertionError("adversarial receipt admitted: "+str(kind))
    print("G3_PORTFOLIO_READINESS_TESTS_PASS=7")
    return r
if __name__=="__main__":
    r=tests(load(Path(sys.argv[1])))
    Path("g3-portfolio-readiness.json").write_text(json.dumps(r,sort_keys=True))
    print("G3_PORTFOLIO_READINESS="+json.dumps(r,sort_keys=True))
