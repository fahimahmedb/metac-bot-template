"""Rolling-origin research with untouched economic test series.

Sources: ForecastBench CC BY-SA 4.0, pinned snapshots and archive. All inputs
are archived pre-forecast snapshots; labels' dates plus embargo are a proxy
for availability, not a complete ALFRED vintage reconstruction.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
import json,math,random,statistics,tarfile
from pathlib import Path
import numpy as np
from economic_baseline import DATES,fetch_snapshot,matching_deltas,probabilities,INPUT_SHA
from historical_calibration import sha256
from local_llm_replay import stable_hash,event_id
from second_holdout import ARCHIVE_SHA,DATA_REF

HORIZONS=(7,30)
ORIGINS=[date(2025,11,1),date(2026,2,1),date(2026,5,1)]
DEV_END=date(2026,7,1)
TEST_END=date(2026,10,26)
LABEL_FREEZE=date(2026,11,20)
EMBARGO=timedelta(days=30)
TEST_CAP=500
FEATURES=("horizon","fred","n_history","age","n_pairs","pair_up","recent_up","ties",
          "z1","z3","z6","level_z","slope","vol_recent_ratio","prior_strength",
          "empirical","momentum","mean_reversion","recent")
BASELINES=("half","empirical","momentum","mean_reversion","recent","pooled")
MODELS=("lr_0.03","lr_0.3","lr_3","hgb_3","hgb_7")
# Candidate list and tuning space fixed before opening the new test results.
CANDIDATES=BASELINES+MODELS+("lr_0.3_shrink","hgb_3_shrink")

def labels_from_archive(path,scheduled):
    """Resolve only scheduled series/date/horizon, reject conflicting outcomes."""
    found=defaultdict(set)
    counts=Counter()
    with tarfile.open(path,"r|gz") as ar:
        for member in ar:
            if not member.isfile() or not member.name.endswith(".json") or member.size>30_000_000:
                continue
            try: issued=date.fromisoformat(Path(member.name).name[:10])
            except ValueError: continue
            if str(issued) not in scheduled:
                continue
            f=ar.extractfile(member)
            if f is None: continue
            obj=json.load(f)
            if not isinstance(obj,dict) or obj.get("organization")!="ForecastBench" or obj.get("question_set")!=f"{issued}-llm.json":
                continue
            for item in obj.get("forecasts",[]):
                counts["scanned"]+=1
                src=item.get("source")
                if src not in {"fred","dbnomics"} or not isinstance(item.get("id"),str) or item.get("resolved") is not True:
                    continue
                try:
                    target=date.fromisoformat(str(item["resolution_date"])[:10])
                    y=float(item["resolved_to"])
                except (KeyError,ValueError,TypeError): continue
                if (target-issued).days not in HORIZONS or target>=LABEL_FREEZE or y not in (0,1): continue
                series=event_id(src,item["id"])
                key=(series,str(issued),str(target))
                if key in scheduled[str(issued)]:
                    found[key].add(int(y))
    counts["conflicting"]=sum(len(x)>1 for x in found.values())
    return {k:next(iter(v)) for k,v in found.items() if len(v)==1},dict(counts)

def extract_features(history,issued,known,horizon,source):
    """All supplied history entries must predate or equal the freeze."""
    if not history or any(d>known for d,v in history) or known>issued:
        raise ValueError("future history")
    vs=np.asarray([v for d,v in history],dtype=float)
    days=np.asarray([(d-history[0][0]).days for d,v in history],dtype=float)
    diffs=np.diff(vs)
    robust=max(float(np.median(np.abs(diffs))) if len(diffs) else 0,
               float(np.std(diffs)) if len(diffs) else 0,1e-8*max(1,abs(vs[-1])))
    def z(k):
        if len(vs)<=k: return 0.
        return float(np.clip((vs[-1]-vs[-1-k])/(robust*math.sqrt(k)),-8,8))
    recent=vs[-12:]
    level_z=float(np.clip((vs[-1]-np.median(recent))/(max(float(np.std(recent)),robust)),-8,8))
    # Per calendar day slope over a short window; standardized for scale invariance.
    tx=days[-8:]; vx=vs[-8:]
    slope=float(np.clip(np.polyfit(tx-tx[0],vx-vx[0],1)[0]*14/robust,-8,8)) if len(tx)>=3 and tx[-1]>tx[0] else 0.
    recent_diff=diffs[-4:]
    vol_ratio=float(np.clip(np.std(recent_diff)/robust,0,5)) if len(recent_diff)>1 else 0.
    pairs=matching_deltas(history,horizon)
    deltas=[d for _,d in pairs]; n=len(deltas)
    up=(sum(d>0 for d in deltas)+2)/(n+4)
    short=deltas[-6:]
    recent_up=(sum(d>0 for d in short)+2)/(len(short)+4)
    ties=sum(d==0 for d in deltas)/n if n else 0.
    old,_=probabilities(history,horizon)
    return dict(zip(FEATURES,[horizon,int(source=="fred"),len(history),(issued-known).days,n,up,recent_up,ties,
                  z(1),z(3),z(6),level_z,slope,vol_ratio,n/(n+8),
                  old["empirical"],old["momentum"],old["mean_reversion"],old["recent"]]))

def build_rows(archive,previous):
    if sha256(archive)!=ARCHIVE_SHA or sha256(previous)!=INPUT_SHA:
        raise ValueError("Source identity mismatch")
    dates=[d for d in DATES if date.fromisoformat(d)<TEST_END]
    with ThreadPoolExecutor(max_workers=4) as pool:
        fetched=list(pool.map(fetch_snapshot,dates))
    snapshots={d:values for d,values,h in fetched}
    old=json.loads(previous.read_text())
    excluded=set()
    for row in old:
        matches=[s for s in snapshots[row["issued"]] if stable_hash("replay-input|"+s+"|"+row["issued"]+"|"+row["target_date"])==row["key"]]
        if len(matches)!=1: raise ValueError("Prior replay identity unresolved")
        excluded.add(matches[0])
    # Build features in one forward pass, never read future snapshot values.
    histories=defaultdict(dict); features={}; scheduled=defaultdict(set)
    for day in dates:
        issued=date.fromisoformat(day)
        for series,(known,value,targets,q) in snapshots[day].items():
            if known>issued: raise ValueError("Future freeze")
            histories[series][known]=value
            if not isinstance(targets,list) or not any(x in q.lower() for x in ("have increased","will exceed","will be higher")): continue
            source=series.split(":",1)[0]
            history=sorted((d,v) for d,v in histories[series].items() if d<=known)
            for h in HORIZONS:
                target=issued+timedelta(days=h)
                if str(target) not in targets or target>=LABEL_FREEZE: continue
                key=(series,day,str(target))
                scheduled[day].add(key)
                features[key]=extract_features(history,issued,known,h,source)
    labels,counts=labels_from_archive(archive,scheduled)
    rows=[{"series":s,"issued":d,"target":t,"y":labels[(s,d,t)],**f}
          for (s,d,t),f in features.items() if (s,d,t) in labels]
    rows.sort(key=lambda r:(r["issued"],r["series"],r["target"]))
    # Select a fixed new cohort by hash, not label. No series used by replay v1.
    test_all=[r for r in rows if date.fromisoformat(r["issued"])>=DEV_END and r["series"] not in excluded]
    # Balance forecast rounds and horizons; deterministic hash within strata.
    bins=defaultdict(list)
    for r in test_all: bins[(r["issued"],r["horizon"])].append(r)
    for k in bins:
        bins[k].sort(key=lambda r:stable_hash("rolling-final-v1|"+r["series"]+"|"+r["issued"]+"|"+r["target"]))
    selected=[]
    while len(selected)<TEST_CAP and any(bins.values()):
        for k in sorted(bins):
            if bins[k] and len(selected)<TEST_CAP: selected.append(bins[k].pop(0))
    if len(selected)<200:
        raise ValueError(f"Need at least 200 new test cases; got {len(selected)}")
    dev=[r for r in rows if date.fromisoformat(r["issued"])<DEV_END]
    assert not {r["series"] for r in selected}&excluded
    assert all(date.fromisoformat(r["issued"])>=DEV_END for r in selected)
    manifest={"archive_sha256":ARCHIVE_SHA,"snapshot_commit":DATA_REF,
              "snapshots":{d:h for d,values,h in fetched},"excluded_prior_series":len(excluded),
              "rows":len(rows),"development":len(dev),"test_pool":len(test_all),
              "test_n":len(selected),"test_series":len({r["series"] for r in selected}),
              "test_rounds":len({r["issued"] for r in selected}),"counts":counts}
    return dev,selected,manifest

def matrix(rows):
    return np.asarray([[r[k] for k in FEATURES] for r in rows],dtype=float)

def fit_models(train):
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    X=matrix(train); y=np.asarray([r["y"] for r in train])
    if len(np.unique(y))<2: raise ValueError("Training labels need both classes")
    result={}
    for c in (.03,.3,3):
        m=make_pipeline(StandardScaler(),LogisticRegression(C=c,max_iter=500,random_state=19))
        m.fit(X,y);result[f"lr_{c:g}"]=m
    for leaves in (3,7):
        m=HistGradientBoostingClassifier(max_iter=80,learning_rate=.05,max_leaf_nodes=leaves,
                min_samples_leaf=40,l2_regularization=5,early_stopping=False,random_state=19)
        m.fit(X,y);result[f"hgb_{leaves}"]=m
    # Pooled historical rates by source & horizon, shrunk to overall rate.
    rate=(sum(y)+2)/(len(y)+4)
    pooled={}
    for k in {(r["fred"],r["horizon"]) for r in train}:
        yy=[r["y"] for r in train if (r["fred"],r["horizon"])==k]
        pooled[k]=(sum(yy)+100*rate)/(len(yy)+100)
    return result,rate,pooled

def predict_all(rows,fitted):
    models,rate,pooled=fitted
    X=matrix(rows)
    pred={"half":np.full(len(rows),.5)}
    for m in ("empirical","momentum","mean_reversion","recent"):
        pred[m]=np.array([r[m] for r in rows])
    pred["pooled"]=np.array([pooled.get((r["fred"],r["horizon"]),rate) for r in rows])
    for name,model in models.items():
        pred[name]=model.predict_proba(X)[:,1]
    pred["lr_0.3_shrink"]=(pred["lr_0.3"]+.5)/2
    pred["hgb_3_shrink"]=(pred["hgb_3"]+.5)/2
    assert set(pred)==set(CANDIDATES)
    return pred

def metrics(y,p):
    y=np.asarray(y); p=np.asarray(p)
    q=np.clip(p,.001,.999)
    return {"n":len(y),"brier":float(np.mean((p-y)**2)),
            "log_loss":float(np.mean(-y*np.log(q)-(1-y)*np.log(1-q))),
            "accuracy":float(np.mean((p>=.5)==y))}

def train_before(dev,origin):
    return [r for r in dev if date.fromisoformat(r["issued"])<origin and date.fromisoformat(r["target"])<origin-EMBARGO]

def select(dev):
    all_losses=defaultdict(list); folds=[]
    for start,end in zip(ORIGINS,ORIGINS[1:]+[DEV_END]):
        train=train_before(dev,start)
        # All validation labels are available before final refit; avoid future
        # validation outcomes entering candidate selection at the final cutoff.
        val=[r for r in dev if start<=date.fromisoformat(r["issued"])<end
             and date.fromisoformat(r["target"])<DEV_END-EMBARGO]
        if len(train)<100 or len(val)<50: raise ValueError("Insufficient rolling fold")
        fitted=fit_models(train)
        # Remove targets before inference; y only used for scoring.
        X=[{k:v for k,v in r.items() if k!="y"} for r in val]
        ps=predict_all(X,fitted); y=np.array([r["y"] for r in val])
        scores={m:metrics(y,p)["brier"] for m,p in ps.items()}
        for m in CANDIDATES: all_losses[m].append(scores[m])
        folds.append({"origin":str(start),"end":str(end),"train_n":len(train),"validation_n":len(val),"brier":scores})
    # Equal weight per temporal fold; modest tie tolerance favors neutral.
    avg={m:statistics.mean(v) for m,v in all_losses.items()}
    best=min(CANDIDATES,key=lambda m:(avg[m],CANDIDATES.index(m)))
    selected=best if avg["half"]-avg[best]>=.002 else "half"
    simple=min(BASELINES,key=lambda m:(avg[m],BASELINES.index(m)))
    return {"folds":folds,"mean_fold_brier":avg,"selected":selected,"best_simple":simple}

def bootstrap(rows,gains,field):
    groups=defaultdict(list)
    for r,g in zip(rows,gains): groups[r[field]].append(float(g))
    arrays=list(groups.values())
    if len(arrays)<5: return {"clusters":len(arrays),"ci95":None}
    sums=np.array([sum(a) for a in arrays]); ns=np.array([len(a) for a in arrays])
    rng=np.random.default_rng(20261124)
    idx=rng.integers(0,len(arrays),(2000,len(arrays)))
    estimates=sums[idx].sum(axis=1)/ns[idx].sum(axis=1)
    return {"clusters":len(arrays),"ci95":[float(x) for x in np.quantile(estimates,[.025,.975])]}

def prepare(archive,previous,outdir):
    dev,test,manifest=build_rows(archive,previous)
    outdir.mkdir(parents=True,exist_ok=True)
    test_inputs=[{k:v for k,v in r.items() if k!="y"} for r in test]
    test_labels=[r["y"] for r in test]
    for name,obj in (("dev.json",dev),("test_inputs.json",test_inputs),("test_labels.json",test_labels),("manifest.json",manifest)):
        (outdir/name).write_text(json.dumps(obj,separators=(",",":"))+"\n")
    print("PREPARED",json.dumps(manifest|{"snapshots":len(manifest["snapshots"])}))
    print("TEST_INPUT_SHA",sha256(outdir/"test_inputs.json"))

def fit_predict(devpath,testpath,out):
    dev=json.loads(devpath.read_text()); test=json.loads(testpath.read_text())
    if any("y" in r for r in test): raise ValueError("Test labels present")
    decision=select(dev)
    fit=fit_models(train_before(dev,DEV_END))
    ps=predict_all(test,fit)
    report={"policy":decision,"train_n":len(train_before(dev,DEV_END)),
            "input_sha256":sha256(testpath),"predictions":{k:v.tolist() for k,v in ps.items()}}
    out.write_text(json.dumps(report,separators=(",",":"))+"\n")
    print("FROZEN",sha256(out),"SELECTED",decision["selected"])

def evaluate(predpath,testpath,labelpath,out):
    p=json.loads(predpath.read_text()); rows=json.loads(testpath.read_text()); y=np.array(json.loads(labelpath.read_text()))
    if p["input_sha256"]!=sha256(testpath) or len(rows)!=len(y): raise ValueError("Mismatched input/labels")
    ps={k:np.array(v) for k,v in p["predictions"].items()}
    if any(len(v)!=len(y) or not np.isfinite(v).all() or np.any((v<0)|(v>1)) for v in ps.values()):
        raise ValueError("Malformed forecasts")
    selected=p["policy"]["selected"]; simple=p["policy"]["best_simple"]
    result={"n":len(y),"test_series":len({r["series"] for r in rows}),"rounds":len({r["issued"] for r in rows}),
            "test_yes_rate":float(y.mean()),"input_sha256":p["input_sha256"],"frozen_predictions_sha256":sha256(predpath),
            "final_train_n":p["train_n"],"policy":p["policy"],"selected":selected,"best_simple":simple,
            "test_scores":{k:metrics(y,v) for k,v in ps.items()},
            "paired":{},"by_horizon":{},"by_source":{}}
    for base in {"half",simple}:
        gain=(ps[base]-y)**2-(ps[selected]-y)**2
        result["paired"][base]={"gain":float(gain.mean()),"round_bootstrap":bootstrap(rows,gain,"issued"),
                                "series_bootstrap":bootstrap(rows,gain,"series")}
    for group,field in (("by_horizon","horizon"),("by_source","fred")):
        for value in sorted({r[field] for r in rows}):
            mask=np.array([r[field]==value for r in rows])
            result[group][str(value)]={"selected":metrics(y[mask],ps[selected][mask]),
                                       "half":metrics(y[mask],ps["half"][mask])}
    out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    for cmd,names in (("prepare",("archive","previous","outdir")),("fit",("dev","test","out")),("score",("pred","test","labels","out"))):
        a=sub.add_parser(cmd)
        for name in names:a.add_argument(name,type=Path)
    a=p.parse_args()
    if a.cmd=="prepare": prepare(a.archive,a.previous,a.outdir)
    elif a.cmd=="fit": fit_predict(a.dev,a.test,a.out)
    else: evaluate(a.pred,a.test,a.labels,a.out)
