"""Paired economic baseline for sealed replay v1.

No label or forecast archive in prediction process. Only published historical
snapshot values available at each row's forecast time. Research-only. This is
a comparator on the SAME 121 inputs, not another independent holdout.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from urllib.request import urlopen
from statistics import median

from local_llm_replay import event_id, stable_hash, DATA_REF
from historical_calibration import Row, score, sha256

INPUT_SHA="80cc1d965c61e981f481c1902c385305903dfa5ab2f007f3cfa370c523d5597e"
DATES="""2024-07-21 2025-03-02 2025-03-16 2025-03-30 2025-04-13 2025-04-27 2025-05-11 2025-05-25 2025-06-08 2025-06-22 2025-08-03 2025-08-17 2025-08-31 2025-10-26 2025-11-09 2025-11-23 2025-12-07 2025-12-21 2026-01-04 2026-01-18 2026-02-01 2026-02-15 2026-03-01 2026-03-15 2026-03-29 2026-04-12 2026-04-26 2026-05-10 2026-05-24 2026-06-07 2026-06-21 2026-07-05 2026-07-19 2026-08-02 2026-08-16 2026-08-30 2026-09-13 2026-09-27 2026-10-11 2026-10-25""".split()
METHODS=("half","empirical","recent","momentum","mean_reversion")

def fetch_snapshot(issued):
    name=f"{issued}-llm.json"
    url=f"https://raw.githubusercontent.com/forecastingresearch/forecastbench-datasets/{DATA_REF}/datasets/question_sets/{name}"
    with urlopen(url,timeout=60) as f:
        raw=f.read(15_000_001)
    if len(raw)>15_000_000:
        raise ValueError("oversize snapshot")
    obj=json.loads(raw)
    if obj["forecast_due_date"]!=issued or obj["question_set"]!=name:
        raise ValueError("snapshot identity mismatch")
    result={}
    for r in obj["questions"]:
        if r.get("source") not in {"fred","dbnomics"} or r.get("id") is None:
            continue
        try:
            freeze=date.fromisoformat(str(r["freeze_datetime"])[:10])
            v=float(r["freeze_datetime_value"])
        except (KeyError,TypeError,ValueError):
            continue
        if freeze>date.fromisoformat(issued) or not math.isfinite(v):
            continue
        key=event_id(r["source"],r["id"])
        item=(freeze,v,r.get("resolution_dates",[]),str(r.get("question","")))
        if key in result and result[key]!=item:
            raise ValueError("ambiguous series in snapshot")
        result[key]=item
    return issued,result,hashlib.sha256(raw).hexdigest()

def matching_deltas(history,horizon):
    """Nonoverlapping historical pairs of similar duration; no future values."""
    chosen=[]
    i=0
    while i<len(history)-1:
        t,v=history[i]
        valid=[(abs((s-t).days-horizon),j) for j,(s,w) in enumerate(history[i+1:],i+1)
               if abs((s-t).days-horizon)<=max(7,horizon*.35)]
        if not valid:
            i+=1
            continue
        _,j=min(valid)
        chosen.append((history[j][0],history[j][1]-v))
        i=j
    return chosen

def probabilities(history,horizon):
    if horizon<=0:
        raise ValueError("nonpositive horizon")
    pairs=matching_deltas(history,horizon)
    n=len(pairs)
    if n<3:
        return {k:.5 for k in METHODS},n
    # Strict increase is the question contract; equality counts as NO.
    empirical=(sum(d>0 for _,d in pairs)+2)/(n+4)
    recent_pairs=pairs[-6:]
    recent=(sum(d>0 for _,d in recent_pairs)+2)/(len(recent_pairs)+4)
    # Low-amplitude directional alternatives, not confident extrapolation.
    direction=0
    if len(history)>=4:
        change=history[-1][1]-history[-4][1]
        direction=(change>0)-(change<0)
    confidence=min(1,n/8)
    return {"half":.5,"empirical":empirical,"recent":recent,
            "momentum":.5+.15*confidence*direction,
            "mean_reversion":.5-.15*confidence*direction},n

def predict(inputs_path,out):
    if sha256(inputs_path)!=INPUT_SHA:
        raise ValueError("Unexpected replay inputs")
    rows=json.loads(inputs_path.read_text())
    last=max(r["issued"] for r in rows)
    dates=[d for d in DATES if d<=last]
    with ThreadPoolExecutor(max_workers=4) as pool:
        fetched=list(pool.map(fetch_snapshot,dates))
    snapshots={d:data for d,data,digest in fetched}
    manifest={d:digest for d,data,digest in fetched}
    preds=[]
    for r in rows:
        issued=date.fromisoformat(r["issued"])
        known=date.fromisoformat(r["known_date"])
        target=date.fromisoformat(r["target_date"])
        matches=[(s,entry) for s,entry in snapshots[r["issued"]].items()
                 if stable_hash("replay-input|"+s+"|"+r["issued"]+"|"+r["target_date"])==r["key"]]
        if len(matches)!=1:
            raise ValueError("cannot recover unique snapshot identity")
        s,(freeze,v,targets,question)=matches[0]
        # Verify the date was an ex-ante scheduled target, not a hindsight date.
        if not isinstance(targets,list) or r["target_date"] not in targets:
            raise ValueError("target date not in historical question snapshot")
        if freeze!=known or v!=float(r["known_value"]):
            raise ValueError("historical value mismatch")
        # Only declared increase templates. Otherwise use neutral fallback.
        eligible=any(x in question.lower() for x in ("have increased","will exceed","will be higher"))
        hist={}
        for d in dates:
            if date.fromisoformat(d)>issued: break
            entry=snapshots[d].get(s)
            if entry is None: continue
            f,w,_,_=entry
            if f<=known:
                hist[f]=w
        history=sorted(hist.items())
        values,n=probabilities(history,(target-issued).days) if eligible else ({k:.5 for k in METHODS},0)
        preds.append({"key":r["key"],"split":r["split"],"issued":r["issued"],
                      "target_date":r["target_date"],"historical_pairs":n,
                      "history_observations":len(history),"template_eligible":eligible,**values})
    obj={"input_sha256":sha256(inputs_path),"snapshot_commit":DATA_REF,
         "snapshot_sha256":manifest,"predictions":preds}
    out.write_text(json.dumps(obj,indent=2)+"\n")
    print("FROZEN_BASELINES",len(preds),sha256(out),flush=True)

def evaluate(pred,labels,out):
    p=json.loads(pred.read_text())
    y=json.loads(labels.read_text())
    rows=p["predictions"]
    assert set(y)=={r["key"] for r in rows}
    grouped=defaultdict(list)
    for r in rows: grouped[r["split"]].append(r)
    def metrics(split,method):
        rr=grouped[split]
        return score([Row(r["key"],date.fromisoformat(r["issued"]),date.fromisoformat(r["target_date"]),r[method],y[r["key"]]) for r in rr],
                     [r[method] for r in rr])
    val={m:metrics("validation",m) for m in METHODS}
    best=min(METHODS,key=lambda m:(val[m]["brier"],m))
    selected=best if val["half"]["brier"]-val[best]["brier"]>=.005 else "half"
    test=grouped["test"]
    report={"input_sha256":p["input_sha256"],"frozen_prediction_sha256":sha256(pred),
            "counts":{k:len(v) for k,v in grouped.items()},"selected":selected,"validation":val,
            "selected_test":metrics("test",selected),"half_test":metrics("test","half"),
            "descriptive_test":{m:metrics("test",m) for m in METHODS},
            "test_with_3_or_more_pairs":sum(r["historical_pairs"]>=3 for r in test),
            "test_median_pairs":median(r["historical_pairs"] for r in test),
            "test_template_eligible":sum(r["template_eligible"] for r in test)}
    out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    s=p.add_subparsers(dest="cmd",required=True)
    a=s.add_parser("predict");a.add_argument("inputs",type=Path);a.add_argument("out",type=Path)
    a=s.add_parser("score");a.add_argument("pred",type=Path);a.add_argument("labels",type=Path);a.add_argument("out",type=Path)
    args=p.parse_args()
    if args.cmd=="predict": predict(args.inputs,args.out)
    else: evaluate(args.pred,args.labels,args.out)
