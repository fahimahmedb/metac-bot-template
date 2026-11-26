"""Bounded Eurostat historical source qualification; no new forecasts or outcomes.
Source Eurostat, historical development observations only. Modifications:
filtered date/geography, derived threshold labels; Eurostat is not responsible
for these modifications. No confirmatory, economic or deployment admission.
"""
import hashlib,json,math,re,sys,urllib.parse
from datetime import datetime,timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import g2_diverse_evidence as source
BASE="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
START="2024-01"
END="2025-12"
SPECS={
 "unemployment":{"dataset":"une_rt_m","filters":{"freq":"M","s_adj":"SA","age":"TOTAL","unit":"PC_ACT","sex":"T","geo":"FR"},"family":"FR_UNEMPLOYMENT","transform":"difference","threshold":".1"},
 "retail":{"dataset":"sts_trtu_m","filters":{"freq":"M","indic_bt":"VOL_SLS","nace_r2":"G47","s_adj":"SCA","unit":"I21","geo":"FR"},"family":"FR_REAL_RETAIL","transform":"pct","threshold":".5"},
 "hicp":{"dataset":"prc_hicp_minr","filters":{"freq":"M","unit":"RCH_M","coicop18":"TOTAL","geo":"FR"},"family":"FR_HICP","transform":"level","threshold":".3"},
}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def url(key):
    s=SPECS[key]
    query={"lang":"EN",**s["filters"],"sinceTimePeriod":START,"untilTimePeriod":END}
    if key=="unemployment":
        # Explicit time positions avoid admitting a broader response. Keep
        # exactly the original range and the same frozen threshold.
        query={"lang":"EN",**s["filters"],"time":[f"{y}-{m:02d}" for y in (2024,2025) for m in range(1,13)]}
    return BASE+s["dataset"]+"?"+urllib.parse.urlencode(query,doseq=True)
def positions(category,size):
    ix=category["index"]
    require(isinstance(ix,(dict,list)),"invalid category index")
    if isinstance(ix,list): keys=ix
    else:
        require(all(type(v) is int for v in ix.values()) and set(ix.values())==set(range(size)),"invalid index positions")
        keys=sorted(ix,key=ix.get)
    require(len(keys)==size and len(set(keys))==size and all(isinstance(k,str) for k in keys),"invalid category identity")
    return keys
def month(s):
    require(isinstance(s,str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])",s) is not None,"month format")
    y,m=map(int,s.split("-"));return y*12+m
def parse(key,raw):
    obj=json.loads(raw,parse_float=Decimal)
    ids=obj["id"];sizes=obj["size"];dim=obj["dimension"];filters=SPECS[key]["filters"]
    require(obj.get("class")=="dataset" and set(ids)==set(filters)|{"time"} and len(ids)==len(set(ids))==len(sizes),"unexpected dimensions")
    require(all(type(n) is int and n>0 for n in sizes) and math.prod(sizes)<=24,"response exceeds historical bound; dimensions="+str(list(zip(ids,sizes))))
    require(obj.get("source") in ("ESTAT","Eurostat"),"source attribution")
    axes={d:positions(dim[d]["category"],n) for d,n in zip(ids,sizes,strict=True)}
    require(all(axes[d]==[v] for d,v in filters.items()),"wrong series identity")
    times=axes["time"]
    require(all(START<=t<=END for t in times),"out-of-window time")
    for t in times:month(t)
    values=obj["value"]
    if isinstance(values,list):
        require(len(values)==len(times),"value shape")
        values=dict(enumerate(values))
    else:
        require(isinstance(values,dict) and all(re.fullmatch(r"0|[1-9]\d*",k) for k in values),"value shape")
        values={int(k):v for k,v in values.items()}
    require(all(0<=i<len(times) for i in values),"value index")
    statuses=obj.get("status",{})
    if isinstance(statuses,list):
        require(len(statuses)==len(times),"status shape")
        statuses={str(i):v for i,v in enumerate(statuses) if v}
    require(isinstance(statuses,dict) and all(re.fullmatch(r"0|[1-9]\d*",i) and int(i)<len(times) for i in statuses),"status index")
    rows=[]
    for i,t in enumerate(times):
        v=values.get(i)
        if v is None:continue
        require(type(v) in (int,Decimal),"invalid value type")
        v=Decimal(v);require(v.is_finite(),"invalid numeric")
        if key=="retail":require(v>0,"nonpositive index")
        if key=="unemployment":require(0<=v<=100,"unemployment range")
        rows.append({"month":t,"value":str(v),"status":statuses.get(str(i),"")})
    rows.sort(key=lambda r:r["month"])
    require(len(rows)>=18,"insufficient history")
    return rows
