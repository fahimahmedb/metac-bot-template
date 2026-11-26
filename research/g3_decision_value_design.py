"""Synthetic engineering qualification of the next economic decision seam.

No real market prices, returns, forecasts, orders, fees or capital. The
hypothesis is that improved forecast accuracy need not improve decision value.
Only a fixed binary two-action payoff abstraction is qualified here.
A later admitted economic experiment must separately identify real payoffs,
costs, benchmark, market information time, risk, tax and capacity.
"""
import hashlib,json,sys
from fractions import Fraction as F
from pathlib import Path
def require(ok,msg):
    if not ok:raise ValueError(msg)
def number(x):
    require(type(x) is str and len(x)<=64,"decimal/rational text required")
    try:return F(x)
    except (ValueError,ZeroDivisionError):raise ValueError("invalid rational")
def prob(x):
    v=number(x);require(0<=v<=1,"probability");return v
def canonical(x):return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha(x):return hashlib.sha256(canonical(x)).hexdigest()
def interval(x):
    require(isinstance(x,list) and len(x)==3,"interval low/point/high")
    lo,p,hi=map(prob,x);require(lo<=p<=hi,"interval ordering")
    return lo,p,hi
def payoffs(row):
    down,up,c=map(number,[row["return_no"],row["return_yes"],row["cost_upper"]])
    require(-1<=down<=up and up<=1 and 0<=c<=1,"payoff or cost bounds")
    return down,up,c
def expected(p,down,up,c):return down+p*(up-down)-c
def policy(row,arm):
    lo,p,hi=interval(row[arm]);down,up,c=payoffs(row)
    # Same long-or-abstain policy for both information sets.
    # Strict positivity at the conservative lower bound; ties abstain.
    edge=expected(lo,down,up,c)
    return int(edge>0),edge
def threshold(row):
    down,up,c=payoffs(row)
    if up==down:return None
    return (c-down)/(up-down)
def freeze(rows):
    require(isinstance(rows,list) and rows,"nonempty plan")
    ids=set()
    for r in rows:
        require(set(r)=={"id","candidate","reference","return_no","return_yes","cost_upper"},"frozen fields")
        require(isinstance(r["id"],str) and r["id"] and r["id"] not in ids,"duplicate identity")
        ids.add(r["id"])
        for a in ("candidate","reference"):policy(r,a)
    return {"scope":"SYNTHETIC_ENGINEERING_ONLY","policy":"ROBUST_LONG_OR_ABSTAIN_V1","rows":sorted(rows,key=lambda r:r["id"])}
def evaluate(plan,expected_sha,labels):
    require(sha(plan)==expected_sha and plan==freeze(plan["rows"]),"plan identity")
    require(isinstance(labels,list),"labels")
    ys={}
    for r in labels:
        require(set(r)=={"id","value"} and type(r["value"]) is int and r["value"] in (0,1) and r["id"] not in ys,"label identity")
        ys[r["id"]]=r["value"]
    require(set(ys)=={r["id"] for r in plan["rows"]},"same sample")
    scores={a:{"brier":F(0),"net":F(0),"trades":0} for a in ("candidate","reference")}
    comparisons=[]
    for r in plan["rows"]:
        y=ys[r["id"]];down,up,c=payoffs(r)
        result={"id":r["id"],"threshold":str(threshold(r)) if threshold(r) is not None else None}
        for a in scores:
            action,edge=policy(r,a);p=interval(r[a])[1]
            net=action*((up if y else down)-c)
            scores[a]["brier"]+=(p-y)**2
            scores[a]["net"]+=net;scores[a]["trades"]+=action
            result[a]={"action":action,"conservative_expected_net":str(edge),"synthetic_net":str(net)}
        comparisons.append(result)
    n=len(comparisons)
    bg=(scores["reference"]["brier"]-scores["candidate"]["brier"])/n
    ng=(scores["candidate"]["net"]-scores["reference"]["net"])/n
    return {"scope":"SYNTHETIC_ENGINEERING_ONLY","plan_sha256":expected_sha,"n":n,
      "arms":{a:{"mean_brier":str(s["brier"]/n),"mean_net":str(s["net"]/n),"actions":s["trades"]} for a,s in scores.items()},
      "paired_brier_gain":str(bg),"paired_net_gain":str(ng),"different_actions":sum(r["candidate"]["action"]!=r["reference"]["action"] for r in comparisons),
      "interpretation":"PREDICTIVE_GAIN_NOT_SUFFICIENT" if bg>0 and ng<=0 else "NO_ACTUAL_ECONOMIC_EVIDENCE",
      "real_economic_trials":0,"actual_market_data_used":False,"predictive_skill":"UNKNOWN","economic_value":"UNKNOWN","promotion_authorized":False,"details":comparisons}
