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
SHADOW_POLICY="mean-and-median-logit-0.7-v1"
REFERENCE_POLICY="laplace-floor-0.01-v1"
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
def shadow_probabilities(members):
    """Fixed exploratory alternatives; no outcomes or external information."""
    require(set(members)==ROLES,"shadow role identity")
    values=[prob(v) for v in members.values()]
    p=statistics.median(values)
    tempered=1/(1+math.exp(-.7*math.log(p/(1-p))))
    return {"mean":round(statistics.mean(values),3),"median_logit_0.7":round(tempered,3)}
def reference_probability(event,freeze):
    """Verify arithmetic and declared timing, NOT external receipt authenticity."""
    b=event["reference"]
    require(b["policy"]==REFERENCE_POLICY and b["definition_sha256"]==event["definition_sha256"],"reference identity")
    require(dt(b["data_cutoff"])<=dt(b["frozen_at"])<=freeze,"reference frozen late or invalid cutoff")
    digest(b["evidence_sha256"])
    n,k=b["n"],b["yes"]
    require(type(n) is int and type(k) is int and n>=12 and 0<=k<=n,"reference counts")
    p=max(.01,min(.99,(k+1)/(n+2)))
    require(abs(prob(b["probability"])-p)<=1e-12,"reference arithmetic")
    return p

