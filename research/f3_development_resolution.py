"""Development-only F3 resolution candidates and paired scoring.
No network, credentials, scheduling, future capture or promotion.
A supplied timestamp/hash is not independent source or first-release proof.
"""
import calendar,csv,hashlib,io,json,math,re,sys
from datetime import datetime,timezone,date
from decimal import Decimal
from pathlib import Path
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from g3_baseline_probe import local_score
from f3_local_numeric_score import score as numeric_score,ref_to_cdf
from f3_campaign_finalize import ROLES,SPECS

ARCHIVE_SHA="62a3f1c1eca0dfed23486e19df7cf3433c3f2df14ee3c440bde996bb282b70ad"
MONTHS={"F304":"2027-01","F310":"2027-01","F306":"2027-01","F307":"2027-02","F308":"2027-02","F309":"2027-02"}
BLS={"F304":"ppi","F307":"empsit"}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def utc(s):
    t=datetime.fromisoformat(s.replace("Z","+00:00"))
    require(t.tzinfo is not None and t.utcoffset().total_seconds()==0,"UTC required")
    return t
def number(v):
    require(type(v) in (str,int,float),"invalid number")
    d=Decimal(str(v));require(d.is_finite(),"nonfinite number");return d
def bounds(month):
    a=date.fromisoformat(month+"-01");b=date(a.year+(a.month==12),a.month%12+1,1);return a,b
def source_url(case,month):
    a,b=bounds(month)
    if case=="F306":
        return "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod="+str(a)+"&endPeriod="+str(b.fromordinal(b.toordinal()-1))+"&format=csvdata"
    if case=="F310":
        return "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month="+month.replace("-","")
    if case=="F308":
        return "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime="+str(a)+"T00:00:00Z&endtime="+str(b)+"T00:00:00Z&minmagnitude=6&eventtype=earthquake&limit=1000&nodata=200"
    if case=="F309":return "https://services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json"
    raise ValueError("BLS first-release archive URL must be separately established")
def load_archive(path):
    raw=Path(path).read_bytes();require(sha(raw)==ARCHIVE_SHA,"archive bytes")
    d=json.loads(raw);require(d["schema"]=="f3-frozen-reference-archive-v1" and d["source_run"]==45740139669 and d["actual_outcomes_scored"]==d["inference_calls"]==0,"archive scope")
    refs={}
    for r in d["references"]:
        c=r["case"];raw=r["raw_utf8"].encode()
        require(c in MONTHS and c not in refs and sha(raw)==r["sha256"],"reference bytes")
        v=json.loads(raw);kind,qid,snapshot=SPECS[c]
        require(v["case"]==c and v["qid"]==qid and v["snapshot_sha256"]==snapshot and v["definition"]["type"]==kind,"reference identity")
        require(sha(json.dumps(v["definition"],sort_keys=True,separators=(",",":"),ensure_ascii=True).encode())==v["definition_sha256"],"definition bytes")
        require(utc(v["frozen_at"]).date().isoformat()=="2026-11-26" and v["promotion_authorized"] is False,"freeze authority")
        refs[c]=v
    require(set(refs)==set(MONTHS),"archive coverage")
    return refs
def latest(rows,month):
    dates={};a,b=bounds(month)
    for stamp,v in rows:
        t=date.fromisoformat(stamp)
        require(a<=t<b and stamp not in dates,"unexpected or duplicate date")
        dates[stamp]=None if v in (None,"","N/A",".","-") else number(v)
    eligible=[(d,v) for d,v in dates.items() if v is not None]
    require(bool(eligible),"no eligible observation")
    return max(eligible)
class Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,d):self.parts.append(d)
def parse_bls(case,raw,month):
    p=Text();p.feed(raw.decode("utf-8"));text=" ".join(" ".join(p.parts).split())
    a,_=bounds(month);name=calendar.month_name[a.month];heading=("PRODUCER PRICE INDEXES" if case=="F304" else "THE EMPLOYMENT SITUATION")+" - "+name.upper()+" "+str(a.year)
    require(text.count(heading)==1,"BLS release heading")
    opening=text.split(heading,1)[1][:700]
    if case=="F304":
        pat=r"The Producer Price Index for final demand (rose|increased|advanced|fell|decreased|declined|edged up|edged down|moved up|moved down) (?:by )?(\d+(?:\.\d+)?) percent in "+name+r", seasonally adjusted"
        m=re.search(pat,opening,re.I)
        if m:
            n=number(m.group(2));return -n if m.group(1).lower() in ("fell","decreased","declined","edged down","moved down") else n
        require(re.search(r"The Producer Price Index for final demand (?:was unchanged|was flat) in "+name+r", seasonally adjusted",opening,re.I) is not None,"unrecognized headline; manual review")
        return Decimal(0)
    m=re.search(r"the unemployment rate (?:changed little at|was unchanged at|was|rose to|increased to|fell to|declined to|edged up to|edged down to|held at) (\d+(?:\.\d+)?) percent",opening,re.I)
    require(m is not None,"unrecognized U-3 headline; manual review")
    return number(m.group(1))
