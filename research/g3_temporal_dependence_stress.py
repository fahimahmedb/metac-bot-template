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
def conditional_counts(n):
    """Counts by successes and switches, uniform paths conditional on switches
    under the stationary symmetric two-state Markov null."""
    d={(0,0,0):1,(1,1,0):1}
    for _ in range(n-1):
        e=defaultdict(int)
        for (last,k,m),w in d.items():
            for y in (0,1):e[y,k+y,m+int(y!=last)]+=w
        d=e
    counts=defaultdict(int)
    for (_,k,m),w in d.items():counts[m,k]+=w
    require(sum(counts.values())==2**n,"path count")
    for m in range(n):
        require(sum(counts[m,k] for k in range(n+1))==2*math.comb(n-1,m),"conditional count")
    return counts
def conditional_rejections(n):
    c=conditional_counts(n);rejections=set()
    for m in range(n):
        total=2*math.comb(n-1,m)
        tail=0
        for k in range(n,-1,-1):
            tail+=c[m,k]
            if c[m,k] and 40*tail<=total and F(1,5)*(2*F(k,n)-1)>=F(str(gate.MIN_GAIN)):
                rejections.add((m,k))
        require(40*sum(c[m,k] for k in range(n+1) if (m,k) in rejections)<=total,"conditional size")
    require((0,n) not in rejections,"constant favorable path admitted")
    return rejections
def alternative_probability(n,pi,rho,rejections):
    # Stationary binary Markov alternative; gain=.2*(2*pi-1).
    require(0<pi<1 and 0<=rho<1,"alternative")
    p01=(1-rho)*pi;p10=(1-rho)*(1-pi)
    d={(0,0,0):1-pi,(1,1,0):pi}
    for _ in range(n-1):
        e=defaultdict(float)
        for (last,k,m),w in d.items():
            p=p01 if last==0 else 1-p10
            e[0,k,m+int(last!=0)]+=w*(1-p)
            e[1,k+1,m+int(last!=1)]+=w*p
        d=e
    require(abs(sum(d.values())-1)<1e-10,"alternative mass")
    return sum(w for (_,k,m),w in d.items() if (m,k) in rejections)
def conditional_design():
    # A diagnostic under one explicit null, NOT a generic valid test for
    # arbitrary dependent Brier gains or evidence of real Markov behavior.
    scenarios=[]
    for n in (10,20,40,80):
        r=conditional_rejections(n)
        null={str(rho):alternative_probability(n,.5,rho,r) for rho in (0.,.6,.9,.99)}
        require(max(null.values())<=.025+1e-12,"null size")
        alt={str(pi):{str(rho):alternative_probability(n,pi,rho,r) for rho in (0.,.6,.9)} for pi in (.65,.75)}
        scenarios.append({"weeks":n,"null_false_pass":null,"power":alt})
    return {"scope":"conditional exact sign-count diagnostic under stationary symmetric binary Markov null only","alpha_one_sided":.025,"size_bound_proved_per_switch_count":True,"constant_positive_path_rejected_as_evidence":True,"scenarios":scenarios,"decision":"Do not promote this as a general Brier-gain test; reject nominal iid-week inference under strong dependence; assess power and justify assumptions before freezing a real portfolio.","real_outcomes":0,"inference_calls":0,"promotion_authorized":False}
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
    result["conditional_design"]=conditional_design()
    print("G3_CONDITIONAL_DESIGN="+json.dumps(result["conditional_design"],sort_keys=True))
    Path("g3-temporal-dependence-report.json").write_text(json.dumps(result,sort_keys=True))
    print("G3_TEMPORAL_STRESS="+json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