def reliability(rows,probabilities):
    """Five fixed bins on exactly the scored pairs; descriptive, not a gate."""
    require(len(rows)==len(probabilities) and bool(rows),"calibration alignment")
    buckets=[[] for _ in range(5)]
    for r,p in zip(rows,probabilities,strict=True):
        p=prob(p)
        idx=next((i for i in range(4) if p<(i+1)/5),4)
        buckets[idx].append((p,r.y))
    bins=[]
    for i,group in enumerate(buckets):
        n=len(group)
        bins.append({"low":i/5,"high":(i+1)/5,"n":n,
                     "mean_probability":statistics.mean(p for p,y in group) if n else None,
                     "observed_frequency":statistics.mean(y for p,y in group) if n else None})
    n=len(rows)
    ece=sum(b["n"]*abs(b["mean_probability"]-b["observed_frequency"]) for b in bins if b["n"])/n
    return {"n":n,"bins":bins,"ece_descriptive":ece,
            "mean_probability_minus_frequency":statistics.mean(probabilities)-statistics.mean(r.y for r in rows),
            "status":"DESCRIPTIVE_ONLY","independence_assumed":False,"promotion_authorized":False}

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
    shadow=manifest.get("shadow_policy")
    require(shadow is None or shadow==SHADOW_POLICY,"unknown shadow policy")
    reference_policy=manifest.get("reference_policy")
    require(reference_policy is None or reference_policy==REFERENCE_POLICY,"unknown reference policy")
    events=unique(manifest["events"],"id")
    references={k:reference_probability(e,freeze) for k,e in events.items()} if reference_policy else {}
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
        require(dt(e["event_start"])<=dt(y["resolved_at"])<=min(cutoff,dt(e["resolution_deadline"])),"outcome timing or registered resolution deadline")
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
    rows=[];preds=defaultdict(list);blocks=defaultdict(list);shadow_preds=defaultdict(list);shadow_blocks=defaultdict(lambda:defaultdict(list));reference_blocks=defaultdict(list)
    for k in pairs:
        issued,p,members=valid[k];y=ys[k]["value"];resolved=dt(ys[k]["resolved_at"])
        rows.append(Row(k,issued.date(),resolved.date(),p,y))
        preds["ensemble"].append(p)
        preds["half"].append(.5)
        for role,v in members.items():preds[role].append(v)
        week=issued.isocalendar()
        blocks[(week.year,week.week)].append((members[PRIMARY]-y)**2-(p-y)**2)
        if reference_policy:
            q=references[k]
            preds["frozen_reference"].append(q)
            reference_blocks[(week.year,week.week)].append((q-y)**2-(p-y)**2)
        if shadow:
            for name,q in shadow_probabilities(members).items():
                shadow_preds[name].append(q)
                shadow_blocks[name][(week.year,week.week)].append((p-y)**2-(q-y)**2)
    metrics={k:score(rows,v) for k,v in preds.items()} if rows else {}
    calibration={k:reliability(rows,v) for k,v in preds.items()} if rows else {}
    interval=block_interval(blocks)
    gain=metrics[PRIMARY]["brier"]-metrics["ensemble"]["brier"] if metrics else None
    # The pre-existing clip in score is inactive for all admitted probabilities.
    resolution_coverage=len(ys)/len(events) if events else 0
    paired_coverage=len(pairs)/len(events) if events else 0
    # Sensitivity bounds for missing registered pairs, not a confidence interval.
    # Under the admitted [.01,.99] floor the Brier gain lies in [-.98,.98].
    missing=len(events)-len(pairs)
    cohort_gain_bounds=([(len(pairs)*gain-.98*missing)/len(events),
                         (len(pairs)*gain+.98*missing)/len(events)]
                        if events and gain is not None else None)
    final_analysis=as_of>=analysis_at
    enough=final_analysis and len(pairs)>=MIN_N and len(blocks)>=MIN_BLOCKS and coverage>=MIN_COVERAGE and resolution_coverage>=MIN_COVERAGE and paired_coverage>=MIN_COVERAGE
    passed=enough and interval is not None and gain>=MIN_GAIN and interval[0]>0 and metrics["ensemble"]["log_loss"]<=metrics[PRIMARY]["log_loss"]
    status="PASS_STATISTICAL_ONLY" if passed else "FAIL_THRESHOLD" if enough else "UNKNOWN_INSUFFICIENT_EVIDENCE"
    reference_result={"status":"NOT_REGISTERED"}
    if reference_policy:
        ref_gain=metrics["frozen_reference"]["brier"]-metrics["ensemble"]["brier"] if rows else None
        ref_ci=block_interval(reference_blocks)
        ref_pass=enough and ref_ci is not None and ref_gain>=MIN_GAIN and ref_ci[0]>0 and metrics["ensemble"]["log_loss"]<=metrics["frozen_reference"]["log_loss"]
        reference_result={"status":"PASS_STATISTICAL_ONLY" if ref_pass else "FAIL_THRESHOLD" if enough else "UNKNOWN_INSUFFICIENT_EVIDENCE","gain":ref_gain,"grouped_ci95":ref_ci,"paired":len(pairs),"provenance_independently_verified":False,"promotion_authorized":False}
    shadow_results={}
    if shadow and rows:
        for name,ps in shadow_preds.items():
            m=score(rows,ps)
            shadow_results[name]={"metrics":m,"gain_vs_median":metrics["ensemble"]["brier"]-m["brier"],"grouped_ci95":block_interval(shadow_blocks[name]),"status":"EXPLORATORY_ONLY","requires_new_independent_confirmation":True}
    return {"status":status,"registered":len(events),"due":len(due),"resolved":len(ys),"paired":len(pairs),"paired_coverage":paired_coverage,"coverage":coverage,"resolution_coverage":resolution_coverage,"final_analysis":final_analysis,"forecast_weeks":len(blocks),"metrics":metrics,"calibration":calibration,"paired_brier_gain":gain,"full_cohort_gain_sensitivity_bounds":cohort_gain_bounds,"grouped_ci95":interval,"primary":PRIMARY,"reference_policy":reference_policy,"reference_result":reference_result,"shadow_policy":shadow,"shadow_results":shadow_results,"inference_calls":0,"provenance_independently_verified":False,"official_futureeval_score":False,"promotion_authorized":False}
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
    for kind in range(9):
        mm,ff,yy=copy.deepcopy((m,f,y))
        if kind==0:mm["events"][1]["family"]=mm["events"][0]["family"]
        elif kind==1:ff.append(ff[0])
        elif kind==2:ff[0]["issued_at"]=mm["events"][0]["event_start"]
        elif kind==3:ff[0]["members"].pop("ernie")
        elif kind==4:ff[0]["aggregate"]=.7
        elif kind==5:yy[0]["value"]=True
        elif kind==6:ff[0]["engine_sha256"]="b"*64
        elif kind==7:yy[0]["resolved_at"]=mm["frozen_at"]
        elif kind==8:yy[0]["resolved_at"]=(dt(mm["events"][0]["resolution_deadline"])+timedelta(days=1)).isoformat()
        try:evaluate(mm,ff,yy,t)
        except ValueError:pass
        else:raise AssertionError("bad fixture admitted: "+str(kind))
    mm,ff,yy,tt=synthetic(120)
    disjoint=evaluate(mm,ff[6:],yy[:-6],tt)
    require(disjoint["paired_coverage"]==.9 and disjoint["status"]=="UNKNOWN_INSUFFICIENT_EVIDENCE","disjoint missingness")
    same=evaluate(mm,ff[6:],yy[6:],tt)
    require(same["paired_coverage"]==.95 and same["status"]=="PASS_STATISTICAL_ONLY","paired boundary")
    require(all(abs(v-r["paired_brier_gain"])<1e-12 for v in r["full_cohort_gain_sensitivity_bounds"]),"complete cohort bounds")
    for a,b in zip(ff,yy):
        v=b["value"]
        a["members"]={"nemotron":.5,"gpt_oss":.52 if v else .48,"ernie":.53 if v else .47}
        a["aggregate"]=a["members"]["gpt_oss"]
    weak=evaluate(mm,ff[6:],yy[6:],tt)
    require(weak["status"]=="PASS_STATISTICAL_ONLY" and weak["full_cohort_gain_sensitivity_bounds"][0]<0<weak["full_cohort_gain_sensitivity_bounds"][1],"missingness can reverse full-cohort gain")
    # Check deterministic prospective alternatives without changing the primary gate.
    sh=shadow_probabilities({"nemotron":.18,"gpt_oss":.13,"ernie":.06})
    require(sh=={"mean":.123,"median_logit_0.7":.209},"shadow arithmetic")
    sm=copy.deepcopy(m);sm["shadow_policy"]=SHADOW_POLICY
    sr=evaluate(sm,f,y,t)
    require(sr["status"]==r["status"] and sr["metrics"]==r["metrics"] and sr["paired_brier_gain"]==r["paired_brier_gain"] and set(sr["shadow_results"])=={"mean","median_logit_0.7"},"shadow altered primary")
    require(all(x["status"]=="EXPLORATORY_ONLY" for x in sr["shadow_results"].values()),"shadow promoted")
    sm["shadow_policy"]="unregistered"
    try:evaluate(sm,f,y,t)
    except ValueError:pass
    else:raise AssertionError("unregistered shadow policy admitted")
    # Fixed comparator, same sample and identical primary verdict. Counts are
    # synthetic; the favorable/adversarial fixtures prove logic, not skill.
    rm=copy.deepcopy(m);rm["reference_policy"]=REFERENCE_POLICY
    for e in rm["events"]:
        e["reference"]={"policy":REFERENCE_POLICY,"definition_sha256":e["definition_sha256"],"data_cutoff":rm["frozen_at"],"frozen_at":rm["frozen_at"],"evidence_sha256":"a"*64,"n":18,"yes":9,"probability":.5}
    rr=evaluate(rm,f,y,t)
    require(rr["status"]==r["status"] and rr["reference_result"]["status"]=="PASS_STATISTICAL_ONLY" and rr["reference_result"]["paired"]==100,"reference paired pass")
    require(rr["metrics"]["frozen_reference"]==rr["metrics"]["half"],"same paired sample")
    for e,label in zip(rm["events"],y,strict=True):
        e["reference"].update(yes=17 if label["value"] else 1,probability=.9 if label["value"] else .1)
    losing=evaluate(rm,f,y,t)
    require(losing["status"]=="PASS_STATISTICAL_ONLY" and losing["reference_result"]["status"]=="FAIL_THRESHOLD" and losing["reference_result"]["gain"]<0,"Nemotron win is not baseline win")
    require(evaluate(rm,f[:90],y,t)["reference_result"]["status"]=="UNKNOWN_INSUFFICIENT_EVIDENCE","reference coverage")
    for field,val in (("frozen_at",f[0]["issued_at"]),("probability",.7),("n",True),("definition_sha256","b"*64),("evidence_sha256","bad"),("policy","other")):
        bad=copy.deepcopy(rm);bad["events"][0]["reference"][field]=val
        try:evaluate(bad,f,y,t)
        except ValueError:pass
        else:raise AssertionError("invalid reference accepted: "+field)
    # Five equal-width bins, fixed before observations. Empty bins stay null.
    cal_rows=[Row(str(i),t.date(),t.date(),p,y) for i,(p,y) in enumerate(((.1,0),(.2,1),(.4,0),(.6,1),(.8,1),(.99,1)))]
    c=reliability(cal_rows,[.1,.2,.4,.6,.8,.99])
    require([b["n"] for b in c["bins"]]==[1,1,1,1,2],"calibration bin boundaries")
    require(abs(c["ece_descriptive"]-(.1+.8+.4+.4+.105*2)/6)<1e-12,"calibration arithmetic")
    c0=reliability(cal_rows,[.5]*6)
    require(c0["bins"][0]["mean_probability"] is None and c0["bins"][2]["n"]==6,"calibration empty bins")
    require(rr["calibration"]["frozen_reference"]==rr["calibration"]["half"] and rr["calibration"]["ensemble"]["n"]==rr["paired"] and rr["status"]==r["status"],"calibration same paired sample")
    print("G3_PAIRED_GATE_TESTS_PASS=36 synthetic_only=true real_resolved_events=0")
if __name__=="__main__":
    if sys.argv[1:]==["--test"]:tests()
    elif len(sys.argv)==5:
        docs=[json.loads(Path(p).read_text()) for p in sys.argv[1:4]]
        result=evaluate(*docs,dt(sys.argv[4]))
        print(json.dumps(result,sort_keys=True))
    else:raise SystemExit("use --test or manifest forecasts outcomes as_of_utc")
