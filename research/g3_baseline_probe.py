"""Zero-inference statistical reference probe on frozen G2 evidence.

Exploratory on G2 (chosen after model forecasts); prospective rules for a
future distinct cohort must be frozen before generating its forecasts.
Internal bin scores are not official Metaculus continuous or peer scores.
"""
import bisect
import hashlib
import json
import math
import sys
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import g2_diverse_evidence as evidence
from historical_calibration import Row, score
from datetime import date

VERSION="empirical-reference-v1"
def require(ok, why):
    if not ok:
        raise ValueError(why)

def month_number(s):
    y,m=map(int,s[:7].split("-"))
    require(1<=m<=12,"invalid month")
    return 12*y+m

def historical_outcomes(case, rows):
    case_id=case["id"]
    if case_id=="D02":
        # No bridging missing months. Published headline changes are rounded
        # to 0.1%; index-derived changes are proxies for first-release labels.
        return [
            (b[0],float(((Decimal(str(b[1]))/Decimal(str(a[1]))-1)*100).quantize(Decimal(".1"),rounding=ROUND_HALF_UP)))
            for a,b in zip(rows,rows[1:]) if month_number(b[0])==month_number(a[0])+1
        ]
    if case_id in ("D04","D06"):
        by_month={}
        for d,v in rows:
            if d[:7]<evidence.CUTOFF[:7]:
                by_month[d[:7]]=v
        return sorted(by_month.items())
    return rows

def categorical_index(case, value):
    case_id=case["id"]
    if case_id=="D01":return int(value>=4.5)
    if case_id=="D06":return int(value>=1.15)
    if case_id=="D02":return 0 if value<0 else 1 if value<.5 else 2
    if case_id=="D05":return 0 if value<80 else 1 if value<140 else 2
    raise ValueError("not categorical")

def grid(case):
    return [case["lower"]+(case["upper"]-case["lower"])*i/200 for i in range(201)]

def bin_index(case,y):
    # For our local scoring: bins below first edge, [edge_i,edge_i+1),
    # and at/above the last edge. Closed-bound violations are not outcomes.
    require(type(y) in (int,float) and math.isfinite(y),"invalid outcome")
    require(case["open_lower"] or y>=case["lower"],"below closed bound")
    require(case["open_upper"] or y<=case["upper"],"above closed bound")
    if not case["open_upper"] and y==case["upper"]:return 200
    return bisect.bisect_right(grid(case),y)

def normalize(counts, prior):
    total=sum(counts)+sum(prior)
    require(total>0,"empty reference")
    return [(c+p)/total for c,p in zip(counts,prior,strict=True)]

def make_reference(case, rows):
    values=historical_outcomes(case,rows)
    require(len(values)>=4,"insufficient historical observations")
    if case["type"]=="numeric":
        k=202
        allowed=[i for i in range(k) if (i!=0 or case["open_lower"]) and (i!=201 or case["open_upper"])]
        counts=Counter(bin_index(case,v) for _,v in values)
        prior=[1/len(allowed) if i in allowed else 0 for i in range(k)]
        empirical=normalize([counts[i] for i in range(k)],prior)
        uniform=prior
    else:
        k=2 if case["type"]=="binary" else len(case["options"])
        counts=Counter(categorical_index(case,v) for _,v in values)
        empirical=normalize([counts[i] for i in range(k)],[1.]*k)
        uniform=[1/k]*k
    require(all(abs(sum(p)-1)<1e-12 and all(math.isfinite(x) and x>=0 for x in p) for p in (empirical,uniform)),"invalid probabilities")
    return {"algorithm":VERSION,"case":case["id"],"type":case["type"],"historical_n":len(values),
            "first_period":values[0][0],"last_period":values[-1][0],"empirical":empirical,"uniform":uniform,
            "scope":"exploratory G2 reference; not a prospective performance result",
            "vintage_limitation":"historical values may be revised; monthly index changes proxy first-release labels",
            "score_scope":"local categorical or grid-bin proper scores, not official continuous/peer scoring"}

def local_score(p,outcome,kind):
    require(len(p)>1 and all(type(x) in (float,int) and math.isfinite(x) and 0<=x<=1 for x in p) and abs(sum(p)-1)<1e-9,"invalid probability vector")
    require(type(outcome) is int and 0<=outcome<len(p),"invalid outcome index")
    logloss=-math.log(p[outcome]) if p[outcome]>0 else math.inf
    if kind=="binary":
        require(len(p)==2,"binary dimension")
        d=date(2026,1,1)
        # Reuse existing binary Brier implementation; log loss here is
        # explicitly unclipped, unlike historical_calibration's capped log.
        return {"brier":score([Row("fixture",d,d,p[1],outcome)],[p[1]])["brier"],"log_loss":logloss}
    if kind=="multiple_choice":
        return {"brier_multiclass":sum((x-int(i==outcome))**2 for i,x in enumerate(p)),"log_loss":logloss}
    if kind=="numeric":
        cumulative=0.; loss=0.
        for i,x in enumerate(p[:-1]):
            cumulative+=x
            loss+=(cumulative-int(outcome<=i))**2
        return {"rps_normalized":loss/(len(p)-1),"bin_log_loss":logloss}
    raise ValueError("unknown score type")

def self_test():
    require(local_score([.5,.5],1,"binary")["brier"]==.25,"binary Brier")
    require(abs(local_score([1/3]*3,1,"multiple_choice")["log_loss"]-math.log(3))<1e-12,"MC log")
    require(local_score([0,1,0],1,"numeric")["rps_normalized"]==0,"numeric perfect")
    require(local_score([1,0,0],2,"numeric")["rps_normalized"]==1,"numeric worst")
    require(math.isinf(local_score([1,0],1,"binary")["log_loss"]),"zero outcome mass")
    for p,y,k in (([.4,.4],0,"binary"),([True,0],0,"binary"),([.5,.5],2,"binary")):
        try:local_score(p,y,k)
        except ValueError:pass
        else:raise AssertionError("bad scoring input admitted")
    case=evidence.load_case("D02")
    require(historical_outcomes(case,[["2026-01",100],["2026-03",110]])==[],"missing month bridged")
    print("LOCAL_SCORE_TESTS_PASS 9")

def main():
    path,case_id,expected_sha=Path(sys.argv[1]),sys.argv[2],sys.argv[3]
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==expected_sha,"snapshot mismatch")
    doc=json.loads(raw)
    case=evidence.load_case(case_id)
    require(doc["case"]==case and doc["observation_cutoff"]==evidence.CUTOFF,"case mismatch")
    rows=doc["observations"]
    require(rows==sorted(rows) and len({r[0] for r in rows})==len(rows),"unordered or duplicate observations")
    require(all(r[0]<=evidence.CUTOFF and type(r[1]) in (int,float) and math.isfinite(r[1]) for r in rows),"bad observation")
    self_test()
    ref=make_reference(case,rows)
    ref.update(snapshot_sha256=expected_sha,inference_calls=0,resolved_events_scored=0)
    Path("baseline-receipt.json").write_text(json.dumps(ref,sort_keys=True))
    print("G3_REFERENCE="+json.dumps({k:v for k,v in ref.items() if k not in ("empirical","uniform")},sort_keys=True))
    if case["type"]!="numeric":print("REFERENCE_PROBABILITIES="+json.dumps(ref["empirical"]))

if __name__=="__main__":main()
