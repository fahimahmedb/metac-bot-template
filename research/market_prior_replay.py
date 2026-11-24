"""New-source holdout: archived market priors vs learned corrections.

Kalshi and INFER only; prior tests used other market sources. No official
tournament use. ForecastBench CC BY-SA 4.0. Use archived as-of freeze prices,
not current odds or later price history. Resolution time is an imperfect proxy.
"""
from __future__ import annotations
import argparse
from collections import defaultdict,Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
import hashlib,json,math,re,statistics,tarfile
from pathlib import Path
from urllib.request import urlopen
import numpy as np
from economic_baseline import DATES
from historical_calibration import sha256
from second_holdout import ARCHIVE_SHA,DATA_REF
from local_llm_replay import stable_hash
from rolling_economic import metrics,bootstrap

SOURCES={"kalshi","infer"}
START=date(2024,7,1)
TEST_START=date(2026,7,1)
TEST_END=date(2026,10,26)
FREEZE=date(2026,11,20)
EMBARGO=timedelta(days=30)
ORIGINS=[date(2025,11,1),date(2026,2,1),date(2026,5,1)]
CAP=500
FEATURES=("logit","abs_logit","horizon_log","infer")
CANDIDATES=("market","half","shrink_10","shrink_25","extremize","temperature","affine","context_lr","context_blend")

def parse_date(x):
    try:return date.fromisoformat(str(x)[:10])
    except ValueError:return None

def clip(p):
    return np.clip(p,.005,.995)

def logit(p):
    p=clip(p);return np.log(p/(1-p))

def sigmoid(z):
    return 1/(1+np.exp(-np.clip(z,-30,30)))

def fetch_snapshot(day):
    name=f"{day}-llm.json"
    url=f"https://raw.githubusercontent.com/forecastingresearch/forecastbench-datasets/{DATA_REF}/datasets/question_sets/{name}"
    with urlopen(url,timeout=60) as f:raw=f.read(15_000_001)
    if len(raw)>15_000_000:raise ValueError("snapshot oversized")
    obj=json.loads(raw)
    if obj["forecast_due_date"]!=day or obj["question_set"]!=name:raise ValueError("identity mismatch")
    return day,[r for r in obj["questions"] if r.get("source") in SOURCES and isinstance(r.get("id"),str)],hashlib.sha256(raw).hexdigest()

