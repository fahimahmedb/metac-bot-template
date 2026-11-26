"""Qualify three different public-data families for future development.
Fixed historical-only range and thresholds, no forecasting or live outcomes.
NOAA climate, EIA energy, USGS hydrology; source attribution retained.
"""
import hashlib,json,re,sys,urllib.parse
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
import g2_diverse_evidence as transport

START="2024-01-01"
END="2025-12-31"
SPECS={
 "nao":{"family":"NORTH_ATLANTIC_OSCILLATION","domain":"climate","threshold":"0","rule":"monthly index >= 0","source":"https://www.cpc.ncep.noaa.gov/products/precip/CWlink/pna/norm.nao.monthly.b5001.current.ascii","attribution":"NOAA Climate Prediction Center"},
 "oil":{"family":"US_COMMERCIAL_CRUDE_STOCKS","domain":"energy","threshold":"-1000","rule":"weekly change <= -1000 thousand barrels, excluding SPR","source":"https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=W&n=PET&s=WCESTUS1","attribution":"US Energy Information Administration"},
 "river":{"family":"POTOMAC_LITTLE_FALLS_DISCHARGE","domain":"hydrology","threshold":"10000","rule":"complete Monday-Sunday mean daily discharge >= 10000 cubic feet per second","source":"https://api.waterdata.usgs.gov/ogcapi/v1/collections/daily/items?"+urllib.parse.urlencode({"monitoring_location_id":"USGS-01646500","parameter_code":"00060","statistic_id":"00003","datetime":"2025-01-01/2025-12-31","limit":400,"f":"json"}),"attribution":"US Geological Survey"}
}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def dval(v):
    x=Decimal(str(v));require(x.is_finite(),"nonfinite value");return x
def row(d,v):
    require(START<=d<=END,"out of historical window")
    return [d,str(dval(v))]
def check_rows(rows,minimum):
    rows.sort()
    require(len(rows)>=minimum and len({r[0] for r in rows})==len(rows),"insufficient or duplicate observations")
    return rows
def nao(raw):
    rows=[]
    for line in raw.decode("ascii").splitlines():
        fields=line.split()
        if len(fields)!=3 or not re.fullmatch(r"\d{4}",fields[0]):continue
        y,m,v=fields
        if y not in ("2024","2025"):continue
        require(m.isdigit() and 1<=int(m)<=12,"invalid month")
        require(abs(dval(v))<=10,"invalid NAO range")
        rows.append(row(f"{y}-{int(m):02d}-01",v))
    return check_rows(rows,24)
