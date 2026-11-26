"""Prospective paired binary statistical gate. No network or model calls.
Reuses existing score; provenance and authority admission remain separate.
Caller-supplied receipts are NOT cryptographically verified by this module.
"""
import hashlib,json,math,random,statistics,sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from historical_calibration import Row, score

PRIMARY="nemotron"
ROLES={"nemotron","gpt_oss","ernie"}
MIN_N=100
MIN_BLOCKS=10
MIN_COVERAGE=.95
MIN_GAIN=.01
SEED=20261126
DRAWS=10000
def require(ok,msg):
    if not ok:raise ValueError(msg)
def dt(s):
    x=datetime.fromisoformat(s.replace("Z","+00:00"))
    require(x.tzinfo is not None and x.utcoffset().total_seconds()==0,"UTC receipt required")
    return x
def digest(s):
    require(isinstance(s,str) and len(s)==64 and all(c in "0123456789abcdef" for c in s),"invalid sha256")
    return s
def prob(p):
    require(type(p) in (float,int) and math.isfinite(p) and .01<=p<=.99,"forecast outside registered floor")
    return float(p)
def unique(rows,key):
    d={}
    for row in rows:
        k=row[key]
        require(isinstance(k,str) and k and k not in d,"duplicate or invalid identity")
        d[k]=row
    return d
def block_interval(gains):
    # Resample whole forecast-week clusters. Paired observations retain identity.
    groups=list(gains.values())
    if len(groups)<MIN_BLOCKS:return None
    rng=random.Random(SEED)
    draws=[]
    for _ in range(DRAWS):
        selected=[rng.choice(groups) for _ in groups]
        draws.append(sum(sum(g) for g in selected)/sum(len(g) for g in selected))
    draws.sort()
    return [draws[int(.025*DRAWS)],draws[int(.975*DRAWS)]]
def evaluate(manifest,forecasts,outcomes,as_of):
    freeze=dt(manifest["frozen_at"])
    analysis_at=dt(manifest["analysis_at"])
    require(freeze<analysis_at,"invalid final analysis date")
    cutoff=min(as_of,analysis_at)
    require(freeze<=cutoff and manifest["type"]=="binary" and manifest["primary"]==PRIMARY,"manifest protocol")
    require(manifest["partition"]=="confirmatory","not confirmatory")
    digest(manifest["engine_sha256"])
    events=unique(manifest["events"],"id")
    # A family can occur only once in confirmatory cohort. Correlated variants
    # of the same underlying event must not enter under different IDs.
    unique(manifest["events"],"family")
    for e in events.values():
        require(freeze<=dt(e["forecast_deadline"])<dt(e["event_start"])<=dt(e["resolution_deadline"])<=analysis_at,"event timing")
        require(isinstance(e["resolution_source"],str) and e["resolution_source"].startswith("https://"),"source")
        digest(e["definition_sha256"])
    fs=unique(forecasts,"id");ys=unique(outcomes,"id")
    require(set(fs)<=set(events) and set(ys)<=set(events),"unregistered event")
    for ident,y in ys.items():
        e=events[ident]
        require(type(y["value"]) is int and y["value"] in (0,1),"invalid outcome")
        require(dt(e["event_start"])<=dt(y["resolved_at"])<=cutoff,"outcome timing")
        digest(y["source_sha256"])
    valid={}
    for ident,f in fs.items():
        e=events[ident];issued=dt(f["issued_at"])
        require(freeze<=issued<=dt(e["forecast_deadline"]) and issued<dt(e["event_start"]) and issued<=cutoff,"late or premature forecast")
        require(f["engine_sha256"]==manifest["engine_sha256"],"engine changed")
        digest(f["receipt_sha256"]);digest(f["evidence_sha256"])
        require(f["status"] in ("PASS","FAIL","ABSTAIN"),"unknown status")
        if f["status"]!="PASS":continue
        require(set(f["members"])==ROLES,"missing member")
        members={k:prob(v) for k,v in f["members"].items()}
        p=prob(f["aggregate"])
        require(abs(p-round(statistics.median(members.values()),3))<=1e-9,"aggregate mismatch")
        valid[ident]=(issued,p,members)
    # All registered events whose forecast deadline has passed count in coverage.
    due=[k for k,e in events.items() if dt(e["forecast_deadline"])<=cutoff]
    coverage=len(set(due)&set(valid))/len(due) if due else 0
    pairs=sorted(set(valid)&set(ys))
    rows=[];preds=defaultdict(list);blocks=defaultdict(list)
    for k in pairs:
        issued,p,members=valid[k];y=ys[k]["value"];resolved=dt(ys[k]["resolved_at"])
        rows.append(Row(k,issued.date(),resolved.date(),p,y))
        preds["ensemble"].append(p)
        preds["half"].append(.5)
        for role,v in members.items():preds[role].append(v)
        week=issued.isocalendar()
        blocks[(week.year,week.week)].append((members[PRIMARY]-y)**2-(p-y)**2)
    metrics={k:score(rows,v) for k,v in preds.items()} if rows else {}
    interval=block_interval(blocks)
    gain=metrics[PRIMARY]["brier"]-metrics["ensemble"]["brier"] if metrics else None
    # The pre-existing clip in score is inactive for all admitted probabilities.
    resolution_coverage=len(ys)/len(events) if events else 0
    final_analysis=as_of>=analysis_at
    enough=final_analysis and len(pairs)>=MIN_N and len(blocks)>=MIN_BLOCKS and coverage>=MIN_COVERAGE and resolution_coverage>=MIN_COVERAGE
    passed=enough and interval is not None and gain>=MIN_GAIN and interval[0]>0 and metrics["ensemble"]["log_loss"]<=metrics[PRIMARY]["log_loss"]
    status="PASS_STATISTICAL_ONLY" if passed else "FAIL_THRESHOLD" if enough else "UNKNOWN_INSUFFICIENT_EVIDENCE"
    return {"status":status,"registered":len(events),"due":len(due),"resolved":len(ys),"paired":len(pairs),"coverage":coverage,"resolution_coverage":resolution_coverage,"final_analysis":final_analysis,"forecast_weeks":len(blocks),"metrics":metrics,"paired_brier_gain":gain,"grouped_ci95":interval,"primary":PRIMARY,"inference_calls":0,"provenance_independently_verified":False,"official_futureeval_score":False,"promotion_authorized":False}
