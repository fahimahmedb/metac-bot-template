"""Offline development definitions for three already-qualified Eurostat sources.
No HTTP call, no outcome retrieval, no forecast, no registration or scheduling.
A candidate capture supplied by a caller is not independently authenticated.
"""
import hashlib,json,math,re,sys,urllib.parse
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from g3_eurostat_source_probe import SPECS,BASE,parse,labels,positions,month,require
TARGET="2027-01"
PREVIOUS="2026-12"
DATES={"hicp":"2027-03-05","unemployment":"2027-03-12","retail":"2027-03-15"}
# Immutable historical source and report bytes from the actual admitted probes.
PINS={
 "hicp":(45741079382,15080429790,"05052a3fdcc04c4788dcc892149916a5676742ce3b5dba37f78eb19c650184b4","ca32db163f937e2bbdd8c3b21441c1e23c2dfabc90f29e405e4139268b008681"),
 "retail":(45741079382,15080544523,"d68cde04e24dec536f5627d43fe9001e70d27e130989bf12fb53a541df90a628","9ad3d8e7f6cafedf020b4527f700282c85168da66755290dd355a4add85f7748"),
 "unemployment":(45741286536,15081436639,"c8693d18e0ec598aad32e1194fbac5451995e22dda76693f7cd2dc1db0dc327c","be02865e0e8db38527a45da40e83f30bcdb6c6f931e75150f6a00d05b0ec52de"),
}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(d):return json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def utc(s):
    x=datetime.fromisoformat(s.replace("Z","+00:00"))
    require(x.tzinfo is not None and x.utcoffset().total_seconds()==0,"UTC required")
    return x
def months(key):return [TARGET] if key=="hicp" else [PREVIOUS,TARGET]
def resolution_url(key):
    s=SPECS[key]
    return BASE+s["dataset"]+"?"+urllib.parse.urlencode({"lang":"EN",**s["filters"],"time":months(key)},doseq=True)
def definition(key):
    run,artifact,raw,report=PINS[key]
    s=SPECS[key]
    return {"id":"G3DEV-"+s["family"]+"-202701","family":s["family"],"candidate":key,"partition":"development_only","type":"binary","dataset":s["dataset"],"filters":s["filters"],"required_months":months(key),"forecast_before":"2027-01-01T00:00:00Z","target_month":TARGET,"transform":s["transform"],"threshold":s["threshold"],"resolution_source":resolution_url(key),"capture_date_utc":DATES[key],"capture_rule":"First successful official exact-date UTC capture containing all required published values and only admitted status flags; no later-vintage backfill. First-success evidence must be verified independently.","allowed_status":["","p"],"release_date_claimed":False,"source_run":run,"source_artifact":artifact,"source_sha256":raw,"report_sha256":report,"confirmatory_eligible":False,"inference_authorized":False,"capture_authorized":False,"attribution":f"Source: Eurostat, https://ec.europa.eu/eurostat/databrowser/product/view/{s['dataset']}; threshold and filtering by project, Eurostat not responsible for modifications."}
def prepare(key,raw,report):
    e=definition(key)
    require(sha(raw)==e["source_sha256"] and sha(report)==e["report_sha256"],"frozen source identity")
    d=json.loads(report);rows=parse(key,raw)
    require(d["candidate"]==key and d["spec"]==SPECS[key] and rows==d["rows"],"historical source linkage")
    require(all(r["status"] in e["allowed_status"] for r in rows),"inconsistent historical flags")
    ys=labels(key,rows);p=(sum(ys)+1)/(len(ys)+2)
    require(d["baseline"]["n"]==len(ys) and d["baseline"]["yes"]==sum(ys) and abs(d["baseline"]["probability"]-p)<1e-12,"baseline mismatch")
    return {"status":"READY_DEVELOPMENT_DEFINITION_ONLY","definition":e,"definition_sha256":sha(canonical(e)),"baseline":{"n":len(ys),"yes":sum(ys),"probability":p},"historical_provisional_rows":sum(r["status"]=="p" for r in rows),"point_in_time_vintages_verified":False,"inference_calls":0,"actual_outcomes_accessed":0}
