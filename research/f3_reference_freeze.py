"""Freeze statistical development comparators before the six F3 forecasts.
Uses the exact registered fixture and existing reference logic. No outcomes,
provider requests, publication, or confirmatory G3 admission.
"""
import hashlib,json,math,os
from datetime import datetime,timezone
from pathlib import Path
import nostream_free_f3 as f3
from g3_baseline_probe import make_reference

def require(ok,msg):
    if not ok:raise ValueError(msg)
def main():
    now=datetime.now(timezone.utc)
    require(now.date().isoformat()=="2026-11-26","reference must precede live window")
    case,q,_,snapshot=f3.input_fixture()
    require(case["id"] in ("F304","F310","F306","F307","F308","F309"),"unregistered fixture")
    require(q.id_of_question==case["qid"] and q.question_text==case["question"],"question identity")
    raw=Path("diverse-input/snapshot.json").read_bytes()
    require(hashlib.sha256(raw).hexdigest()==snapshot,"evidence identity")
    doc=json.loads(raw)
    original=doc["case"]
    reference=make_reference(original,doc["observations"])
    # F310 has only two full months. Its daily-level distribution is a
    # descriptive proxy; uniform is the primary comparator for this fixture.
    primary="uniform" if case["id"]=="F310" else "empirical"
    require(all(abs(sum(reference[k])-1)<1e-12 and all(math.isfinite(p) and p>=0 for p in reference[k]) for k in ("uniform","empirical")),"invalid reference")
    definition=json.dumps(case,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    result={"case":case["id"],"qid":case["qid"],"definition":case,"definition_sha256":hashlib.sha256(definition).hexdigest(),"snapshot_sha256":snapshot,"frozen_at":now.isoformat(),"primary":primary,"reference":reference,"empirical_scope":"daily-level descriptive proxy, not monthly-end distribution" if case["id"]=="F310" else "historical frequency under existing source-specific transformation","scoring_scope":"local scores only; numeric bin/CDF convention needs qualification before scoring","inference_calls":0,"outcomes_scored":0,"promotion_authorized":False,"scientific_status":"development comparator only, not confirmatory G3"}
    Path("f3-reference.json").write_text(json.dumps(result,sort_keys=True))
    print("F3_REFERENCE_FROZEN="+json.dumps({k:v for k,v in result.items() if k not in ("definition","reference")}|{"historical_n":reference["historical_n"],"probabilities":reference[primary] if case["type"]!="numeric" else None},sort_keys=True))
if __name__=="__main__":main()