def row(i,p,q,c="0.007",low=None,high=None):
    return {"id":str(i),"candidate":[low or p,p,high or p],"reference":[q,q,q],"return_no":"-0.01","return_yes":"0.01","cost_upper":c}
def trial(rows,ys):
    plan=freeze(rows);return evaluate(plan,sha(plan),[{"id":r["id"],"value":y} for r,y in zip(rows,ys,strict=True)])
def tests():
    def reject(fn):
        try:fn()
        except (ValueError,TypeError,KeyError,ArithmeticError):return
        raise AssertionError("invalid input admitted")
    r=row(0,"0.85","0.50")
    require(threshold(r)==F(85,100) and policy(r,"candidate")[0]==0,"strict breakeven")
    require(policy(row(0,"0.86","0.50"),"candidate")[0]==1,"positive robust edge")
    require(policy(row(0,"0.9","0.5",low="0.8",high="0.95"),"candidate")[0]==0,"uncertainty blocks action")
    neutral=trial([row(1,"0.8","0.6"),row(2,"0.2","0.4")],[1,0])
    require(F(neutral["paired_brier_gain"])==F(3,25) and F(neutral["paired_net_gain"])==0 and neutral["different_actions"]==0,"better forecast same decision")
    loss=trial([row(i,"0.8","0.6") for i in range(9)]+[row(9,"0.9","0.4")],[1]*9+[0])
    require(F(loss["paired_brier_gain"])==F(43,1000) and F(loss["paired_net_gain"])==F(-17,10000),"better forecast worse net")
    win=trial([row(0,"0.6","0.4",c="0.001")],[1])
    require(F(win["paired_net_gain"])==F(9,1000) and win["different_actions"]==1,"synthetic positive")
    require(trial([row(0,"0.9","0.9")],[1])["paired_net_gain"]=="0","identical signals")
    reject(lambda:freeze([row(0,"0.8","0.6"),row(0,"0.8","0.6")]))
    reject(lambda:freeze([row(0,"0.8","0.6",low="0.9")]))
    reject(lambda:freeze([row(0,"0.8","0.6",c="-0.001")]))
    reject(lambda:freeze([row(0,"0.8","0.6")|{"return_no":"0.02"}]))
    reject(lambda:freeze([row(0,"1.1","0.5")]))
    plan=freeze([row(0,"0.8","0.6")]);y=[{"id":"0","value":1}]
    reject(lambda:evaluate(plan,"0"*64,y))
    reject(lambda:evaluate(plan,sha(plan),[{"id":"0","value":True}]))
    reject(lambda:evaluate(plan,sha(plan),[]))
    require(evaluate(plan,sha(plan),y)["promotion_authorized"] is False,"no promotion")
    # Test monotonicity exactly for 101 probabilities x 5 cost assumptions.
    for i in range(101):
        p=str(F(i,100))
        actions=[policy(row(0,p,"0.5",c=str(F(c,1000))),"candidate")[0] for c in (0,1,5,10,20)]
        require(actions==sorted(actions,reverse=True),"cost monotonicity")
    return {"distinct_checks":17,"monotonicity_grid":505,"same_decision":neutral,"negative_net":loss,"positive_net":win,"real_economic_trials":0}
if __name__=="__main__":
    r=tests()
    Path("decision-design-report.json").write_text(json.dumps(r,sort_keys=True))
    print("G3_DECISION_DESIGN_PASS="+json.dumps({k:v for k,v in r.items() if k not in ("same_decision","negative_net","positive_net")}|{k:{a:b for a,b in r[k].items() if a!="details"} for k in ("same_decision","negative_net","positive_net")},sort_keys=True))