def parse_candidate(key,raw):
    obj=json.loads(raw,parse_float=Decimal)
    ids=obj["id"];sizes=obj["size"];filters=SPECS[key]["filters"];allowed=months(key)
    require(obj.get("class")=="dataset" and obj.get("source") in ("ESTAT","Eurostat"),"source identity")
    require(len(ids)==len(set(ids))==len(sizes) and set(ids)==set(filters)|{"time"},"dimensions")
    require(all(type(n) is int and 0<=n<=len(allowed) for n in sizes),"axis bounds")
    axes={d:positions(obj["dimension"][d]["category"],n) for d,n in zip(ids,sizes,strict=True)}
    require(all(axes[d]==[v] for d,v in filters.items()),"wrong series identity")
    times=axes["time"];require(set(times)<=set(allowed),"wrong period")
    for t in times:month(t)
    values=obj.get("value",{})
    if isinstance(values,list):
        require(len(values)==len(times),"value shape");values=dict(enumerate(values))
    else:
        require(isinstance(values,dict) and all(re.fullmatch(r"0|[1-9]\d*",k) for k in values),"value indices");values={int(k):v for k,v in values.items()}
    require(all(0<=i<len(times) for i in values),"value bounds")
    statuses=obj.get("status",{})
    if isinstance(statuses,list):
        require(len(statuses)==len(times),"status shape");statuses={str(i):v for i,v in enumerate(statuses) if v}
    require(isinstance(statuses,dict) and all(re.fullmatch(r"0|[1-9]\d*",i) and int(i)<len(times) for i in statuses),"status indices")
    rows=[]
    for i,t in enumerate(times):
        v=values.get(i)
        if v is None:continue
        require(type(v) in (int,Decimal) and Decimal(v).is_finite(),"invalid value")
        v=Decimal(v)
        if key=="retail":require(v>0,"nonpositive index")
        if key=="unemployment":require(0<=v<=100,"rate bounds")
        rows.append({"month":t,"value":str(v),"status":statuses.get(str(i),"")})
    return sorted(rows,key=lambda r:r["month"])
def evaluate_capture(key,raw,captured_at,url,expected_sha):
    e=definition(key)
    require(url==e["resolution_source"] and utc(captured_at).date().isoformat()==e["capture_date_utc"] and sha(raw)==expected_sha,"capture identity/date")
    rows=parse_candidate(key,raw)
    result={"id":e["id"],"definition_sha256":sha(canonical(e)),"captured_at":captured_at,"source_sha256":expected_sha,"status":"UNRESOLVED","value":None,"capture_provenance_independently_verified":False,"first_success_independently_verified":False,"admission":False}
    if [r["month"] for r in rows]!=e["required_months"] or any(r["status"] not in e["allowed_status"] for r in rows):return result
    ys=labels(key,rows);require(len(ys)==1,"exact event arithmetic")
    return result|{"status":"TYPED_CANDIDATE_NOT_ADMITTED","value":ys[0]}
def tests():
    def response(key,vs,ts=None,flags=None,geo="FR"):
        filters=SPECS[key]["filters"]|{"geo":geo};ts=months(key) if ts is None else ts
        return canonical({"class":"dataset","source":"ESTAT","id":list(filters)+["time"],"size":[1]*len(filters)+[len(ts)],"dimension":{k:{"category":{"index":{v:0}}} for k,v in filters.items()}|{"time":{"category":{"index":{v:i for i,v in enumerate(ts)}}}},"value":vs,"status":flags or {}})
    def check(key,b,at=None,url=None,digest=None):
        return evaluate_capture(key,b,at or DATES[key]+"T12:00:00Z",url or resolution_url(key),digest or sha(b))
    def reject(fn):
        try:fn()
        except (ValueError,KeyError,TypeError,ArithmeticError):return
        raise AssertionError("invalid capture accepted")
    require(check("unemployment",response("unemployment",[7,7.1]))["value"]==1,"exact rate difference")
    require(check("retail",response("retail",[100,100.5],flags={"1":"p"}))["value"]==1,"retail provisional permitted")
    require(check("hicp",response("hicp",[.3]))["value"]==1 and check("hicp",response("hicp",[.299]))["value"]==0,"HICP exact threshold")
    require(check("retail",response("retail",[100,None]))["status"]=="UNRESOLVED","missing value")
    require(check("retail",response("retail",[100,101],flags={"1":"b"}))["status"]=="UNRESOLVED","non-admitted flag")
    require(check("hicp",response("hicp",[],ts=[]))["status"]=="UNRESOLVED","missing period")
    r=check("hicp",response("hicp",[.3]));require(r["status"]=="TYPED_CANDIDATE_NOT_ADMITTED" and r["admission"] is False and r["first_success_independently_verified"] is False,"claim ceiling")
    b=response("hicp",[.3])
    reject(lambda:check("hicp",b,at="2027-03-06T00:00:00Z"))
    reject(lambda:check("hicp",b,at="2027-03-05T01:00:00+01:00"))
    reject(lambda:check("hicp",b,url="https://example.invalid"))
    reject(lambda:check("hicp",b,digest="0"*64))
    reject(lambda:check("hicp",response("hicp",[.3],geo="US")))
    reject(lambda:check("hicp",response("hicp",[.3],ts=["2027-02"])))
    reject(lambda:check("retail",response("retail",[0,100])))
    print("EUROSTAT_DEVELOPMENT_TESTS_PASS=14 synthetic_only=true")
if __name__=="__main__":
    tests()
    if sys.argv[1:]==["--test"]:sys.exit(0)
    key=sys.argv[1];root=Path(sys.argv[2])
    r=prepare(key,(root/"eurostat-source.json").read_bytes(),(root/"eurostat-report.json").read_bytes())
    Path("eurostat-definition.json").write_bytes(canonical(r))
    print("EUROSTAT_DEFINITION="+json.dumps(r,sort_keys=True))
