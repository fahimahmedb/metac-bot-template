"""Descriptive forecast-error dependence on the already consumed ForecastBench
development artifact (CC BY-SA 4.0). No holdout access, no F3 inference.
"""
import hashlib,json,math,statistics,sys
from collections import defaultdict,Counter
from datetime import date
from pathlib import Path
from aggregation_development import choose_values,pred

PIN="aca79df1c14b20b4f19a19941ed323305b6a24d9475ac66ca6663077ce74d554"
ARCHIVE="1ddccd02e1410533a944d9fb7ff94bc2d56a980bd6446a5fbec27bd560463dfa"
def require(ok,msg):
    if not ok:raise ValueError(msg)
def corr(pairs):
    if len(pairs)<3:return None
    a,b=zip(*pairs)
    if len(set(a))<2 or len(set(b))<2:return None
    return statistics.correlation(a,b)
def summary(rows,mode):
    groups=defaultdict(list)
    for r in rows:
        d=date.fromisoformat(r["issued"]);end=date.fromisoformat(r["resolved"])
        require(d<end and type(r["y"]) is int and r["y"] in (0,1),"row timing/label")
        p=pred(choose_values(r,mode),"median");q=pred(choose_values(r,mode),"logit_1.3")
        y=r["y"]
        groups[d].append((end,(.5-y)**2-(p-y)**2,(p-y)**2-(q-y)**2))
    dates=sorted(groups)
    if not dates:return {"rounds":0,"n":0}
    sizes=[len(groups[d]) for d in dates];n=sum(sizes)
    vals={}
    for index,name in ((1,"median_vs_half"),(2,"logit_1.3_vs_median")):
        means={d:statistics.mean(x[index] for x in groups[d]) for d in dates}
        lags={}
        for gap in (14,28,56):
            pairs=[(means[a],means[b]) for a in dates for b in dates if (b-a).days==gap]
            lags[str(gap)]={"pairs":len(pairs),"correlation_descriptive":corr(pairs)}
        vals[name]={"event_weighted_gain":sum(x[index] for d in dates for x in groups[d])/n,"round_equal_gain":statistics.mean(means.values()),"round_sd":statistics.stdev(means.values()) if len(dates)>1 else None,"positive_rounds":sum(v>0 for v in means.values()),"exact_calendar_lags_days":lags}
    transitions=[]
    for a,b in zip(dates,dates[1:]):
        transitions.append({"gap_days":(b-a).days,"earlier_rows":len(groups[a]),"resolution_not_before_next_issue":sum(x[0]>=b for x in groups[a])})
    denom=sum(t["earlier_rows"] for t in transitions)
    return {"n":n,"rounds":len(dates),"round_weight_concentration_kish":n*n/sum(k*k for k in sizes),"round_sizes_min_max":[min(sizes),max(sizes)],"issue_gap_days":dict(Counter(t["gap_days"] for t in transitions)),"earlier_resolution_date_not_before_next_issue_fraction":sum(t["resolution_not_before_next_issue"] for t in transitions)/denom if denom else None,"metrics":vals}
def main(path,mode):
    require(mode in ("all","three"),"mode")
    raw=Path(path).read_bytes();require(hashlib.sha256(raw).hexdigest()==PIN,"artifact digest")
    d=json.loads(raw);require(d["archive_sha256"]==ARCHIVE,"archive identity")
    rows=d["rows"];require(len(rows)==1060 and len({r["id"] for r in rows})==1060 and Counter(r["partition"] for r in rows)=={"train":948,"validation":112},"frozen development coverage")
    require(corr([(0,0),(1,1),(2,2)])==1 and corr([(0,0),(1,1)]) is None and corr([(1,0),(1,1),(1,2)]) is None,"correlation guards")
    r={"mode":mode,"source_json_sha256":PIN,"license":d["license"],"scope":"previously consumed archived development forecast errors, not F3 or actual independence evidence","reports":{k:summary([v for v in rows if v["partition"]==k],mode) for k in ("train","validation")},"pooled_descriptive":summary(rows,mode),"inference_calls":0,"confirmatory_pairs":0,"promotion_authorized":False,"decision":"do not infer a maximum dependence lag from this short, irregular, overlapping archive"}
    Path("g3-archive-dependence.json").write_text(json.dumps(r,sort_keys=True))
    print("G3_ARCHIVE_DEPENDENCE="+json.dumps(r,sort_keys=True))
if __name__=="__main__":main(*sys.argv[1:])
