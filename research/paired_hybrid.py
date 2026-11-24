"""Predeclared paired comparison of the numeric baseline and old-model replay.

Run only when both frozen prediction artifacts exist. No selection on test
labels. This is the same replay holdout, not an independent fourth test.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import random
from historical_calibration import Row, score, transform, sha256
from economic_baseline import INPUT_SHA, METHODS

def aligned(llm, numeric):
    if llm["input_sha256"]!=INPUT_SHA or numeric["input_sha256"]!=INPUT_SHA:
        raise ValueError("Different inputs")
    a={r["key"]:r for r in llm["predictions"]}
    b={r["key"]:r for r in numeric["predictions"]}
    if len(a)!=len(llm["predictions"]) or len(b)!=len(numeric["predictions"]) or set(a)!=set(b):
        raise ValueError("Duplicate or unmatched questions")
    out=[]
    for key,r in sorted(a.items()):
        s=b[key]
        for field in ("split","issued","target_date"):
            if r[field]!=s[field]:
                raise ValueError("Metadata mismatch")
        out.append((r,s))
    return out

def choose_on_validation(pairs, labels):
    groups=defaultdict(list)
    for r,s in pairs:
        groups[r["split"]].append((r,s))
    if {k:len(v) for k,v in groups.items()}!={"train":48,"validation":32,"test":41}:
        raise ValueError("Unexpected holdout sizes")

    def rows(split):
        return [Row(r["key"],date.fromisoformat(r["issued"]),date.fromisoformat(r["target_date"]),
                    .5,labels[r["key"]]) for r,s in groups[split]]
    def numeric_pred(split,m):
        return [s[m] for r,s in groups[split]]
    def llm_pred(split,c):
        p=[r[c["method"]] for r,s in groups[split]]
        return [transform(x,c["a"],c["b"]) for x in p] if c["calibrated"] else p
    def loss(split,p):
        return score(rows(split),p)["brier"]
    tr=rows("train")
    llms=[]
    for method in ("direct","structured"):
        raw={"method":method,"a":0,"b":1,"calibrated":False}
        p=llm_pred("train",raw)
        best=min((score(tr,[transform(x,a,b) for x in p])["brier"]+.01*(a*a+(b-1)**2),a,b)
                 for a in (-.5,0,.5) for b in (.5,1,1.5))
        llms += [raw, {"method":method,"a":best[1],"b":best[2],"calibrated":True}]
    # Exactly one selected numerical and one selected LLM policy. Then only
    # three fixed blend weights. Baseline 50% remains an explicit fallback.
    num=min(METHODS,key=lambda m:(loss("validation",numeric_pred("validation",m)),m))
    lm=min(llms,key=lambda c:loss("validation",llm_pred("validation",c)))
    candidates=[("half",0),("numeric",0),("llm",1),("blend_25",.25),("blend_50",.5),("blend_75",.75)]
    def predict(split,c):
        name,w=c
        if name=="half": return [.5]*len(groups[split])
        return [(1-w)*p+w*q for p,q in zip(numeric_pred(split,num),llm_pred(split,lm))]
    val={c[0]:loss("validation",predict("validation",c)) for c in candidates}
    best=min(candidates,key=lambda c:(val[c[0]],candidates.index(c)))
    chosen=best if val["half"]-val[best[0]]>=.005 else candidates[0]
    # All parameters and the chosen policy are frozen before accessing test
    # labels. Descriptive comparison of both component policies is reported.
    return {"numeric_method":num,"llm_policy":lm,"validation":val,"selected":chosen[0]}, groups, predict, candidates

def bootstrap(rows, baseline, candidate):
    grouped=defaultdict(list)
    for r,p,q in zip(rows,baseline,candidate):
        grouped[r.issued].append((p-r.y)**2-(q-r.y)**2)
    blocks=list(grouped.values())
    if len(blocks)<5:
        return {"rounds":len(blocks),"ci95":None}
    rng=random.Random(20261126)
    samples=[]
    for _ in range(2000):
        picks=[rng.choice(blocks) for _ in blocks]
        samples.append(sum(map(sum,picks))/sum(map(len,picks)))
    samples.sort()
    return {"rounds":len(blocks),"ci95":[samples[49],samples[1949]]}

def evaluate(llm_path,numeric_path,label_path,out):
    llm=json.loads(llm_path.read_text())
    numeric=json.loads(numeric_path.read_text())
    labels=json.loads(label_path.read_text())
    pairs=aligned(llm,numeric)
    if set(labels)!={r["key"] for r,s in pairs} or any(y not in (0,1) for y in labels.values()):
        raise ValueError("Label mismatch")
    # Explicitly remove test outcomes from the selection call.
    fit_labels={r["key"]:labels[r["key"]] for r,s in pairs if r["split"]!="test"}
    policy,groups,predict,candidates=choose_on_validation(pairs,fit_labels)
    chosen=next(c for c in candidates if c[0]==policy["selected"])
    p=predict("test",chosen)
    baseline=predict("test",("half",0))
    test=[Row(r["key"],date.fromisoformat(r["issued"]),date.fromisoformat(r["target_date"]),
              .5,labels[r["key"]]) for r,s in groups["test"]]
    result={"input_sha256":INPUT_SHA,"llm_predictions_sha256":sha256(llm_path),
            "numeric_predictions_sha256":sha256(numeric_path),
            "model":llm["model"],"revision":llm["revision"],
            "policy":policy,"selected_test":score(test,p),"half_test":score(test,baseline),
            "descriptive_test":{c[0]:score(test,predict("test",c)) for c in candidates},
            "paired_round_bootstrap":bootstrap(test,baseline,p)}
    out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("llm","numeric","labels","out"): p.add_argument(name,type=Path)
    a=p.parse_args()
    evaluate(a.llm,a.numeric,a.labels,a.out)
