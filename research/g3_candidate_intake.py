"""G3 candidate intake, not an admissible forecast or resolved-event cohort.
Official ForecastBench snapshot (CC BY-SA 4.0); no market forecasts read or exported.
Only source identity and future target dates are retained; event definitions and
point-in-time public source rights must still pass individual review.
"""
import hashlib,json,urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

REF="678d514ecd1cede1c0cfd009dc83be7e4fdf0940"
BLOB="ba26f714ff798f3c22865c6994a579449aaf0473"
NAME="2026-11-22-llm.json"
URL=f"https://raw.githubusercontent.com/forecastingresearch/forecastbench-datasets/{REF}/datasets/question_sets/{NAME}"
CUTOFF=date(2026,11,26)
MIN_TARGET=date(2026,12,3)
ALLOWED={"fred","dbnomics"}
EXCLUDED={"UNRATE","DGS10","DEXUSEU","WPSFD4","CPIAUCSL","LNS14000000","CUUR0000SA0"}

def require(ok,msg):
    if not ok:raise ValueError(msg)

def intake(doc):
    require(doc.get("question_set")==NAME and doc.get("forecast_due_date")=="2026-11-22","snapshot identity")
    rows=doc["questions"]
    require(isinstance(rows,list) and len(rows)>0,"no questions")
    counts=Counter()
    candidates={}
    for item in rows:
        source=item.get("source")
        if source not in ALLOWED:
            counts["excluded_non_allowed_source"]+=1
            continue
        counts["allowed_source_rows"]+=1
        ident=item.get("id")
        if not isinstance(ident,str) or not ident or len(ident)>200 or ident.upper() in EXCLUDED:
            counts["excluded_identity"]+=1;continue
        targets=item.get("resolution_dates")
        if not isinstance(targets,list):
            counts["excluded_no_date_list"]+=1;continue
        valid=[]
        for val in targets:
            try:
                if not isinstance(val,str) or len(val)!=10:continue
                d=date.fromisoformat(val)
                if MIN_TARGET<=d:valid.append(d.isoformat())
            except ValueError:continue
        if not valid:
            counts["excluded_no_future_target"]+=1;continue
        key=(source,ident)
        target=min(valid)
        if key not in candidates or target<candidates[key]["target"]:
            candidates[key]={"source":source,"source_id":ident,"target":target}
    ranked=sorted(candidates.values(),key=lambda r:(r["source"],hashlib.sha256((r["source"]+"|"+r["source_id"]+"|"+r["target"]).encode()).hexdigest()))
    # Deterministic alternating sources, no probability, outcome, question text or freeze value.
    selected=[]; groups={s:[r for r in ranked if r["source"]==s] for s in sorted(ALLOWED)}
    while len(selected)<8 and any(groups.values()):
        for group in groups.values():
            if group and len(selected)<8:selected.append(group.pop(0))
    require(len({(r["source"],r["source_id"]) for r in selected})==len(selected),"duplicate series")
    return {"cutoff":str(CUTOFF),"min_target":str(MIN_TARGET),"source_ref":REF,"source_blob":BLOB,"source_url":URL,"license":"CC BY-SA 4.0, Forecasting Research Institute ForecastBench datasets","counts":dict(counts),"eligible_date_candidates":len(candidates),"eligible_by_source":dict(Counter(r["source"] for r in ranked)),"review_candidates":selected,"scientific_status":"candidate intake only; individual resolution and evidence review required; not matched ForecastBench evaluation time","inference_calls":0,"outcomes_scored":0,"published":0}

def tests():
    base={"question_set":NAME,"forecast_due_date":"2026-11-22","questions":[{"source":"fred","id":"X","resolution_dates":["2026-11-26","2026-12-20","2026-12-10"],"freeze_datetime_value":999,"forecast":0.9},{"source":"fred","id":"X","resolution_dates":["2026-12-04"],"resolved_to":1},{"source":"polymarket","id":"Y","resolution_dates":["2027-01-01"],"forecast":0.9},{"source":"fred","id":"DGS10","resolution_dates":["2027-01-01"]},{"source":"dbnomics","id":"Z","resolution_dates":["2026-11-25","bad"]}]}
    result=intake(base)
    require(result["review_candidates"]==[{"source":"fred","source_id":"X","target":"2026-12-04"}],"selection")
    require(not any(k in json.dumps(result) for k in ("freeze_datetime_value","resolved_to","0.9")),"forbidden fields")
    print("G3_INTAKE_TESTS_PASS")

if __name__=="__main__":
    tests()
    with urllib.request.urlopen(URL,timeout=45) as r:raw=r.read(5_000_001)
    require(len(raw)<=5_000_000,"oversize")
    require(hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()==BLOB,"pinned git blob mismatch")
    result=intake(json.loads(raw));result["source_sha256"]=hashlib.sha256(raw).hexdigest()
    Path("g3-intake.json").write_text(json.dumps(result,indent=2,sort_keys=True))
    print("G3_INTAKE_RESULT="+json.dumps(result,sort_keys=True))
