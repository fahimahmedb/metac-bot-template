"""Exact synthetic null stress for G3's forecast-week bootstrap assumption.
No real forecasts or outcomes. Conditional on a deliberately extreme null:
ten equal-sized, internally perfectly dependent observations per week; symmetric
binary labels, candidate .6 and primary .4, true expected Brier/log-loss gain zero.
Across weeks, labels follow a stationary two-state Markov chain. The binomial
percentile is the exact infinite-resample analogue, not the finite seeded CI.
"""
import json,math,sys
from collections import defaultdict
from fractions import Fraction as F
from pathlib import Path
import g3_paired_gate as gate
def require(ok,msg):
    if not ok:raise ValueError(msg)
def lower_bootstrap_count(n,k):
    p=F(k,n);acc=F(0)
    for j in range(n+1):
        acc+=math.comb(n,j)*p**j*(1-p)**(n-j)
        if acc>=F(1,40):return j
    raise AssertionError("cdf")
def passes_exact(n,k):
    return F(1,5)*(2*F(k,n)-1)>=F(str(gate.MIN_GAIN)) and 2*lower_bootstrap_count(n,k)>n
def min_k(n):
    return next(k for k in range(n+1) if passes_exact(n,k))
def count_distribution(n,stay):
    require(type(n) is int and n>=1 and 0<=stay<=1,"scenario")
    d={(0,0):F(1,2),(1,1):F(1,2)}
    for _ in range(n-1):
        e=defaultdict(F)
        for (last,k),p in d.items():
            for y in (0,1):e[y,k+y]+=p*(stay if y==last else 1-stay)
        d=e
    require(sum(d.values())==1,"probability conservation")
    return d
def false_pass(n,stay):
    d=count_distribution(n,stay)
    return sum(p for (_,k),p in d.items() if passes_exact(n,k))
def gate_smoke(k):
    m,f,y,t=gate.synthetic(100)
    # Exactly ten synthetic equal-sized forecast-week groups.
    for i,(a,b) in enumerate(zip(f,y,strict=True)):
        label=int(i%10<k)
        b["value"]=label
        a["members"]={"nemotron":.4,"gpt_oss":.6,"ernie":.7}
        a["aggregate"]=.6
    r=gate.evaluate(m,f,y,t)
    require(r["paired"]==100 and r["forecast_weeks"]==10,"gate smoke fixture")
    return {"positive_weeks":k,"actual_gate_status":r["status"],"actual_seeded_ci95":r["grouped_ci95"],"paired_brier_gain":r["paired_brier_gain"],"exact_bootstrap_analogue_pass":passes_exact(10,k)}
def main():
    require(gate.MIN_N==100 and gate.MIN_BLOCKS==10 and gate.MIN_GAIN==.01,"gate protocol changed")
    require(min_k(10)==9 and min_k(20)==15 and min_k(40)==27,"exact thresholds")
    for n in (10,20,40):
        d=count_distribution(n,F(1,2))
        require(all(sum(v for (_,j),v in d.items() if j==k)==F(math.comb(n,k),2**n) for k in range(n+1)),"iid reduction")
        for s in (F(1,2),F(4,5),F(19,20)):
            d=count_distribution(n,s)
            require(sum(F(k)*v for (_,k),v in d.items())==F(n,2),"zero population gain")
    require(false_pass(10,F(1,2))==F(11,1024),"iid exact probability")
    require(false_pass(10,F(4,5))>false_pass(10,F(1,2)),"persistence stress")
    smoke=[gate_smoke(k) for k in (8,9,10)]
    require(smoke[-1]["actual_gate_status"]=="PASS_STATISTICAL_ONLY","actual positive path")
    result={"scope":"SYNTHETIC_NULL_ASSUMPTION_STRESS_ONLY","true_expected_brier_gain":0,"true_expected_log_loss_gain":0,"independent_empirical_false_positive_rate":"UNKNOWN","finite_seeded_gate_smoke":smoke,"scenarios":[{"weeks":n,"events_per_week":10,"minimum_positive_weeks_exact_analogue":min_k(n),"probability_false_pass_exact_analogue":{str(float(s)):float(false_pass(n,s)) for s in (F(1,2),F(4,5),F(19,20))}} for n in (10,20,40)],"decision":"Require prospectively justified temporal-dependence and effective-cluster design before confirmatory freeze; keep current gate unchanged as software comparator only.","real_outcomes":0,"inference_calls":0,"promotion_authorized":False}
    Path("g3-temporal-dependence-report.json").write_text(json.dumps(result,sort_keys=True))
    print("G3_TEMPORAL_STRESS="+json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
