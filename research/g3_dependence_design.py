"""Pre-outcome G3 dependence design: finite-dependence bound and exact Markov diagnostic.

Not an admission gate, not a change to the existing primary scoring policy.
The bound requires justified independent color classes; the diagnostic assumes
a stationary homogeneous symmetric two-state Markov sign process. Neither
assumption has been established for F3. No real outcomes or model calls.
"""
import itertools,json,math,statistics
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

RANGE=1.96
ALPHA=.025 # one-sided lower endpoint of existing 95% interval
def require(ok,msg):
    if not ok:raise ValueError(msg)

def lower_bound(groups,lag,alpha=ALPHA):
    """Weighted event mean, bounded by Hoeffding + Holder over lag+1 colors.
    Each color must be jointly independent, not merely pairwise uncorrelated.
    Fixed registered chronological weeks; missing weeks cannot be compressed.
    """
    require(type(lag) is int and lag>=0 and 0<alpha<1 and bool(groups),"design parameters")
    require(all(type(w) is int and bool(v) and all(type(x) in (float,int) and math.isfinite(x) and -.98<=x<=.98 for x in v) for w,v in groups.items()),"week/gain")
    total=sum(len(v) for v in groups.values())
    weights=[len(v)/total for v in groups.values()]
    colors=min(lag+1,len(groups))
    mean=sum(sum(v) for v in groups.values())/total
    effective=1/(colors*sum(w*w for w in weights))
    margin=RANGE*math.sqrt(math.log(1/alpha)/(2*effective))
    return {"event_weighted_gain":mean,"effective_week_bound":effective,"lower":max(-.98,mean-margin),"radius":margin,"assumption_verified":False}

def min_equal_weeks(gain,lag):
    require(0<gain<=.98 and type(lag) is int and lag>=0,"planning")
    # Strict positive lower bound under equal-sized independent color classes.
    return math.floor((lag+1)*RANGE**2*math.log(1/ALPHA)/(2*gain**2))+1

def markov_counts(n):
    """Counts of sign paths by switch count and number of favorable weeks."""
    require(type(n) is int and 1<=n<=150,"n")
    d={(0,0,0):1,(1,0,1):1}
    for _ in range(n-1):
        e=defaultdict(int)
        for (last,s,k),c in d.items():
            for y in (0,1):e[y,s+int(last!=y),k+y]+=c
        d=e
    out=defaultdict(int)
    for (_,s,k),v in d.items():out[s,k]+=v
    return out

def conditional_tail(n,s,k,counts=None):
    require(0<=s<n and 0<=k<=n,"sign counts")
    d=markov_counts(n) if counts is None else counts
    return Fraction(sum(v for (t,j),v in d.items() if t==s and j>=k),2*math.comb(n-1,s))

def exact_null(n,stay):
    d=markov_counts(n); reject=Fraction(0)
    for (s,k),v in d.items():
        if Fraction(1,5)*(2*Fraction(k,n)-1)>=Fraction(1,100) and conditional_tail(n,s,k,d)<=Fraction(1,40):
            reject+=Fraction(v,2)*stay**(n-1-s)*(1-stay)**s
    return reject

def tests():
    a=lower_bound({i:[.2]*10 for i in range(10)},0)
    b=lower_bound({i:[.2]*10 for i in range(10)},3)
    require(abs(a["effective_week_bound"]-10)<1e-12 and abs(b["effective_week_bound"]-2.5)<1e-12,"colors")
    require(b["lower"]<a["lower"]<0,"dependence sensitivity")
    require(lower_bound({0:[.2]*100,1:[.2]},0)["effective_week_bound"]<1.03,"imbalance")
    require(min_equal_weeks(.1,3)==4*min_equal_weeks(.1,0) or abs(min_equal_weeks(.1,3)-4*min_equal_weeks(.1,0))<=3,"planning")
    for n in range(1,9):
        d=markov_counts(n); brute=defaultdict(int)
        for seq in itertools.product((0,1),repeat=n):
            brute[sum(a!=b for a,b in zip(seq,seq[1:])),sum(seq)]+=1
        require(d==brute,"exact path enumeration")
    for n in (10,20,40):
        d=markov_counts(n)
        for s in range(n):
            require(sum(v for (t,k),v in d.items() if t==s)==2*math.comb(n-1,s),"conditional normalization")
            require(sum(Fraction(v,2*math.comb(n-1,s)) for (t,k),v in d.items() if t==s and conditional_tail(n,s,k,d)<=Fraction(1,40))<=Fraction(1,40),"conditional type I bound")
    require(conditional_tail(10,0,10)==Fraction(1,2),"all-positive persistent path")
    for bad in ({0:[1.]},{0:[True]},{}):
        try:lower_bound(bad,0)
        except ValueError:pass
        else:raise AssertionError("invalid gain accepted")
    print("G3_DEPENDENCE_DESIGN_TESTS_PASS")

def main():
    tests()
    rows=[]
    for n in (10,20,40):
        rows.append({"weeks":n,"null_false_pass_markov_sign_diagnostic":{str(float(p)):float(exact_null(n,p)) for p in (Fraction(1,2),Fraction(4,5),Fraction(19,20))},"all_favorable_no_switch_p":float(conditional_tail(n,0,n)),"bounded_lower_if_gain_0_2":{str(m):lower_bound({i:[.2]*10 for i in range(n)},m) for m in (0,1,3,9)}})
    plans=[{"observed_gain":g,"minimum_equal_weeks_for_positive_bound":{str(m):min_equal_weeks(g,m) for m in (0,1,3,9)}} for g in (.01,.05,.1,.2)]
    result={"status":"DESIGN_ONLY_BLOCK_ASSUMPTIONS_UNVERIFIED","scope":"synthetic diagnostics and conservative sufficient bound, not power guarantee or actual F3 skill","scenarios":rows,"planning":plans,"arbitrary_serial_dependence_guarantee":False,"markov_scope":"sign/count diagnostic only; not a general mean Brier gain test","existing_primary_gate_changed":False,"real_outcomes":0,"inference_calls":0,"promotion_authorized":False}
    Path("g3-dependence-design.json").write_text(json.dumps(result,sort_keys=True))
    print("G3_DEPENDENCE_DESIGN="+json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
