"""Development-only exact-date resolution definitions for climate, energy,
and hydrology. Reuses historical source receipts. No HTTP or future retrieval.
Caller capture provenance/first-success remain independently unverified.
"""
import hashlib,html,json,sys,re,urllib.parse
from datetime import date,datetime,timedelta
from decimal import Decimal
from pathlib import Path
import g3_cross_domain_sources as old

RUN=45741785164
PINS={
 "nao":(15080828037,"81998461219a33988b341b565137b19ee0838f893c489d7f513dc532a7ff559d","0297c3df76d8fac850e8af9b394ff7df701c1e77e9eb768268ee9be12aebb3a5"),
 "oil":(15081616469,"dc0e9ce35ab9b821b3f5c9b7bf459a74cfa52197ea3bf9b1d835b4d35b51b8e1","ca4920b3cc30b4a7e0ee9ef0ff8bb610e9cc6aae4c595778a3edf0800df0c604"),
 "river":(15081541790,"a92ed53fe41b4e0175bd6800517c04cc49eaf613f092060c13a8bbdb2934a2e3","a49580cf83d951e670e11cbaf17d8f2e80d1b88b7b172aca1a2b21c71464ed51")
}
REPORT_PINS={
 "nao":"f668df14de9492e62257cc38c9cad1cc0e5b4607a54a388a4cadfe09badc1814",
 "oil":"893ed55c631d6192650ef78b5fd79e3146b7536d7ff3083aa8fe1fe84029e848",
 "river":"469a91b55e3cd0e80ac4862c799f18663440dd2077e3fd943c96851de358feba"}