def parse(case,raw,month):
    if case in BLS:return parse_bls(case,raw,month)
    if case=="F306":
        rows=[]
        for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
            require(tuple(r[k] for k in ("FREQ","CURRENCY","CURRENCY_DENOM","EXR_TYPE","EXR_SUFFIX"))==("D","USD","EUR","SP00","A"),"ECB series")
            rows.append((r["TIME_PERIOD"],r["OBS_VALUE"]))
        d,v=latest(rows,month);require(v>0,"invalid FX rate");return v
    if case=="F310":
        rows=[]
        for el in ET.fromstring(raw).iter():
            if el.tag.split("}")[-1]=="properties":
                fields={c.tag.split("}")[-1]:c.text for c in el}
                require("NEW_DATE" in fields and "BC_10YEAR" in fields,"Treasury columns")
                rows.append((fields["NEW_DATE"][:10],fields["BC_10YEAR"]))
        return latest(rows,month)[1]
    if case=="F309":
        rows=[r for r in json.loads(raw) if r["time-tag"]==month]
        require(len(rows)==1,"missing or duplicate observed SSN")
        v=number(rows[0]["ssn"]);require(v>=0,"negative/missing SSN");return v
    if case=="F308":
        doc=json.loads(raw);require(doc["type"]=="FeatureCollection","not GeoJSON collection")
        features=doc["features"];require(len(features)<1000,"possibly truncated catalog")
        if "count" in doc.get("metadata",{}):require(doc["metadata"]["count"]==len(features),"count mismatch")
        a,b=bounds(month);lo=int(datetime(a.year,a.month,1,tzinfo=timezone.utc).timestamp()*1000);hi=int(datetime(b.year,b.month,1,tzinfo=timezone.utc).timestamp()*1000)
        ids=set();n=0
        for row in features:
            p=row["properties"];ident=row["id"]
            require(isinstance(ident,str) and ident and ident not in ids,"duplicate event")
            ids.add(ident);t=p["time"]
            require(type(t) is int and lo<=t<=hi and p["type"]=="earthquake" and number(p["mag"])>=6,"event filter")
            if t<hi:n+=1
        return Decimal(n)
    raise ValueError("unknown case")
def classify(case,value):
    v=number(value)
    if case=="F304":return 0 if v<0 else 1 if v<Decimal(".5") else 2
    if case=="F306":return int(v>=Decimal("1.15"))
    if case=="F307":require(0<=v<=100,"U-3 range");return int(v>=Decimal("4.5"))
    if case=="F309":require(v>=0,"SSN range");return 0 if v<80 else 1 if v<140 else 2
    if case=="F308":require(v>=0 and v==v.to_integral_value(),"earthquake count");return int(v)
    if case=="F310":return float(v)
    raise ValueError("unknown case")
def candidate(case,ref,raw,url,captured_at,expected_sha,now):
    """Returns only a conditional label, never an admitted resolution."""
    require(ref["case"]==case and sha(raw)==expected_sha,"capture identity")
    stamp=utc(captured_at);now=utc(now);deadline=utc(ref["definition"]["resolve"])
    _,end=bounds(MONTHS[case])
    require(end<=stamp.date() and stamp<=now and stamp<=deadline,"capture outside window")
    if case in BLS:
        m=re.fullmatch(r"https://www\.bls\.gov/news\.release/archives/"+BLS[case]+r"_(\d{8})\.htm",url)
        require(m is not None,"BLS archive URL")
        published=datetime.strptime(m.group(1),"%m%d%Y").date()
        require(end<=published<=stamp.date(),"BLS publication date")
    else:
        require(stamp.date()==deadline.date() and url==source_url(case,MONTHS[case]),"exact registered snapshot day or URL")
        if case=="F308":
            generated=json.loads(raw).get("metadata",{}).get("generated")
            require(type(generated) is int,"catalog generation time missing")
            created=datetime.fromtimestamp(generated/1000,timezone.utc)
            require(created.date()==stamp.date() and created<=stamp,"catalog generation time")
    value=parse(case,raw,MONTHS[case])
    return {"case":case,"definition_sha256":ref["definition_sha256"],"source_sha256":expected_sha,"source_url":url,"captured_at":captured_at,"value":classify(case,value),"raw_value":str(value),"status":"CANDIDATE_NOT_ADMITTED","capture_provenance_verified":False,"first_release_verified":False,"outcome_admitted":False}
def vector(value,definition):
    if definition["type"]=="binary":require(type(value) in (int,float),"binary ballot");return [1-value,value]
    require(isinstance(value,dict) and set(value)==set(definition["options"]),"MC options")
    return [value[k] for k in definition["options"]]
