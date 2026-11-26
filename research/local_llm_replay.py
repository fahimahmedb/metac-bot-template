"""Offline inference on a pinned 2024 model, not on previously tested markets.

Three disjoint runner jobs: prepare sealed labels; infer from masked inputs;
score and calibrate after outputs are frozen. Data: ForecastBench CC BY-SA 4.0.
No APIs with credentials and no live prediction submission.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import tarfile
from urllib.request import urlopen

from historical_calibration import Row, score, sha256, transform
from second_holdout import DATA_REF, ARCHIVE_SHA

MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
REVISION = "7ae5576"  # Sep 25 2024, HF commit history; resolve full SHA before download
SOURCES = {"fred", "dbnomics"}
CAP = {"train":48,"validation":32,"test":64}
MIN_N = {"train":30,"validation":20,"test":40}
TRAIN_END=date(2026,1,1)
VAL_END=date(2026,6,1)
TEST_START=date(2026,7,1)
TEST_END=date(2026,10,26)
FREEZE=date(2026,11,20)
EMBARGO=timedelta(days=30)

def stable_hash(s):
    return hashlib.sha256(s.encode()).hexdigest()

def event_id(src,ident):
    return src+":"+json.dumps(ident,sort_keys=True,separators=(",",":"))

def assign_split(series,issued,resolved):
    """Disjoint series groups and chronological label availability."""
    bucket=int(stable_hash("replay-v1|"+series)[:8],16)%10
    if resolved<=issued:
        return None
    if bucket<6 and date(2025,3,1)<=issued<TRAIN_END and resolved<TRAIN_END-EMBARGO:
        return "train"
    if 6<=bucket<8 and TRAIN_END<=issued<VAL_END and resolved<VAL_END-EMBARGO:
        return "validation"
    if bucket>=8 and TEST_START<=issued<TEST_END and resolved<FREEZE:
        return "test"
    return None

def sanitize(s):
    return re.sub(r"https?://\S+","[URL removed]",str(s))[:1200]

def prepare(archive,outdir):
    if sha256(archive)!=ARCHIVE_SHA:
        raise ValueError("Archive changed")
    # Read only final binary labels, never pass archived model probabilities
    # to the inference job. One earliest selected observation per series.
    observations=defaultdict(set)
    with tarfile.open(archive,"r|gz") as ar:
        for member in ar:
            if not member.isfile() or not member.name.endswith(".json") or member.size>30_000_000:
                continue
            try: issued=date.fromisoformat(Path(member.name).name[:10])
            except ValueError: continue
            if not date(2025,3,1)<=issued<TEST_END:
                continue
            f=ar.extractfile(member)
            if f is None: continue
            obj=json.load(f)
            if not isinstance(obj,dict) or obj.get("organization")!="ForecastBench":
                continue
            if obj.get("question_set")!=f"{issued}-llm.json": continue
            for item in obj.get("forecasts",[]):
                src=item.get("source")
                if src not in SOURCES or item.get("id") is None or item.get("resolved") is not True:
                    continue
                try:
                    resolved=date.fromisoformat(str(item["resolution_date"])[:10])
                    y=float(item["resolved_to"])
                except (KeyError,ValueError,TypeError): continue
                if y not in (0,1): continue
                series=event_id(src,item["id"])
                split=assign_split(series,issued,resolved)
                if split:
                    observations[(series,issued,resolved,split)].add(int(y))
    chosen={}
    for key,ys in sorted(observations.items(),key=lambda kv:(kv[0][1],kv[0][2],kv[0][0])):
        series,issued,resolved,split=key
        if len(ys)==1:
            chosen.setdefault(series,(issued,resolved,split,next(iter(ys))))
    # Select by fixed hash, not observed outcome. Extra candidates only to
    # cover missing snapshots/fields; final cap still hash-ranked.
    bysplit=defaultdict(list)
    for series,(issued,resolved,split,y) in chosen.items():
        bysplit[split].append((series,issued,resolved,y))
    pending={}
    for split,rows in bysplit.items():
        ranked=sorted(rows,key=lambda r:stable_hash("sample-v1|"+r[0]))
        for series,issued,resolved,y in ranked[:CAP[split]*3]:
            pending[(series,issued)]=(resolved,split,y)
    byround=defaultdict(set)
    for series,issued in pending: byround[issued].add(series)
    def fetch(pair):
        issued,series_set=pair
        name=f"{issued}-llm.json"
        url=f"https://raw.githubusercontent.com/forecastingresearch/forecastbench-datasets/{DATA_REF}/datasets/question_sets/{name}"
        with urlopen(url,timeout=60) as stream: raw=stream.read(15_000_001)
        if len(raw)>15_000_000: raise ValueError("Snapshot too large")
        obj=json.loads(raw)
        if obj.get("forecast_due_date")!=str(issued) or obj.get("question_set")!=name:
            raise ValueError("Snapshot mismatch")
        out={}
        for item in obj.get("questions",[]):
            if item.get("source") not in SOURCES or item.get("id") is None: continue
            series=event_id(item["source"],item["id"])
            if series not in series_set: continue
            resolved,split,y=pending[(series,issued)]
            try: freeze=date.fromisoformat(str(item["freeze_datetime"])[:10])
            except (KeyError,ValueError): continue
            if freeze>issued or not isinstance(item.get("question"),str): continue
            # Whitelist historically available snapshot fields. For non-market
            # dataset questions the freeze value is an observed series value.
            if not item["question"].strip(): continue
            opaque=stable_hash("replay-input|"+series+"|"+str(issued)+"|"+str(resolved))
            record={"key":opaque,"split":split,"source":item["source"],"issued":str(issued),
                    "target_date":str(resolved),"question":sanitize(item["question"]),
                    "background":sanitize(item.get("background","")),
                    "criteria":sanitize(item.get("resolution_criteria","")),
                    "known_date":str(freeze),"known_value":sanitize(item.get("freeze_datetime_value","")),
                    "known_value_explanation":sanitize(item.get("freeze_datetime_value_explanation",""))}
            out[series]=(record,y)
        return out,{"date":str(issued),"sha256":hashlib.sha256(raw).hexdigest()}
    available,manifest={},[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        for found,meta in ex.map(fetch,sorted(byround.items())):
            available.update(found)
            manifest.append(meta)
    inputs,labels=[],{}
    counts={}
    for split in CAP:
        ranked=sorted((s for s,(r,y) in available.items() if r["split"]==split),
                      key=lambda s:stable_hash("sample-v1|"+s))[:CAP[split]]
        counts[split]=len(ranked)
        if len(ranked)<MIN_N[split]:
            raise ValueError("Insufficient matched snapshots: "+str(counts))
        for series in ranked:
            r,y=available[series]
            inputs.append(r)
            labels[r["key"]]=y
    assert len(inputs)==len(labels)
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/"inputs.json").write_text(json.dumps(inputs,indent=2)+"\n")
    (outdir/"labels.json").write_text(json.dumps(labels,sort_keys=True)+"\n")
    (outdir/"manifest.json").write_text(json.dumps({"counts":counts,"archive_sha256":ARCHIVE_SHA,
              "snapshot_ref":DATA_REF,"snapshots":manifest},indent=2)+"\n")
    print("PREPARED",counts,"input_sha256",sha256(outdir/"inputs.json"))

def make_prompt(row,structured):
    intro="Estimate the outcome of this historical forecasting question as of the stated forecast date. Do not use later facts."
    if structured:
        intro+=" Consider the exact resolution criterion, time horizon, current observed value, ordinary variation and a plausible opposite outcome. Do not assume a trend without evidence."
    return (intro+"\nForecast date: "+row["issued"]+"\nTarget date: "+row["target_date"]+
            "\nQuestion: "+row["question"]+"\nBackground: "+row["background"]+
            "\nResolution criterion: "+row["criteria"]+"\nObserved value on "+row["known_date"]+": "+
            row["known_value"]+"\nMeaning: "+row["known_value_explanation"]+
            "\nAnswer with exactly Yes or No. Is the outcome more likely to resolve Yes?")

def infer(inputs_path,output):
    import torch
    from huggingface_hub import HfApi, snapshot_download
    from transformers import AutoModelForCausalLM, AutoTokenizer
    records=json.loads(inputs_path.read_text())
    forbidden={"y","label","outcome","resolved_to","forecast","p","url","freeze_datetime_value"}
    if any(forbidden.intersection(r) for r in records): raise ValueError("Forbidden field in inference input")
    info=HfApi().model_info(MODEL,revision=REVISION)
    revision=info.sha
    if not revision or not revision.startswith(REVISION): raise ValueError("Model revision mismatch")
    folder=snapshot_download(MODEL,revision=revision,allow_patterns=["*.json","*.safetensors","*.txt"])
    tok=AutoTokenizer.from_pretrained(folder,trust_remote_code=False,local_files_only=True)
    torch.set_num_threads(2)
    model=AutoModelForCausalLM.from_pretrained(folder,trust_remote_code=False,local_files_only=True,
                 torch_dtype=torch.float32,use_safetensors=True).eval()
    yes,no=tok.encode("Yes",add_special_tokens=False),tok.encode("No",add_special_tokens=False)
    if len(yes)!=1 or len(no)!=1 or yes==no: raise ValueError("Expected two single answer tokens")
    preds=[]
    with torch.inference_mode():
        for i,r in enumerate(records):
            values={}
            for name,structured in (("direct",False),("structured",True)):
                chat=[{"role":"user","content":make_prompt(r,structured)}]
                ids=tok.apply_chat_template(chat,add_generation_prompt=True,return_tensors="pt")
                logits=model(input_ids=ids,use_cache=False).logits[0,-1,[yes[0],no[0]]]
                p=float(torch.softmax(logits,dim=0)[0])
                if not math.isfinite(p): raise ValueError("Nonfinite probability")
                values[name]=p
            preds.append({"key":r["key"],"split":r["split"],"issued":r["issued"],"target_date":r["target_date"],
                          **values})
            if (i+1)%16==0: print("INFERRED",i+1,flush=True)
    report={"model":MODEL,"revision":revision,"method":"conditional Yes/No next-token softmax; not verbal probability",
            "input_sha256":sha256(inputs_path),"predictions":preds}
    output.write_text(json.dumps(report,indent=2)+"\n")
    print("FROZEN",len(preds),"sha256",sha256(output),"model",revision)

def evaluate(prediction_path,labels_path,output):
    prediction=json.loads(prediction_path.read_text())
    labels=json.loads(labels_path.read_text())
    grouped=defaultdict(list)
    for r in prediction["predictions"]:
        grouped[r["split"]].append(r)
    assert set(labels)=={r["key"] for r in prediction["predictions"]}
    def rows(split,method):
        return [Row(r["key"],date.fromisoformat(r["issued"]),date.fromisoformat(r["target_date"]),r[method],labels[r["key"]])
                for r in grouped[split]]
    # Calibrate only with training labels, then choose on validation.
    candidates=[{"method":"half","a":0,"b":0}]
    for method in ("direct","structured"):
        t=rows("train",method)
        best=min((score(t,[transform(r.p,a,b) for r in t])["brier"]+.01*(a*a+(b-1)**2),a,b)
                 for a in (-.5,0,.5) for b in (.5,1,1.5))
        candidates += [{"method":method,"a":0,"b":1,"calibrated":False},
                       {"method":method,"a":best[1],"b":best[2],"calibrated":True}]
    def predictions(split,c):
        if c["method"]=="half": return [.5]*len(grouped[split])
        p=[r[c["method"]] for r in grouped[split]]
        return [transform(x,c["a"],c["b"]) for x in p] if c["calibrated"] else p
    val=rows("validation","direct")
    val_scores=[score(val,predictions("validation",c))["brier"] for c in candidates]
    best=min(range(len(candidates)),key=lambda i:(val_scores[i],i))
    selected=best if val_scores[0]-val_scores[best]>=.005 else 0
    # Parameters frozen before any test scores.
    test=rows("test","direct")
    test_p=predictions("test",candidates[selected])
    # Raw direct and structured results are descriptive comparisons, never
    # used for selection. Report all predeclared candidates.
    report={"model":prediction["model"],"revision":prediction["revision"],
            "input_sha256":prediction["input_sha256"],"frozen_prediction_sha256":sha256(prediction_path),
            "counts":{k:len(v) for k,v in grouped.items()},
            "validation":[dict(c,brier=s) for c,s in zip(candidates,val_scores)],
            "selected":candidates[selected],"selected_test":score(test,test_p),
            "test_half":score(test,[.5]*len(test)),
            "raw_direct":score(test,predictions("test",candidates[1])),
            "raw_structured":score(test,predictions("test",candidates[3]))}
    output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("prepare");a.add_argument("archive",type=Path);a.add_argument("outdir",type=Path)
    a=sub.add_parser("infer");a.add_argument("inputs",type=Path);a.add_argument("output",type=Path)
    a=sub.add_parser("score");a.add_argument("prediction",type=Path);a.add_argument("labels",type=Path);a.add_argument("output",type=Path)
    a=p.parse_args()
    if a.cmd=="prepare": prepare(a.archive,a.outdir)
    elif a.cmd=="infer": infer(a.inputs,a.output)
    else: evaluate(a.prediction,a.labels,a.output)
