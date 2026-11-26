"""Descriptive dependence of archived historical event labels, not forecast errors.
Reuses the pinned cross-domain reports. No future data, inference or admission."""
import json,statistics,sys,math
from datetime import date,timedelta
from pathlib import Path
from g3_cross_domain_development import prepare

def require(ok,msg):
    if not ok:raise ValueError(msg)

def period(d,key):
    t=date.fromisoformat(d)
    return t.year*12+t.month-1 if key=="nao" else (t-timedelta(days=t.weekday())).toordinal()//7

def correlation(a,b):
    if len(a)<3 or len(set(a))<2 or len(set(b))<2:return None
    return statistics.correlation(a,b)

def describe(pairs):
    a=[x for x,y in pairs];b=[y for x,y in pairs]
    return {"n":len(pairs),"r":correlation(a,b),"transition_rate":sum(x!=y for x,y in pairs)/len(pairs) if pairs else None}
def lagged(series,lag):
    require(type(lag) is int and lag>0,"lag")
    return describe([(series[k],series[k+lag]) for k in sorted(series) if k+lag in series])
def align(a,b):
    return describe([(a[k],b[k]) for k in sorted(a.keys()&b.keys())])
def tests():
    require(lagged({1:0,2:1,4:1},1)["n"]==1,"gap bridged")
    require(lagged({1:0,2:1,3:0,4:1},1)["r"]==-1,"alternating")
    require(lagged({1:1,2:1,3:1,4:1},1)["r"] is None,"constant")
    require(align({1:0,2:1,3:0},{2:0,3:1,4:0})["n"]==2,"date alignment")
    require(period("2025-01-03","oil")==period("2025-01-05","river"),"ISO week alignment")
    print("HISTORICAL_LABEL_DEPENDENCE_TESTS_PASS=5")
def main(root):
    tests()
    data={};reports={}
    for key in ("nao","oil","river"):
        raw=(root/key/"cross-domain.json").read_bytes()
        receipt=prepare(key,raw)
        labels=json.loads(raw)["labels"]
        series={period(d,key):y for d,y in labels}
        require(len(series)==len(labels),"duplicate period")
        data[key]=series
        reports[key]={"n":len(series),"report_sha256":receipt["report_sha256"],"period_unit":"months" if key=="nao" else "weeks","lags":{str(l):lagged(series,l) for l in (1,2,3,4,8)}}
    result={"series":reports,"oil_river_same_week":align(data["oil"],data["river"]),"scope":"descriptive historical revised event labels; not forecast-error dependence or evidence of independence","decision":"Do not count repeated or cross-domain labels as independent automatically. Use nonoverlapping event windows and predefine dependency groups; estimate actual paired gain dependence in development before confirmatory freeze.","inference_calls":0,"future_outcomes_accessed":0,"confirmatory_pairs":0,"promotion_authorized":False}
    Path("historical-label-dependence.json").write_text(json.dumps(result,sort_keys=True))
    print("HISTORICAL_LABEL_DEPENDENCE="+json.dumps(result,sort_keys=True))
if __name__=="__main__":main(Path(sys.argv[1]))