def prepare(archive,out):
    if sha256(archive)!=ARCHIVE_SHA:raise ValueError("archive changed")
    with ThreadPoolExecutor(max_workers=4) as ex:
        snapshots=list(ex.map(fetch_snapshot,[d for d in DATES if parse_date(d)<TEST_END]))
    # First appearance by event, regardless of whether usable/resolved.
    first={}; candidates={}; counts=Counter(); histories=defaultdict(list)
    for day,items,digest in snapshots:
        issued=parse_date(day)
        for q in items:
            key=q["source"]+":"+q["id"]
            first.setdefault(key,issued)
            try:p=float(q["freeze_datetime_value"])
            except (KeyError,TypeError,ValueError):continue
            freeze=parse_date(q.get("freeze_datetime"))
            close=parse_date(q.get("market_info_close_datetime"))
            if not freeze or freeze>issued or not close or close<=issued or not math.isfinite(p) or not 0<=p<=1:continue
            if (issued-freeze).days>30:continue
            histories[key].append((issued,p))
            if key in candidates:continue
            # A single first usable forecast per event. No realized duration or label in features.
            candidates[key]={"key":key,"source":q["source"],"issued":day,"close":str(close),
                             "first":str(first[key]),"p":p,"logit":float(logit(p)),
                             "abs_logit":abs(float(logit(p))),"horizon_log":math.log1p((close-issued).days),
                             "infer":int(q["source"]=="infer"),"change":0.,"n":1,
                             "question":re.sub(r"\s+"," ",str(q.get("question","")).lower()).strip()}
    labels=defaultdict(set)
    with tarfile.open(archive,"r|gz") as ar:
        for member in ar:
            if not member.isfile() or not member.name.endswith(".json") or member.size>30_000_000:continue
            issued=parse_date(Path(member.name).name[:10])
            if not issued or not START<=issued<TEST_END:continue
            f=ar.extractfile(member)
            if f is None:continue
            obj=json.load(f)
            if not isinstance(obj,dict) or obj.get("organization")!="ForecastBench" or obj.get("question_set")!=f"{issued}-llm.json":continue
            for item in obj.get("forecasts",[]):
                counts["rows_scanned"]+=1
                source=item.get("source"); ident=item.get("id")
                if source not in SOURCES or not isinstance(ident,str) or item.get("resolved") is not True:continue
                key=source+":"+ident
                if key not in candidates:continue
                r=candidates[key]
                try:y=float(item["resolved_to"])
                except (KeyError,ValueError,TypeError):continue
                resolved=parse_date(item.get("resolution_date"))
                if y in (0,1) and resolved and resolved>parse_date(r["issued"]) and resolved<FREEZE:
                    labels[key].add((str(resolved),int(y)))
    counts["candidate_events"]=len(candidates)
    counts["conflicting_events"]=sum(len(v)>1 for v in labels.values())
    rows=[];seen_text=set()
    for key,r in sorted(candidates.items(),key=lambda kv:(kv[1]["issued"],kv[0])):
        if len(labels.get(key,set()))!=1:continue
        if not r["question"] or r["question"] in seen_text:continue
        seen_text.add(r["question"])
        resolved,y=next(iter(labels[key]))
        rows.append({k:v for k,v in r.items() if k!="question"}|{"resolved":resolved,"y":y})
    dev=[r for r in rows if parse_date(r["issued"])<TEST_START]
    pool=[r for r in rows if TEST_START<=parse_date(r["first"])<=parse_date(r["issued"])<TEST_END]
    # Hash-based sample, not labels; source coverage is reported.
    test=sorted(pool,key=lambda r:stable_hash("new-source-v1|"+r["key"]))[:CAP]
    out.mkdir(parents=True,exist_ok=True)
    if len(test)<40 or len(dev)<100:raise ValueError(f"Insufficient new source coverage dev={len(dev)} test={len(test)}")
    for name,obj in (("dev.json",dev),("inputs.json",[{k:v for k,v in r.items() if k not in {"y","resolved"}} for r in test]),
                     ("labels.json",[r["y"] for r in test])):
        (out/name).write_text(json.dumps(obj,separators=(",",":"))+"\n")
    manifest={"archive":ARCHIVE_SHA,"snapshots":{d:h for d,q,h in snapshots},"snapshot_commit":DATA_REF,
              "counts":dict(counts),"dev":len(dev),"test":len(test),"pool":len(pool),
              "dev_sources":dict(Counter(r["source"] for r in dev)),"test_sources":dict(Counter(r["source"] for r in test))}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("PREPARED",json.dumps(manifest|{"snapshots":len(manifest["snapshots"])}),flush=True)

def fit(train):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    y=np.array([r["y"] for r in train]);p=np.array([r["p"] for r in train]);z=logit(p)
    # Fit conservative calibration towards identity on train only.
    best=min((float(np.mean((sigmoid(b*z)-y)**2))+.003*(b-1)**2,b) for b in (.5,.75,1,1.25,1.5,2))
    affine=min((float(np.mean((sigmoid(a+b*z)-y)**2))+.003*(a*a+(b-1)**2),a,b)
               for a in (-.5,-.25,0,.25,.5) for b in (.5,.75,1,1.25,1.5,2))
    lr=make_pipeline(StandardScaler(),LogisticRegression(C=.03,max_iter=500,random_state=19))
    lr.fit(np.array([[r[k] for k in FEATURES] for r in train]),y)
    return best[1],affine[1:],lr