DATES={"nao":"2027-03-05","oil":"2027-01-27","river":"2027-02-01"}
WEEK=[str(date(2027,1,11)+timedelta(days=i)) for i in range(7)]
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(doc):return json.dumps(doc,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def utc(s):
    d=datetime.fromisoformat(s.replace("Z","+00:00"))
    require(d.tzinfo is not None and d.utcoffset().total_seconds()==0,"UTC required")
    return d
def source(key):
    if key!="river":return old.SPECS[key]["source"]
    u=urllib.parse.urlsplit(old.SPECS[key]["source"])
    q=urllib.parse.parse_qs(u.query)
    q.update(datetime=[WEEK[0]+"/"+WEEK[-1]],limit=["14"])
    return urllib.parse.urlunsplit((u.scheme,u.netloc,u.path,urllib.parse.urlencode(q,doseq=True),""))
def definition(key):
    spec=old.SPECS[key];a,z,h=PINS[key]
    period={"nao":["2027-01-01"],"oil":["2027-01-08","2027-01-15"],"river":WEEK}[key]
    return {"id":"G3DEV-"+spec["family"]+"-202701","family":spec["family"],"domain":spec["domain"],"type":"binary","partition":"development_only","required_periods":period,"forecast_before":"2027-01-01T00:00:00Z","rule":spec["rule"],"threshold":spec["threshold"],"resolution_source":source(key),"capture_date_utc":DATES[key],"capture_rule":"First successful exact-date UTC capture with complete valid observations; no later backfill; independently verify first success and provenance.","capture_date_is_release_date":False,"allow_provisional_river":key=="river","source_run":RUN,"source_artifact":a,"artifact_zip_sha256":z,"historical_source_sha256_reported":h,"attribution":spec["attribution"],"confirmatory_eligible":False,"inference_authorized":False,"capture_authorized":False}
def prepare(key,raw):
    require(sha(raw)==REPORT_PINS[key],"exact archived report bytes")
    d=json.loads(raw);e=definition(key)
    require(d["candidate"]==key and d["spec"]==old.SPECS[key] and d["source_sha256"]==PINS[key][2],"source identity")
    require(utc(d["retrieved_at"]).date().isoformat()=="2026-11-26" and d["inference_calls"]==d["outcomes_accessed"]==0 and d["promotion_authorized"] is False,"historical scope")
    rows=d["rows"]
    require(rows==sorted(rows) and len({r[0] for r in rows})==len(rows) and all(old.START<=r[0]<=old.END for r in rows),"historical dates")
    for t,v in rows:date.fromisoformat(t);old.dval(v)
    ys=old.labels(key,rows)
    require(ys==d["labels"] and len(ys)==d["baseline"]["n"] and sum(y for _,y in ys)==d["baseline"]["yes"],"historical label mismatch")
    p=(sum(y for _,y in ys)+1)/(len(ys)+2)
    require(abs(p-d["baseline"]["probability"])<1e-12,"baseline mismatch")
    return {"definition":e,"definition_sha256":sha(canonical(e)),"report_sha256":sha(raw),"baseline":d["baseline"],"original_historical_source_bytes_verified":False,"status":"READY_DEVELOPMENT_DEFINITION_ONLY","inference_calls":0,"actual_outcomes_accessed":0}
def extract_nao(raw):
    values={};seen=False
    for line in raw.decode("ascii").splitlines():
        f=line.split()
        if len(f)<2 or f[0]!="2027" or f[1] not in ("1","01"):continue
        require(len(f)==3 and not seen,"duplicate/malformed NAO")
        seen=True
        if f[2] in ("-99.9","-999","-999.0","-999.9"):continue
        x=old.dval(f[2]);require(abs(x)<=10,"NAO range")
        values["2027-01-01"]=x
    return values
def extract_oil(raw):
    text=raw.decode("utf-8")
    plain=" ".join(html.unescape(re.sub(r"<[^>]+>"," ",text)).split())
    require(re.search(r"Weekly\s+U\.S\.\s+Ending Stocks excluding SPR of Crude Oil\s*\(Thousand Barrels\)",plain,re.I) is not None,"EIA series title")
    p=old.Tables();p.feed(text)
    values={};seen=set();months=0
    for cells in p.rows:
        if not cells or cells[0]!="2027-Jan":continue
        months+=1;require(months==1 and len(cells)==11,"duplicate/malformed oil month")
        for d,v in zip(cells[1::2],cells[2::2],strict=True):
            if d not in ("01/08","01/15"):continue
            t="2027-"+d.replace("/","-")
            require(t not in seen,"duplicate oil week")
            seen.add(t)
            if v in ("","-","--","NA","W"):continue
            require(re.fullmatch(r"[\d,]+",v) is not None,"oil numeric format")
            x=old.dval(v.replace(",",""));require(100000<=x<=1000000,"oil units/range")
            values[t]=x
    return values
def extract_river(raw):
    obj=json.loads(raw);fs=obj["features"]
    require(obj["type"]=="FeatureCollection" and len(fs)<=14 and obj.get("numberMatched",len(fs))==obj.get("numberReturned",len(fs))==len(fs),"water completeness")
    require(not any(l.get("rel")=="next" for l in obj.get("links",[])),"water pagination")
    values={};series=set();seen=set()
    for f in fs:
        p=f["properties"];t=p["time"]
        require(p["monitoring_location_id"]=="USGS-01646500" and p["parameter_code"]=="00060" and p["statistic_id"]=="00003" and t in WEEK and t not in seen,"water identity/date")
        seen.add(t)
        require(p["unit_of_measure"] in ("ft3/s","ft^3/s","ft3/sec","cfs","ft³/s"),"water units")
        series.add(p.get("time_series_id",p.get("timeseries_id")))
        if p["value"] is None or p.get("approval_status") not in ("Approved","Provisional"):continue
        x=old.dval(p["value"]);require(x>=0,"negative water")
        values[t]=x
    require(len(series)<=1 and None not in series,"water time series identity")
    return values
def evaluate_capture(key,raw,captured_at,url,digest):
    e=definition(key)
    require(url==e["resolution_source"] and sha(raw)==digest and utc(captured_at).date().isoformat()==e["capture_date_utc"],"capture identity/date")
    values={"nao":extract_nao,"oil":extract_oil,"river":extract_river}[key](raw)
    r={"id":e["id"],"definition_sha256":sha(canonical(e)),"captured_at":captured_at,"source_sha256":digest,"status":"UNRESOLVED","value":None,"admission":False,"first_success_independently_verified":False,"capture_provenance_independently_verified":False}
    if set(values)!=set(e["required_periods"]):return r
    if key=="nao":y=int(values["2027-01-01"]>=0)
    elif key=="oil":y=int(values["2027-01-15"]-values["2027-01-08"]<=-1000)
    else:y=int(sum(values.values())>=70000)
    return r|{"status":"TYPED_CANDIDATE_NOT_ADMITTED","value":y}
def tests():
    def check(k,b,t=None,u=None,h=None):return evaluate_capture(k,b,t or DATES[k]+"T12:00:00Z",u or source(k),h or sha(b))
    def reject(fn):
        try:fn()
        except (ValueError,TypeError,KeyError,ArithmeticError):return
        raise AssertionError("invalid capture accepted")
    require(check("nao",b"2027 1 0")["value"]==1 and check("nao",b"2027 01 -0.01")["value"]==0,"NAO equality")
    require(check("nao",b"2026 1 1")["status"]=="UNRESOLVED","NAO missing")
    reject(lambda:check("nao",b"2027 1 0\n2027 1 1"))
    def oil(b,title="Weekly U.S. Ending Stocks excluding SPR of Crude Oil (Thousand Barrels)",duplicate=False):
        cells=["2027-Jan","01/01","410,000","01/08","400,000","01/15",b,"01/15" if duplicate else "01/22","399,000" if duplicate else "","01/29",""]
        return ("<h1>"+title+"</h1><table><tr>"+"".join("<td>"+s+"</td>" for s in cells)+"</tr></table>").encode()
    require(check("oil",oil("399,000"))["value"]==1 and check("oil",oil("399,001"))["value"]==0,"oil equality")
    require(check("oil",oil(""))["status"]=="UNRESOLVED","oil missing")
    def river(n=7,v="10000",status="Provisional",unit="ft3/s",site="USGS-01646500"):
        fs=[{"properties":{"time":t,"value":v,"approval_status":status,"unit_of_measure":unit,"monitoring_location_id":site,"parameter_code":"00060","statistic_id":"00003","time_series_id":"synthetic"}} for t in WEEK[:n]]
        return canonical({"type":"FeatureCollection","features":fs,"numberMatched":len(fs),"numberReturned":len(fs),"links":[]})
    require(check("river",river())["value"]==1 and check("river",river(v="9999.99"))["value"]==0,"river equality")
    require(check("river",river(n=6))["status"]=="UNRESOLVED","river incomplete")
    require(check("river",river(status="unknown"))["status"]=="UNRESOLVED","water approval")
    reject(lambda:check("river",river(unit="m3/s")))
    reject(lambda:check("river",river(site="wrong")))
    reject(lambda:check("nao",b"2027 1 0",t="2027-03-06T00:00:00Z"))
    reject(lambda:check("nao",b"2027 1 0",t="2027-03-05T01:00:00+01:00"))
    reject(lambda:check("nao",b"2027 1 0",h="0"*64))
    reject(lambda:check("nao",b"2027 1 0",u="https://example.invalid"))
    require(not check("nao",b"2027 1 0")["admission"],"claim ceiling")
    reject(lambda:check("nao",b"2027 1 -99.9\n2027 1 1"))
    reject(lambda:check("oil",oil("399,000",title="Different petroleum series")))
    reject(lambda:check("oil",oil("",duplicate=True)))
    require(check("oil",oil("NA"))["status"]=="UNRESOLVED","explicit unavailable value")
    print("CROSS_DOMAIN_DEVELOPMENT_TESTS_PASS=19 synthetic_only=true")
if __name__=="__main__":
    tests()
    key=sys.argv[1];raw=Path(sys.argv[2]).read_bytes()
    r=prepare(key,raw)
    # Changing the historical rows/labels could otherwise preserve the same
    # definition hash and alter the baseline despite a reported source hash.
    tampered=json.loads(raw)
    tampered["rows"]=tampered["rows"][:-1]
    ys=old.labels(key,tampered["rows"]);n=len(ys);y=sum(v for _,v in ys)
    tampered["labels"]=ys;tampered["baseline"]={"n":n,"yes":y,"probability":(y+1)/(n+2)}
    try:prepare(key,canonical(tampered))
    except ValueError:pass
    else:raise AssertionError("tampered archived report admitted")
    print("CROSS_DOMAIN_PINNED_REPORT_TAMPER_REJECTED")
    Path("cross-domain-definition.json").write_bytes(canonical(r))
    print("CROSS_DOMAIN_DEFINITION="+json.dumps(r,sort_keys=True))
