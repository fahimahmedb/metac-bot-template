"""Independent arithmetic audit of the recorded G2 numeric distributions.
Scoped to the two predeclared local linear 201-point fixtures, not a generic
replacement for No-Stream's numeric engine. No network, secrets or inference.
"""
import json, math, statistics, sys
from pathlib import Path

PIN = "79c1d7a1192a00724646ab05c67f3b776d2d7b65"
SNAPSHOTS = {
    "D03": "c69d9bba0dd7f22761d0788188926368935ab79f0b993202ed7020cbe1f16804",
    "D04": "319a2d90575a77643283824c379ac386053aef350eaa5f64641dee5deaa935f5",
}
ROLES = {
    "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
    "openrouter/openai/gpt-oss-120b",
    "openrouter/google/gemma-4-26b-a4b-it:free",
}
TOL = 1e-9
MIN_STEP = 0.00005
MAX_STEP = 0.2

def check(ok, reason):
    if not ok:
        raise ValueError(reason)

def legal(cdf, case):
    check(len(cdf) == 201 and all(type(x) in (float, int) and math.isfinite(x) and 0 <= x <= 1 for x in cdf), "invalid CDF")
    check(all(MIN_STEP-TOL <= b-a <= MAX_STEP+TOL for a,b in zip(cdf,cdf[1:])), "step violation")
    check(abs(cdf[0]) <= TOL if case == "D03" else cdf[0] >= .01-TOL, "lower bound")
    check(cdf[-1] <= .99+TOL, "upper tail")

def independent_expected(members, case):
    for c in members:
        legal(c, case)
    med = [statistics.median(col) for col in zip(*members, strict=True)]
    legal(med, case)
    if case == "D04":
        # Continuous fixture: median is already platform-legal; no snap.
        return med
    # Integer count fixture: derive masses on half-integer intervals of its
    # 0..50 linear grid, preserve tails, then mix a uniform floor.
    def at(x):
        pos = x*4
        i = min(199, max(0, math.floor(pos)))
        return med[i] + (med[i+1]-med[i])*(pos-i)
    masses = [max(0,at(min(50,k+.5))-at(max(0,k-.5))) for k in range(51)]
    check(sum(masses)>0, "no interior mass")
    masses = [m*(med[-1]-med[0])/sum(masses) for m in masses]
    step = [med[0]+sum(masses[:i//4+1]) for i in range(201)]
    step[0],step[-1] = med[0],med[-1]
    alpha = min(1,MIN_STEP*201/(med[-1]-med[0])*1.1)
    result = [(1-alpha)*x + alpha*(med[0]+(med[-1]-med[0])*i/200) for i,x in enumerate(step)]
    # This audit only admits the observed no-max-step-clipping branch.
    check(max(b-a for a,b in zip(result,result[1:])) <= MAX_STEP+TOL, "unqualified max-step branch")
    for i in range(1,201):
        result[i]=min(.99,max(result[i],result[i-1]+MIN_STEP))
    for i in range(199,-1,-1):
        result[i]=max(0,min(result[i],result[i+1]-MIN_STEP))
    legal(result,case)
    return result

def audit(doc, case):
    check(case in SNAPSHOTS and doc["case_id"] == case, "case mismatch")
    check(doc["snapshot_sha256"] == SNAPSHOTS[case] and doc["source_sha"] == PIN, "provenance mismatch")
    check(doc["technical_pipeline_pass"] is True and doc["aggregation_verified"] is True and doc["published"] == 0 and doc["degradation"] == 0, "invalid receipt")
    check(set(doc["members"]) == ROLES, "role mismatch")
    actual=doc["report"]
    legal(actual,case)
    expected=independent_expected(list(doc["members"].values()),case)
    error=max(abs(x-y) for x,y in zip(expected,actual,strict=True))
    check(error<=TOL, "numeric reconstruction mismatch")
    return {"case":case,"points":201,"max_abs_error":error,"numeric_independent_recomputation":True,"scope":"recorded fixture only"}

if __name__ == "__main__":
    doc=json.loads(Path(sys.argv[1]).read_text())
    case=sys.argv[2]
    result=audit(doc,case)
    # Adversary: change the report while retaining its identity and PASS flags.
    bad=json.loads(json.dumps(doc))
    bad["report"]=[x+.0001 if 20<i<180 else x for i,x in enumerate(bad["report"])]
    try:
        audit(bad,case)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered report admitted")
    print("NUMERIC_RECOMPUTATION="+json.dumps(result,sort_keys=True))
    print("TAMPER_REJECTION_PASS")