def synthetic(n=100):
    from datetime import timedelta,timezone
    origin=datetime(2027,1,1,tzinfo=timezone.utc)
    sha="a"*64
    m={"type":"binary","partition":"confirmatory","primary":PRIMARY,"engine_sha256":sha,"frozen_at":origin.isoformat(),"analysis_at":(origin+timedelta(days=100)).isoformat(),"events":[]}
    fs=[];ys=[]
    for i in range(n):
        issued=origin+timedelta(days=7*(i%10)+1)
        eid=f"synthetic-{i}";y=i%2
        m["events"].append({"id":eid,"family":eid,"forecast_deadline":issued.isoformat(),"event_start":(issued+timedelta(days=1)).isoformat(),"resolution_deadline":(issued+timedelta(days=2)).isoformat(),"resolution_source":"https://example.invalid","definition_sha256":sha})
        fs.append({"id":eid,"issued_at":issued.isoformat(),"status":"PASS","engine_sha256":sha,"receipt_sha256":sha,"evidence_sha256":sha,"members":{"nemotron":.5,"gpt_oss":.8 if y else .2,"ernie":.9 if y else .1},"aggregate":.8 if y else .2})
        ys.append({"id":eid,"value":y,"resolved_at":(issued+timedelta(days=2)).isoformat(),"source_sha256":sha})
    return m,fs,ys,origin+timedelta(days=100)
def tests():
    import copy
    m,f,y,t=synthetic()
    r=evaluate(m,f,y,t);require(r["status"]=="PASS_STATISTICAL_ONLY" and r["paired"]==100,"synthetic positive")
    require(evaluate(m,f[:90],y,t)["status"]=="UNKNOWN_INSUFFICIENT_EVIDENCE","missing coverage")
    require(evaluate(m,f,y[:99],t)["status"]=="UNKNOWN_INSUFFICIENT_EVIDENCE","small sample")
    from datetime import timedelta
    require(evaluate(m,f,y,t-timedelta(days=1))["status"]=="UNKNOWN_INSUFFICIENT_EVIDENCE","interim look promoted")
    bad=copy.deepcopy(f)
    for row in bad:row["members"]={"nemotron":.5,"gpt_oss":.5,"ernie":.5};row["aggregate"]=.5
    require(evaluate(m,bad,y,t)["status"]=="FAIL_THRESHOLD","zero gain")
    for kind in range(8):
        mm,ff,yy=copy.deepcopy((m,f,y))
        if kind==0:mm["events"][1]["family"]=mm["events"][0]["family"]
        elif kind==1:ff.append(ff[0])
        elif kind==2:ff[0]["issued_at"]=mm["events"][0]["event_start"]
        elif kind==3:ff[0]["members"].pop("ernie")
        elif kind==4:ff[0]["aggregate"]=.7
        elif kind==5:yy[0]["value"]=True
        elif kind==6:ff[0]["engine_sha256"]="b"*64
        elif kind==7:yy[0]["resolved_at"]=mm["frozen_at"]
        try:evaluate(mm,ff,yy,t)
        except ValueError:pass
        else:raise AssertionError("bad fixture admitted: "+str(kind))
    print("G3_PAIRED_GATE_TESTS_PASS=13 synthetic_only=true real_resolved_events=0")
if __name__=="__main__":
    if sys.argv[1:]==["--test"]:tests()
    elif len(sys.argv)==5:
        docs=[json.loads(Path(p).read_text()) for p in sys.argv[1:4]]
        result=evaluate(*docs,dt(sys.argv[4]))
        print(json.dumps(result,sort_keys=True))
    else:raise SystemExit("use --test or manifest forecasts outcomes as_of_utc")
