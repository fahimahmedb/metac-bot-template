"""Local normalized ranked probability score for the two F3 numeric fixtures.
Not Metaculus peer or official continuous log score. No outcome retrieval.

F308 integer counts: half-integer thresholds plus inclusive upper bound.
F310 yield: 201 linear thresholds, half-open local bins and inclusive upper.
Metaculus API documents strict lower tail and inclusive upper endpoint:
https://www.metaculus.com/api/ . The local interior convention is explicit.
"""
import hashlib,json,math,statistics,sys
from decimal import Decimal
from pathlib import Path

def require(ok,msg):
    if not ok:raise ValueError(msg)
def numeric(x):
    return type(x) in (float,int) and math.isfinite(x)
def cdf_check(cdf,case):
    require(isinstance(cdf,list) and len(cdf)==201 and all(numeric(p) and 0<=p<=1 for p in cdf),"CDF shape/range")
    require(all(a<=b for a,b in zip(cdf,cdf[1:])),"nonmonotone CDF")
    require(case in ("F308","F310"),"unsupported fixture")
    if case=="F308":require(abs(cdf[0])<=1e-12,"closed lower bound")
def ref_to_cdf(p,case):
    require(isinstance(p,list) and len(p)==202 and all(numeric(x) and 0<=x<=1 for x in p) and abs(sum(p)-1)<=1e-10,"reference probability mass")
    cdf=[math.fsum(p[:i+1]) for i in range(201)]
    cdf=[min(1.,max(0.,v)) for v in cdf]
    cdf_check(cdf,case)
    return cdf
def score(cdf,y,case):
    cdf_check(cdf,case)
    require(numeric(y),"invalid outcome")
    y=Decimal(str(y))
    if case=="F308":
        require(y>=0 and y==y.to_integral_value(),"noninteger or below closed count bound")
        # A mass concentrated at an integer is scored as a count, not as
        # the arbitrary 0.25-wide grid cell adjacent to that integer.
        pairs=[(cdf[4*k+2],int(y<Decimal(k)+Decimal(".5"))) for k in range(50)]
        pairs.append((cdf[-1],int(y<=50)))
    else:
        thresholds=[Decimal(-2)+Decimal(17)*i/Decimal(200) for i in range(201)]
        pairs=[(p,int(y<t if i<200 else y<=t)) for i,(p,t) in enumerate(zip(cdf,thresholds,strict=True))]
    return statistics.mean((p-label)**2 for p,label in pairs)
def tests():
    # Integer mass at 10 on either side of the integer's grid point.
    # Both representations must have the same count-level score.
    a=[float(i>=40) for i in range(201)];b=[float(i>=41) for i in range(201)]
    require(score(a,10,"F308")==score(b,10,"F308")==0,"integer adjacent-bin ambiguity")
    require(score(a,11,"F308")>0,"wrong integer unpenalized")
    require(score([0.]*200+[1.],50,"F308")==0,"upper equality counted outside")
    require(score([0.]*201,51,"F308")==0,"upper tail")
    require(score([0.]*201,50,"F308")>0,"upper endpoint distinction")
    require(score([0.]+[1.]*200,0,"F308")==0,"closed lower equality")
    require(score([0.]*200+[1.],15,"F310")==0,"continuous upper equality")
    require(score([0.]*201,16,"F310")==0,"continuous upper tail")
    require(score([1.]*201,-3,"F310")==0,"continuous lower tail")
    require(score([0.]+[1.]*200,-2,"F310")==0,"continuous lower equality")
    for case,cdf,y in (("F308",[0.]*201,-1),("F308",[0.]*201,1.5),("F308",[.1]*201,1),("F310",[.5]*200+[.4],1),("F310",[0.]*201,True)):
        try:score(cdf,y,case)
        except ValueError:pass
        else:raise AssertionError("invalid input accepted")
    print("LOCAL_NUMERIC_SCORE_TESTS_PASS=15 synthetic_only=true")
def main(case,path,expected):
    tests()
    raw=Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==expected,"frozen reference mismatch")
    d=json.loads(raw);require(d["case"]==case and d["outcomes_scored"]==0,"reference identity")
    cdf=ref_to_cdf(d["reference"][d["primary"]],case)
    # This is ONLY a numerical shape/edge smoke test on synthetic labels,
    # not a score of the future event or a comparison of actual forecasts.
    examples=(0,1,10,50,51) if case=="F308" else (-3,-2,4,15,16)
    require(all(0<=score(cdf,y,case)<=1 for y in examples),"invalid score")
    print("LOCAL_NUMERIC_REFERENCE_READY="+json.dumps({"case":case,"reference_sha256":expected,"thresholds":51 if case=="F308" else 201,"synthetic_labels":len(examples),"actual_outcomes_scored":0,"official_score":False,"inference_calls":0},sort_keys=True))
if __name__=="__main__":main(*sys.argv[1:])
