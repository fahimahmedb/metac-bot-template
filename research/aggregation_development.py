"""Development-only paired aggregation experiment on licensed archived forecasts.

Not F3 forecasts, not new holdout, not FutureEval scores. Reuses frozen
ForecastBench reader; excludes explicit freeze-value variants and FRED data.
The archive was previously used for research. All results are exploratory.
"""
import hashlib,json,math,random,statistics,sys
from collections import defaultdict,Counter
from datetime import date
from pathlib import Path
from second_holdout import read_archive,partition,pooled
from historical_calibration import Row,score,transform,paired_bootstrap

POLICIES=("median","mean","logit","logit_0.7","logit_1.3","median_0.7","median_1.3")
GROUP="no-explicit-market-context"
def require(ok,msg):
    if not ok:raise ValueError(msg)
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def pred(values,method):
    require(len(values)>=3 and all(type(v) in (float,int) and math.isfinite(v) and 0<=v<=1 for v in values),"invalid pool")
    if method=="median":return statistics.median(values)
    if method=="mean":return statistics.mean(values)
    if method.startswith("median_"):return transform(statistics.median(values),0,float(method.split("_")[1]))
    z=statistics.mean(math.log(min(.999,max(.001,p))/(1-min(.999,max(.001,p)))) for p in values)
    scale=1 if method=="logit" else float(method.split("_")[1])
    return 1/(1+math.exp(-scale*z))

def prepare(archive,out):
    events,preds,counts=read_archive(archive)
    selected=[]
    for e in sorted(events.values(),key=lambda e:(e.issued,e.key)):
        # The prior test partition remains unused here; no repeated test claim.
        if partition(e) not in ("train","validation"):continue
        providers=pooled(e,preds,GROUP)
        if len(providers)<3:continue
        selected.append({"id":h(e.key),"source":e.key.split(":",1)[0],"issued":str(e.issued),"resolved":str(e.resolved),"partition":partition(e),"y":e.y,"pools":providers})
    require(len({r["id"] for r in selected})==len(selected),"duplicate event")
    result={"license":"Forecasting Research Institute ForecastBench CC BY-SA 4.0; https://www.forecastbench.org/datasets/","scope":"previously consumed development archive only; no real F3 predictions","counts":counts,"rows":selected}
    out.write_text(json.dumps(result,sort_keys=True))
    print("AGG_PREP="+json.dumps({"n":len(selected),"partitions":dict(Counter(r["partition"] for r in selected)),"rounds":len(set(r["issued"] for r in selected)),"sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"inference_calls":0}))

def choose_values(row,mode):
    pool=row["pools"]
    if mode=="all":return list(pool.values())
    # Exactly three provider ballots, selected by identity hash, never by labels
    # or forecasts. Fixed selection deterministic per event.
    ids=sorted(pool,key=lambda p:h(row["id"]+"|"+p))[:3]
    return [pool[p] for p in ids]

def evaluate(data,mode):
    require(mode in ("three","all"),"unknown mode")
    data=data["rows"]
    require(len({r["id"] for r in data})==len(data),"duplicate event")
    def subset(rows):
        if not rows:return {"n":0,"status":"BLOCK_NO_ROWS"}
        rr=[Row(r["id"],date.fromisoformat(r["issued"]),date.fromisoformat(r["resolved"]),pred(choose_values(r,mode),"median"),r["y"]) for r in rows]
        require(all(r.y in (0,1) and r.issued<r.resolved for r in rr),"invalid timing")
        predictions={p:[pred(choose_values(r,mode),p) for r in rows] for p in POLICIES}
        metrics={p:score(rr,ps) for p,ps in predictions.items()}
        metrics["half"]=score(rr,[.5]*len(rr))
        base=metrics["median"]["brier"]
        comparisons={p:{"gain_vs_median":base-metrics[p]["brier"],"round_bootstrap":paired_bootstrap(rr,predictions[p])} for p in POLICIES if p!="median"}
        return {"n":len(rr),"rounds":len({r.issued for r in rr}),"metrics":metrics,"comparisons":comparisons,"positive_rate":sum(r.y for r in rr)/len(rr),"median_provider_count":statistics.median(len(r["pools"]) for r in rows)}
    reports={k:subset([r for r in data if r["partition"]==k]) for k in ("train","validation")}
    # No fitted parameters; pick the best earlier development policy only,
    # then describe its later-development performance without changing it.
    a,b=reports["train"],reports["validation"]
    if a["n"]>=100 and b["n"]>=30:
        best=min(POLICIES,key=lambda p:(a["metrics"][p]["brier"],POLICIES.index(p)))
        chosen=best if a["metrics"]["median"]["brier"]-a["metrics"][best]["brier"]>=.002 else "median"
        later=b["metrics"]["median"]["brier"]-b["metrics"][chosen]["brier"]
        decision="CANDIDATE_FOR_PROSPECTIVE_TEST" if chosen!="median" and later>=.002 else "KEEP_MEDIAN_REFERENCE"
    else:chosen=None;later=None;decision="BLOCK_INSUFFICIENT_DEVELOPMENT_COVERAGE"
    return {"mode":mode,"scope":"exploratory, overlapping historical development rows, not independent confirmation","reports":reports,"chosen_on_earlier_development":chosen,"later_development_gain":later,"decision":decision,"inference_calls":0,"f3_skill":"UNKNOWN","promotion_authorized":False}

def tests():
    require(pred([.1,.2,.9],"median")==.2,"median")
    require(abs(pred([.1,.2,.9],"mean")-.4)<1e-12,"mean")
    require(abs(pred([.2,.5,.8],"logit")-.5)<1e-12,"symmetric logit")
    row={"id":"x","pools":{"a":.1,"b":.2,"c":.3,"d":.4}}
    v=choose_values(row,"three")
    require(len(v)==3 and v==choose_values(dict(row,pools=dict(reversed(list(row["pools"].items())))),"three"),"selection identity")
    try:pred([.1,.2,float("nan")],"mean")
    except ValueError:pass
    else:raise AssertionError("NaN admitted")
    print("AGG_DEV_TESTS_PASS=5")

if __name__=="__main__":
    tests()
    if sys.argv[1]=="prepare":prepare(Path(sys.argv[2]),Path(sys.argv[3]))
    elif sys.argv[1]=="evaluate":
        r=evaluate(json.loads(Path(sys.argv[2]).read_text()),sys.argv[3])
        Path("aggregation-report.json").write_text(json.dumps(r,sort_keys=True))
        print("AGG_DEV_RESULT="+json.dumps(r,sort_keys=True))
    else:raise SystemExit("invalid mode")
