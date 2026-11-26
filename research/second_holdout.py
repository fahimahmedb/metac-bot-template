"""Second, independent temporal holdout: a learned text-only prior and ensembles.

Research only, no tournament access. First experiment's test dates are not
reused as test. Archived questions are snapshots, not current question pages.
ForecastBench (CC BY-SA 4.0): https://github.com/forecastingresearch/forecastbench-datasets
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics
import tarfile
from urllib.request import urlopen

from historical_calibration import Row, score, sha256

DATA_REF = "86b92ba06ed34d606d633bff3e99af54dd447d3a"
ARCHIVE_SHA = "3b3b9630f2ccf4da401e703266a116cdc7de535eabb4cb44c9a10d1c01315b0f"
TRAIN_END = date(2026, 4, 1)
VALID_END = date(2026, 7, 1)
TEST_END = date(2026, 10, 26)
LABEL_FREEZE = date(2026, 11, 20)
EMBARGO = timedelta(days=30)
MIN_TRAIN, MIN_VALID, MIN_TEST = 100, 30, 40
SOURCES = {"metaculus", "manifold", "polymarket"}
VARIANTS = {"zero-shot", "scratchpad", "scratchpad-with-news",
            "scratchpad-with-second-news", "superforecaster-with-news-1",
            "superforecaster-with-news-2", "superforecaster-with-news-3",
            "zero-shot-with-freeze-values", "scratchpad-with-freeze-values",
            "scratchpad-with-news-with-freeze-values"}

@dataclass(frozen=True)
class Event:
    key: str
    issued: date
    resolved: date
    y: int

def variant_of(model, item):
    """Only explicitly recognized archive variants; never infer from unknown tags."""
    explicit = item.get("forecast_variant_key")
    if explicit:
        return explicit if explicit in VARIANTS else None
    match = re.search(r"\(([^()]*)\)$", model.lower())
    if match:
        v = match.group(1).replace(" ", "-")
        return v if v in VARIANTS else None
    return None

def context_group(variant):
    return "market-context" if "freeze-values" in variant else "no-explicit-market-context"

def partition(event):
    if event.issued >= event.resolved:
        return None
    if event.issued < TRAIN_END and event.resolved < TRAIN_END-EMBARGO:
        return "train"
    if TRAIN_END <= event.issued < VALID_END and event.resolved < VALID_END-EMBARGO:
        return "validation"
    if VALID_END <= event.issued < TEST_END and event.resolved < LABEL_FREEZE:
        return "test"
    return None

def read_archive(path):
    """Collect earliest event dates across ALL eligible snapshots, not each model."""
    if sha256(path) != ARCHIVE_SHA:
        raise ValueError("Archived forecasts changed; stop rather than silently changing holdout.")
    seen = {}
    labels = defaultdict(set)
    preds = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    counts = Counter()
    with tarfile.open(path, "r|gz") as ar:
        for member in ar:
            if not member.isfile() or not member.name.endswith(".json") or member.size>30_000_000:
                continue
            try:
                issued = date.fromisoformat(Path(member.name).name[:10])
            except ValueError:
                continue
            if not date(2024,7,1) <= issued < TEST_END:
                continue
            file = ar.extractfile(member)
            if file is None:
                continue
            obj = json.load(file)
            if not isinstance(obj, dict) or obj.get("question_set") != f"{issued}-llm.json":
                continue
            org = obj.get("organization")
            model_org = obj.get("model_organization")
            model = obj.get("model")
            if org!="ForecastBench" or not model_org or model_org=="ForecastBench" or not model:
                continue
            for item in obj.get("forecasts",[]):
                counts["rows_seen"] += 1
                source, ident = item.get("source"), item.get("id")
                if source not in SOURCES or not isinstance(ident,str):
                    continue
                key = f"{source}:{ident}"
                # Include unresolved and imputed rows in the earliest appearance
                # registry so they cannot move an old event into the new holdout.
                seen[key] = min(seen.get(key,issued),issued)
                if item.get("imputed") is not False or item.get("resolved") is not True:
                    continue
                try:
                    p=float(item["forecast"])
                    y=float(item["resolved_to"])
                    resolved=date.fromisoformat(str(item["resolution_date"])[:10])
                except (KeyError,TypeError,ValueError):
                    continue
                if not (math.isfinite(p) and 0<=p<=1 and y in (0,1) and issued<resolved<LABEL_FREEZE):
                    continue
                labels[key].add((resolved,int(y)))
                counts["eligible_rows"] += 1
                variant = variant_of(model,item)
                if variant is not None:
                    group = context_group(variant)
                    # Distinct model variants within one provider receive no extra
                    # provider weight. Preserve one value per exact model variant.
                    preds[(key,issued)][group][model_org][model+"|"+variant] = p
    events = {}
    for key, possibilities in labels.items():
        if len(possibilities)!=1:
            counts["conflicting_labels"]+=1
            continue
        resolved,y=next(iter(possibilities))
        event=Event(key,seen[key],resolved,y)
        if partition(event):
            events[key]=event
    counts["unique_partitioned_events"]=len(events)
    return events,preds,dict(counts)

def get_question_texts(events):
    """Download pinned historical snapshots; whitelist ONLY question text."""
    rounds=defaultdict(set)
    for e in events.values():
        rounds[e.issued].add(e.key)
    def fetch(pair):
        issued, required=pair
        name=f"{issued}-llm.json"
        url=f"https://raw.githubusercontent.com/forecastingresearch/forecastbench-datasets/{DATA_REF}/datasets/question_sets/{name}"
        with urlopen(url,timeout=60) as stream:
            raw=stream.read(15_000_001)
        if len(raw)>15_000_000:
            raise ValueError("snapshot too large")
        obj=json.loads(raw)
        if obj.get("forecast_due_date")!=str(issued) or obj.get("question_set")!=name:
            raise ValueError("snapshot identity mismatch")
        out={}
        for item in obj["questions"]:
            key=f"{item.get('source')}:{item.get('id')}"
            question=item.get("question")
            if key in required and isinstance(question,str) and question.strip():
                # No metadata, freeze value, URLs, answer or background passed on.
                question=re.sub(r"https?://\S+","[URL]",question)
                out[key]=question.strip()
        return out, {"date":str(issued),"sha256":hashlib.sha256(raw).hexdigest(),"matched":len(out)}
    texts, manifest={},[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        for found,record in ex.map(fetch,sorted(rounds.items())):
            texts.update(found)
            manifest.append(record)
    return texts,manifest

def text_features(event,text):
    # Source and event ID are deliberately omitted. Keep the actual question
    # and mask year literals to reduce memorization of a specific date.
    return re.sub(r"\b(?:19|20)\d{2}\b","YEAR",text.lower())

def pooled(event,preds,group):
    providers=preds.get((event.key,event.issued),{}).get(group,{})
    return {k:statistics.median(values.values()) for k,values in providers.items() if values}

def logit(p):
    p=min(.999,max(.001,p))
    return math.log(p/(1-p))

def sigmoid(z):
    return 1/(1+math.exp(-z))

def aggregate(providers,method,weights=None):
    values=list(providers.values())
    if not values:
        raise ValueError("empty ensemble")
    mean=statistics.mean(values)
    if method=="mean":
        return mean
    if method=="median":
        return statistics.median(values)
    if method=="logit":
        return sigmoid(statistics.mean(logit(p) for p in values))
    if method=="tempered-logit":
        return sigmoid(.7*statistics.mean(logit(p) for p in values))
    if method=="weighted":
        weights=weights or {}
        return sum(weights.get(k,1)*p for k,p in providers.items())/sum(weights.get(k,1) for k in providers)
    raise ValueError(method)

def metric(events,ps):
    return score([Row(e.key,e.issued,e.resolved,.5,e.y) for e in events],ps)

def boot(events,baseline,challenger):
    rounds=defaultdict(list)
    for e,p,q in zip(events,baseline,challenger):
        rounds[e.issued].append((p-e.y)**2-(q-e.y)**2)
    blocks=list(rounds.values())
    if len(blocks)<5:
        return {"rounds":len(blocks),"ci95":None}
    rng=random.Random(20261125)
    samples=[]
    for _ in range(2000):
        draws=[rng.choice(blocks) for _ in blocks]
        samples.append(sum(map(sum,draws))/sum(map(len,draws)))
    samples.sort()
    return {"rounds":len(blocks),"ci95":[samples[49],samples[1949]]}

def grouped_events(events):
    out=defaultdict(list)
    for e in sorted(events,key=lambda x:(x.issued,x.key)):
        out[partition(e)].append(e)
    return out

def ensemble_eval(events,preds,group):
    pools={e.key:pooled(e,preds,group) for e in events}
    parts=grouped_events([e for e in events if len(pools[e.key])>=2])
    t,v,s=(parts[k] for k in ("train","validation","test"))
    report={"group":group,"n":[len(t),len(v),len(s)]}
    if len(t)<MIN_TRAIN or len(v)<MIN_VALID or len(s)<MIN_TEST:
        return dict(report,status="BLOCK_INSUFFICIENT_COVERAGE")
    # Smoothed provider reliability from training labels only. No future data.
    errors=defaultdict(list)
    for e in t:
        for name,p in pools[e.key].items():
            errors[name].append((p-e.y)**2)
    weights={k:.20/((sum(es)+50*.20)/(len(es)+50)) for k,es in errors.items()}
    methods=["mean","median","logit","tempered-logit","weighted"]
    def predictions(rows,method):
        return [aggregate(pools[e.key],method,weights) for e in rows]
    val={m:metric(v,predictions(v,m))["brier"] for m in methods}
    best=min(methods,key=lambda m:(val[m],m))
    chosen=best if val["mean"]-val[best]>=.002 else "mean"
    # Freeze chosen policy before reading the test labels for scores.
    p0=predictions(s,"mean")
    p1=predictions(s,chosen)
    member_mean=sum(statistics.mean((p-e.y)**2 for p in pools[e.key].values()) for e in s)/len(s)
    raw,adjusted=metric(s,p0),metric(s,p1)
    return dict(report,status="SCORED",chosen=chosen,validation_brier=val,
                uniform_ensemble=raw,selected_ensemble=adjusted,
                mean_provider_member_brier=member_mean,
                brier_gain_vs_uniform=raw["brier"]-adjusted["brier"],
                paired_round_bootstrap=boot(s,p0,p1))

def text_eval(events,texts):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    parts=grouped_events([e for e in events if e.key in texts])
    t,v,s=(parts[k] for k in ("train","validation","test"))
    report={"n":[len(t),len(v),len(s)]}
    if len(t)<MIN_TRAIN or len(v)<MIN_VALID or len(s)<MIN_TEST:
        return dict(report,status="BLOCK_INSUFFICIENT_COVERAGE")
    rate=(sum(e.y for e in t)+1)/(len(t)+2)
    def x(rows):
        return [text_features(e,texts[e.key]) for e in rows]
    train_x,val_x,test_x=x(t),x(v),x(s)
    models={}
    # Tfidf vocabulary, IDF and logistic weights are learned only on train.
    for c in (.1,1.,10.):
        model=make_pipeline(TfidfVectorizer(ngram_range=(1,2),min_df=3,max_features=15000,sublinear_tf=True),
                            LogisticRegression(C=c,solver="liblinear",random_state=17,max_iter=500))
        model.fit(train_x,[e.y for e in t])
        models[str(c)]=model
    val={"base_rate":metric(v,[rate]*len(v))["brier"]}
    for name,model in models.items():
        val[name]=metric(v,list(model.predict_proba(val_x)[:,1]))["brier"]
    best=min(models,key=lambda m:(val[m],m))
    chosen=best if val["base_rate"]-val[best]>=.002 else "base_rate"
    baseline=[rate]*len(s)
    pred=baseline[:] if chosen=="base_rate" else list(models[chosen].predict_proba(test_x)[:,1])
    raw,adjusted=metric(s,baseline),metric(s,pred)
    return dict(report,status="SCORED",train_rate=rate,validation_brier=val,chosen=chosen,
                baseline=raw,constant_half=metric(s,[.5]*len(s)),selected=adjusted,
                brier_gain=raw["brier"]-adjusted["brier"],
                paired_round_bootstrap=boot(s,baseline,pred))

def main(path,output):
    events,preds,counts=read_archive(path)
    # First-stage policies declared in source. The entire held-out period is new
    # relative to experiment #1. Both market-context groups reported even if blocked.
    all_events=list(events.values())
    texts,manifest=get_question_texts(events)
    # Detect exact duplicate question texts across dates/sources before selecting
    # the final sample. Keep earliest only; semantic duplicates remain possible.
    unique={}
    for e in sorted(all_events,key=lambda e:(e.issued,e.key)):
        if e.key in texts:
            key=re.sub(r"\s+"," ",texts[e.key].lower()).strip()
            unique.setdefault(key,e)
    all_events=list(unique.values())
    groups=grouped_events(all_events)
    report={"archive_sha256":sha256(path),"question_snapshot_ref":DATA_REF,
            "split":{"train_end":str(TRAIN_END),"validation_end":str(VALID_END),"test_end":str(TEST_END),
                     "label_freeze":str(LABEL_FREEZE),"embargo_days":30},
            "counts":counts,"snapshots":manifest,
            "distinct_questions":[len(groups[k]) for k in ("train","validation","test")],
            "text_prior":text_eval(all_events,texts),
            "ensembles":[ensemble_eval(all_events,preds,g) for g in ("no-explicit-market-context","market-context")]}
    output.write_text(json.dumps(report,indent=2)+"\n")
    # Avoid dumping all snapshot records into job logs.
    print(json.dumps({k:v for k,v in report.items() if k!="snapshots"},indent=2))
    if not any(x["status"]=="SCORED" for x in [report["text_prior"],*report["ensembles"]]):
        raise SystemExit("No qualifying experiment")
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("archive",type=Path)
    ap.add_argument("--output",type=Path,default=Path("second_holdout_report.json"))
    args=ap.parse_args()
    main(args.archive,args.output)