class Tables(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.cells=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=="tr":self.cells=[];self.cell=None
        elif tag in ("td","th") and self.cells is not None:self.cell=[]
    def handle_data(self,s):
        if self.cell is not None:self.cell.append(s)
    def handle_endtag(self,tag):
        if tag in ("td","th") and self.cell is not None and self.cells is not None:
            self.cells.append(" ".join("".join(self.cell).split()));self.cell=None
        elif tag=="tr" and self.cells is not None:
            self.rows.append(self.cells);self.cells=None;self.cell=None
def oil(raw):
    p=Tables();p.feed(raw.decode("utf-8",errors="strict"))
    rows=[];months=set()
    for cells in p.rows:
        if not cells or not re.fullmatch(r"202[45]-[A-Za-z]{3}",cells[0]):continue
        m=datetime.strptime(cells[0],"%Y-%b");require(cells[0] not in months,"duplicate month");months.add(cells[0])
        require(len(cells)==11,"unexpected weekly table shape")
        for day,value in zip(cells[1::2],cells[2::2],strict=True):
            if not day and not value:continue
            require(re.fullmatch(r"\d{2}/\d{2}",day) is not None and re.fullmatch(r"[\d,]+",value) is not None,"invalid weekly cell")
            t=date.fromisoformat(f"{m.year}-{day.replace('/','-')}")
            require(t.month==m.month and t.weekday()==4,"weekly date mismatch")
            v=dval(value.replace(",",""));require(100000<=v<=1000000,"oil stock units/range")
            rows.append(row(str(t),v))
    require(len(months)==24,"missing monthly table rows")
    return check_rows(rows,100)
def river(raw):
    doc=json.loads(raw);fs=doc["features"]
    require(doc["type"]=="FeatureCollection" and len(fs)<=366 and doc.get("numberReturned",len(fs))==len(fs) and doc.get("numberMatched",len(fs))==len(fs),"incomplete or oversized water query")
    require(not any(x.get("rel")=="next" for x in doc.get("links",[])),"pagination incomplete")
    rows=[];series=set()
    for f in fs:
        p=f["properties"]
        require(p["monitoring_location_id"]=="USGS-01646500" and p["parameter_code"]=="00060" and p["statistic_id"]=="00003","water series identity")
        require(p["unit_of_measure"] in ("ft3/s","ft^3/s","ft3/sec","cfs","ft³/s"),"water units: "+str(p["unit_of_measure"]))
        require("2025-01-01"<=p["time"]<="2025-12-31","water dates")
        series.add(p.get("time_series_id",p.get("timeseries_id")))
        if p["value"] is None:continue
        v=dval(p["value"]);require(v>=0,"negative discharge")
        rows.append(row(p["time"],v))
    require(len(series)==1 and None not in series,"ambiguous time series")
    return check_rows(rows,330)
def labels(key,rows):
    if key=="nao":return [[r[0],int(dval(r[1])>=0)] for r in rows]
    if key=="oil":
        return [[b[0],int(dval(b[1])-dval(a[1])<=-1000)] for a,b in zip(rows,rows[1:]) if (date.fromisoformat(b[0])-date.fromisoformat(a[0])).days==7]
    by={date.fromisoformat(d):dval(v) for d,v in rows};out=[]
    for t in sorted(by):
        if t.weekday()!=0:continue
        days=[t+timedelta(days=i) for i in range(7)]
        if all(d in by for d in days):out.append([str(days[-1]),int(sum(by[d] for d in days)>=70000)])
    return out
def tests():
    require(labels("oil",[["2025-01-03","400000"],["2025-01-10","399000"],["2025-01-24","390000"]])==[["2025-01-10",1]],"oil threshold/gap")
    require(labels("nao",[["2025-01-01","0"],["2025-02-01","-.01"]])==[["2025-01-01",1],["2025-02-01",0]],"NAO threshold")
    r=[[str(date(2025,1,6)+timedelta(days=i)),"10000"] for i in range(7)]
    require(labels("river",r)==[["2025-01-12",1]] and labels("river",r[:-1])==[],"river complete week")
    try:check_rows([["2025-01-01","0"]]*2,2)
    except ValueError:pass
    else:raise AssertionError("duplicate accepted")
    try:row("2026-01-01","0")
    except ValueError:pass
    else:raise AssertionError("future relative to historical range")
    print("CROSS_DOMAIN_TESTS_PASS=5")
def main(key):
    tests();spec=SPECS[key];now=datetime.now(timezone.utc)
    require(now.date().isoformat()=="2026-11-26","source window")
    with patch.object(transport,"ALLOWED",{urllib.parse.urlsplit(spec["source"]).hostname}):
        raw=transport.fetch_public(spec["source"])
    rows={"nao":nao,"oil":oil,"river":river}[key](raw);ys=labels(key,rows)
    require(len(ys)>=20,"insufficient labels")
    prior=(sum(y for _,y in ys)+1)/(len(ys)+2)
    report={"candidate":key,"spec":spec,"retrieved_at":now.isoformat(),"source_sha256":hashlib.sha256(raw).hexdigest(),"rows":rows,"labels":ys,"baseline":{"n":len(ys),"yes":sum(y for _,y in ys),"probability":prior},"scope":"historical source probe only; revised observations possible; no confirmatory or live forecast admission","inference_calls":0,"outcomes_accessed":0,"promotion_authorized":False}
    Path("cross-domain.json").write_text(json.dumps(report,sort_keys=True))
    print("CROSS_DOMAIN_RESULT="+json.dumps({k:v for k,v in report.items() if k not in ("rows","labels")}|{"observations":len(rows),"first":rows[0][0],"last":rows[-1][0]},sort_keys=True))
if __name__=="__main__":main(sys.argv[1])