def predictions(rows,fitted):
    b,(a,ab),lr=fitted
    p=np.array([r["p"] for r in rows]);z=logit(p)
    contextual=lr.predict_proba(np.array([[r[k] for k in FEATURES] for r in rows]))[:,1]
    return {"market":p,"half":np.full(len(p),.5),"shrink_10":.9*p+.05,"shrink_25":.75*p+.125,
            "extremize":sigmoid(1.25*z),"temperature":sigmoid(b*z),"affine":sigmoid(a+ab*z),
            "context_lr":contextual,"context_blend":.75*p+.25*contextual}

def training(dev,origin):
    return [r for r in dev if parse_date(r["issued"])<origin and parse_date(r["resolved"])<origin-EMBARGO]

def select(dev):
    folds=[];scores=defaultdict(list)
    for start,end in zip(ORIGINS,ORIGINS[1:]+[TEST_START]):
        tr=training(dev,start)
        val=[r for r in dev if start<=parse_date(r["issued"])<end and parse_date(r["resolved"])<TEST_START-EMBARGO]
        if len(tr)<50 or len(val)<20 or len({r["y"] for r in tr})<2:continue
        ps=predictions(val,fit(tr)); y=np.array([r["y"] for r in val])
        values={k:metrics(y,p)["brier"] for k,p in ps.items()}
        folds.append({"start":str(start),"end":str(end),"train":len(tr),"validation":len(val),"brier":values})
        for k,v in values.items():scores[k].append(v)
    if len(folds)<2:raise ValueError("Insufficient rolling validation coverage")
    avg={k:statistics.mean(v) for k,v in scores.items()}
    best=min(CANDIDATES,key=lambda k:(avg[k],CANDIDATES.index(k)))
    chosen=best if avg["market"]-avg[best]>=.001 else "market"
    return {"folds":folds,"mean_brier":avg,"selected":chosen}

def fit_predict(devpath,inputpath,out):
    dev=json.loads(devpath.read_text());test=json.loads(inputpath.read_text())
    if any("y" in r or "resolved" in r for r in test):raise ValueError("test label leak")
    if {r["key"] for r in dev}&{r["key"] for r in test}:raise ValueError("duplicate events")
    policy=select(dev);tr=training(dev,TEST_START)
    ps=predictions(test,fit(tr))
    obj={"policy":policy,"train_n":len(tr),"input_sha256":sha256(inputpath),"predictions":{k:v.tolist() for k,v in ps.items()}}
    out.write_text(json.dumps(obj,separators=(",",":"))+"\n")
    print("FROZEN",sha256(out),"SELECTED",policy["selected"],flush=True)

def score(predpath,inputpath,labelpath,out):
    p=json.loads(predpath.read_text());rows=json.loads(inputpath.read_text());y=np.array(json.loads(labelpath.read_text()))
    if sha256(inputpath)!=p["input_sha256"] or len(rows)!=len(y):raise ValueError("identity mismatch")
    ps={k:np.array(v) for k,v in p["predictions"].items()}
    chosen=p["policy"]["selected"]
    scores={k:metrics(y,v) for k,v in ps.items()}
    paired={}
    for comparator in ("market","half"):
        gain=(ps[comparator]-y)**2-(ps[chosen]-y)**2
        paired[comparator]={"gain":float(gain.mean()),"round_bootstrap":bootstrap(rows,gain,"issued")}
    report={"n":len(y),"sources":dict(Counter(r["source"] for r in rows)),"test_yes_rate":float(y.mean()),
            "input_sha256":p["input_sha256"],"prediction_sha256":sha256(predpath),"train_n":p["train_n"],
            "policy":p["policy"],"test_scores":scores,"paired":paired}
    out.write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2))

if __name__=="__main__":
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
    for cmd,fields in (("prepare",("archive","out")),("fit",("dev","inputs","out")),("score",("pred","inputs","labels","out"))):
        q=s.add_parser(cmd)
        for f in fields:q.add_argument(f,type=Path)
    a=p.parse_args()
    if a.cmd=="prepare":prepare(a.archive,a.out)
    elif a.cmd=="fit":fit_predict(a.dev,a.inputs,a.out)
    else:score(a.pred,a.inputs,a.labels,a.out)
