"""Rolling-origin development benchmarks on three existing BLS snapshots.
Revised historical data, NOT vintage-correct historical inference or F3 skill.
Primary expanding Laplace baseline remains fixed; alternatives exploratory.
"""
import hashlib,json,math,sys,statistics
from pathlib import Path
from decimal import Decimal
from g3_bls_candidates import SPECS,month_num,outcomes

EXPECTED={
"cpi":"73d048ed85482a2c74ede4640ca65697204b8953e88f47850557416e97a73470",
"payroll":"64852544b10f345f907c7988834b149a097b37ce118214529f3b11920b7f4d1a",
"openings":"dca538e1d68879aa70bef3f747fe2a36d66437dcd1bfae5b3f30d5e36916839b"}
METHODS=("half","expanding","recent12","markov")
def require(ok,msg):
    if not ok:raise ValueError(msg)
def laplace(ys):return (sum(ys)+1)/(len(ys)+2)
def predict(history,previous):
    require(len(history)>=12 and all(type(y) is int and y in (0,1) for _,y in history),"history")
    pairs=[b[1] for a,b in zip(history,history[1:]) if b[0]==a[0]+1 and a[1]==previous]
    return {"half":.5,"expanding":laplace([y for _,y in history]),"recent12":laplace([y for _,y in history[-12:]]),"markov":laplace(pairs) if previous is not None else laplace([y for _,y in history])}
def event_rows(rows,spec):
    result=[]
    for a,b in zip(rows,rows[1:]):
        if month_num(b[0])!=month_num(a[0])+1:continue
        result.append((month_num(b[0]),outcomes([a,b],spec)[0]))
    return result
def evaluate(events):
    require(len(events)>=20 and all(a[0]<b[0] for a,b in zip(events,events[1:])),"insufficient/unsorted events")
    predictions=[]
    for i in range(12,len(events)):
        m,y=events[i]
        history=events[:i]
        previous=history[-1][1] if history[-1][0]==m-1 else None
        predictions.append({"month_index":m,"outcome":y,"probabilities":predict(history,previous),"history_n":i})
    reports={}
    for name in METHODS:
        p=[r["probabilities"][name] for r in predictions];y=[r["outcome"] for r in predictions]
        reports[name]={"brier":statistics.mean((a-b)**2 for a,b in zip(p,y,strict=True)),"log_loss":statistics.mean(-math.log(a if b else 1-a) for a,b in zip(p,y,strict=True))}
    return predictions,reports
def tests():
    e=[(i,i%2) for i in range(25)]
    p,r=evaluate(e);require(len(p)==13 and p[0]["history_n"]==12,"rolling size")
    p2,_=evaluate(e[:12]+[(12,1-e[12][1])]+e[13:])
    require(p[0]["probabilities"]==p2[0]["probabilities"],"current-label leakage")
    p3,_=evaluate(e[:-1]+[(24,1-e[-1][1])])
    require([x["probabilities"] for x in p]==[x["probabilities"] for x in p3],"future-label leakage")
    require(abs(r["half"]["brier"]-.25)<1e-12,"half baseline")
    require(event_rows([["2026-01","100"],["2026-03","103"]],SPECS["payroll"])==[],"gap bridged")
    require(predict([(i,0) for i in range(12)],None)["markov"]==1/14,"no predecessor")
    print("BLS_ROLLING_TESTS_PASS=6")
def main(key,path):
    tests()
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==EXPECTED[key],"snapshot identity")
    d=json.loads(raw);spec=SPECS[key]
    require(d["definition"]==spec and d["candidate"]==key and d["observation_cutoff"]=="2026-10","manifest identity")
    rows=d["rows"]
    require(rows==sorted(rows) and len({r[0] for r in rows})==len(rows) and all(r[0]<="2026-10" and Decimal(r[1]).is_finite() and Decimal(r[1])>0 for r in rows),"invalid rows")
    events=event_rows(rows,spec)
    require(len(events)==d["baseline"]["n"] and sum(y for _,y in events)==d["baseline"]["yes"],"baseline mismatch")
    require(abs(laplace([y for _,y in events])-d["baseline"]["probability"])<1e-12,"baseline mismatch")
    predictions,metrics=evaluate(events)
    r={"candidate":key,"snapshot_sha256":EXPECTED[key],"n":len(predictions),"metrics":metrics,"future_fixed_baseline":d["baseline"]["probability"],"decision":"KEEP_PREDECLARED_EXPANDING_BASELINE","scope":"rolling-origin on revised observations; not a vintage-correct forecast trial; not F3 performance","inference_calls":0,"f3_skill":"UNKNOWN","rows":predictions}
    Path("rolling-result.json").write_text(json.dumps(r,sort_keys=True))
    print("BLS_ROLLING_RESULT="+json.dumps({k:v for k,v in r.items() if k!="rows"},sort_keys=True))
if __name__=="__main__":main(sys.argv[1],Path(sys.argv[2]))