def scores(case,ref,forecast,label):
    d=ref["definition"];kind=d["type"];y=label["value"]
    require(label["case"]==case and label["definition_sha256"]==ref["definition_sha256"] and label["outcome_admitted"] is False,"label scope")
    require(forecast["case"]==case and forecast["qid"]==d["qid"] and forecast["question_type"]==kind and forecast["snapshot_sha256"]==ref["snapshot_sha256"] and set(forecast["members"])==ROLES,"forecast identity")
    start=utc(forecast["event_start"]);a,_=bounds(MONTHS[case])
    require(start.date()==a and start.hour==start.minute==start.second==start.microsecond==0,"event time")
    require(utc(ref["frozen_at"])<utc(forecast["latest_dispatch_at"])<=utc(forecast["forecast_issued_no_later_than"])<start,"forecast cutoff")
    prior=ref["reference"][ref["primary"]]
    arms={"aggregate":forecast["aggregate"],**forecast["members"]}
    if kind=="numeric":
        result={"reference":{"rps_normalized":numeric_score(ref_to_cdf(prior,case),y,case)}}
        for k,v in arms.items():result[k]={"rps_normalized":numeric_score(v,y,case)}
    else:
        result={"reference":local_score(prior,y,kind)}
        for k,v in arms.items():result[k]=local_score(vector(v,d),y,kind)
    # JSON-safe representation for zero probability loss.
    clean={k:{m:(x if math.isfinite(x) else "INFINITE") for m,x in v.items()} for k,v in result.items()}
    return {"case":case,"scores":clean,"status":"CONDITIONAL_DEVELOPMENT_ARITHMETIC_ONLY","actual_outcomes_scored":0,"official_score":False,"promotion_authorized":False}
def tests(refs):
    def reject(fn):
        try:fn()
        except (ValueError,KeyError,TypeError,ArithmeticError):return
        raise AssertionError("bad input accepted")
    require(classify("F304","-.1")==0 and classify("F304","0")==1 and classify("F304",".5")==2,"PPI boundaries")
    require(classify("F306","1.14999")==0 and classify("F306","1.15")==1,"FX boundaries")
    require(classify("F307","4.4999")==0 and classify("F307","4.5")==1,"U3 boundaries")
    require(classify("F309","79.9")==0 and classify("F309","80")==1 and classify("F309","140")==2,"SSN boundaries")
    reject(lambda:classify("F308","1.5"))
    require(parse_bls("F304",b"<pre>PRODUCER PRICE INDEXES - JANUARY 2027 The Producer Price Index for final demand fell 0.3 percent in January, seasonally adjusted</pre>","2027-01")==Decimal("-.3"),"headline sign")
    require(parse_bls("F307",b"<pre>THE EMPLOYMENT SITUATION - FEBRUARY 2027 and the unemployment rate was 4.5 percent</pre>","2027-02")==Decimal("4.5"),"headline U3")
    reject(lambda:parse_bls("F307",b"<pre>THE EMPLOYMENT SITUATION - JANUARY 2027 and the unemployment rate was 4.5 percent</pre>","2027-02"))
    reject(lambda:latest([("2027-01-01","1"),("2027-01-01","2")],"2027-01"))
    for c,r in refs.items():
        d=r["definition"];kind=d["type"]
        val=.6 if kind=="binary" else dict(zip(d["options"],[.2,.3,.5])) if kind=="multiple_choice" else ([0.]+[i/200 for i in range(1,201)] if c=="F308" else [i/200 for i in range(201)])
        forecast={"case":c,"qid":d["qid"],"question_type":kind,"snapshot_sha256":r["snapshot_sha256"],"members":dict.fromkeys(ROLES,val),"aggregate":val,"event_start":MONTHS[c]+"-01T00:00:00Z","latest_dispatch_at":"2026-11-27T01:00:00Z","forecast_issued_no_later_than":"2026-11-27T01:01:00Z"}
        label={"case":c,"definition_sha256":r["definition_sha256"],"value":10 if c=="F308" else 4.0 if c=="F310" else 1,"outcome_admitted":False}
        report=scores(c,r,forecast,label)
        require(len(report["scores"])==5 and report["actual_outcomes_scored"]==0 and not report["promotion_authorized"],"score ceiling")
        reject(lambda:scores(c,r,dict(forecast,qid=0),label))
        reject(lambda:scores(c,r,dict(forecast,forecast_issued_no_later_than=forecast["event_start"]),label))
        reject(lambda:scores(c,r,forecast,dict(label,outcome_admitted=True)))
    raw=json.dumps([{"time-tag":"2027-02","ssn":80,"smoothed_ssn":150}]).encode();ref=refs["F309"];u=source_url("F309","2027-02")
    result=candidate("F309",ref,raw,u,"2027-03-31T10:00:00Z",sha(raw),"2027-03-31T11:00:00Z")
    require(result["value"]==1 and result["outcome_admitted"] is False,"use observed only")
    reject(lambda:candidate("F309",ref,raw,u,"2027-03-30T10:00:00Z",sha(raw),"2027-03-31T11:00:00Z"))
    reject(lambda:candidate("F309",ref,raw,u,"2027-03-31T10:00:00Z",sha(raw),"2026-11-26T11:00:00Z"))
    reject(lambda:candidate("F309",ref,raw,u,"2027-03-31T10:00:00Z","0"*64,"2027-03-31T11:00:00Z"))
    print("F3_SCORE_SYNTHETIC_PASS cases=6 actual_outcomes_scored=0")
if __name__=="__main__":tests(load_archive(sys.argv[1]))