def labels(key,rows):
    s=SPECS[key];threshold=Fraction(Decimal(s["threshold"]))
    vs=[(month(r["month"]),Fraction(Decimal(r["value"]))) for r in rows]
    if s["transform"]=="level":return [int(v>=threshold) for _,v in vs]
    out=[]
    for (t,a),(u,b) in zip(vs,vs[1:]):
        if u!=t+1:continue
        out.append(int(100*(b-a)>=threshold*a) if s["transform"]=="pct" else int(b-a>=threshold))
    return out
def tests():
    filters=SPECS["unemployment"]["filters"]
    times=[f"2024-{i:02d}" for i in range(1,13)]+[f"2025-{i:02d}" for i in range(1,13)]
    doc={"class":"dataset","source":"ESTAT","id":list(filters)+["time"],"size":[1]*len(filters)+[24],"dimension":{k:{"category":{"index":{v:0}}} for k,v in filters.items()}|{"time":{"category":{"index":{v:i for i,v in reversed(list(enumerate(times)))}}}},"value":{str(i):7+i/10 for i in range(24)}}
    enc=lambda d:json.dumps(d).encode()
    r=parse("unemployment",enc(doc));require(len(r)==24 and r[0]["month"]==times[0] and r[-1]["month"]==times[-1],"indexed time")
    require(labels("unemployment",[{"month":"2024-01","value":"7"},{"month":"2024-02","value":"7.1"},{"month":"2024-04","value":"9"}])==[1],"exact threshold/no gap bridging")
    require(labels("retail",[{"month":"2024-01","value":"100"},{"month":"2024-02","value":"100.5"}])==[1],"retail threshold")
    require(labels("hicp",[{"month":"2024-01","value":".3"},{"month":"2024-02","value":".2999"}])==[1,0],"HICP threshold")
    import copy
    for change in ("wrong_geo","out_of_window","bad_index","wrong_source","nonfinite"):
        d=copy.deepcopy(doc)
        if change=="wrong_geo":d["dimension"]["geo"]["category"]["index"]={"US":0}
        elif change=="out_of_window":d["dimension"]["time"]["category"]["index"]["2026-01"]=d["dimension"]["time"]["category"]["index"].pop("2025-12")
        elif change=="bad_index":d["value"]["24"]=7
        elif change=="wrong_source":d["source"]="OTHER"
        elif change=="nonfinite":d["value"]["0"]=float("nan")
        try:parse("unemployment",enc(d))
        except (ValueError,KeyError,TypeError):pass
        else:raise AssertionError("invalid accepted: "+change)
    q=urllib.parse.parse_qs(urllib.parse.urlsplit(url("unemployment")).query)
    require(q["time"]==times and q["age"]==["TOTAL"] and "sinceTimePeriod" not in q and "untilTimePeriod" not in q,"explicit bounded months")
    print("EUROSTAT_SOURCE_TESTS_PASS=10")
def main(key):
    tests()
    require(key in SPECS,"unknown candidate")
    now=datetime.now(timezone.utc)
    require(now.date().isoformat()=="2026-11-26","date window")
    # Scoped reuse of existing no-redirect HTTPS transport. No keys.
    with patch.object(source,"ALLOWED",{"ec.europa.eu"}):raw=source.fetch_public(url(key))
    rows=parse(key,raw);ys=labels(key,rows);require(len(ys)>=12,"insufficient labels")
    s=SPECS[key]
    attribution=f"Source: Eurostat, https://ec.europa.eu/eurostat/databrowser/product/view/{s['dataset']}, accessed {now.date()}. Historical filtering and threshold derivation by project; Eurostat is not responsible for modifications."
    report={"candidate":key,"family":s["family"],"spec":s,"retrieved_at":now.isoformat(),"source_url":url(key),"source_sha256":digest(raw),"attribution":attribution,"historical_range":[START,END],"rows":rows,"baseline":{"method":"Laplace-smoothed fixed threshold frequency, adjacent months only when required","n":len(ys),"yes":sum(ys),"probability":(sum(ys)+1)/(len(ys)+2)},"point_in_time_vintages_verified":False,"confirmatory_eligible":False,"inference_calls":0,"outcomes_accessed":0,"status":"HISTORICAL_SOURCE_PROBE_PASS"}
    Path("eurostat-source.json").write_bytes(raw)
    Path("eurostat-report.json").write_text(json.dumps(report,sort_keys=True))
    print("EUROSTAT_SOURCE_RESULT="+json.dumps({k:v for k,v in report.items() if k!="rows"}|{"observations":len(rows)},sort_keys=True))
if __name__=="__main__":
    if sys.argv[1:]==["--test"]:tests()
    else:main(sys.argv[1])
